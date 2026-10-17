"""Proveedor Promptfoo para ejecutar un turno real de la arquitectura centralizada."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
from pathlib import Path
from typing import Any

# Promptfoo ejecuta proveedores Python con el directorio `evals` como ruta de
# trabajo. Añadir explícitamente la raíz permite importar la arquitectura y el
# paquete `core` sin depender del entorno desde el que se lanzó npm.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arch_centralizada import construir_agentes_centralizados, ejecutar_turno_centralizado
from core.config import get_settings
from core.llm import get_active_model
from core.tools import establecer_mock_clima, obtener_traza_herramientas
import core.tools as tools
from evals.isolated_agenda import isolated_agenda

try:
    _ = tools._faq_store.encoder
except Exception:
    pass


def _resultado_json(valor: Any) -> Any:
    if not isinstance(valor, str):
        return valor
    try:
        return json.loads(valor)
    except json.JSONDecodeError:
        return valor[:1000]


def _normalizar_traza(traza: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalizada = []
    for item in traza:
        normalizada.append(
            {
                "nombre": item["nombre"],
                "argumentos": item.get("argumentos", {}),
                "exitosa": item.get("exitosa", False),
                "resultado": _resultado_json(item.get("resultado")),
                "error": item.get("error"),
                "duracion_ms": item.get("duracion_ms", 0),
            }
        )
    return normalizada


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    variables = context.get("vars", {}) if context else {}
    query = variables.get("query", prompt)
    mock_mode = variables.get("mock_mode")
    arquitectura = "centralizada"
    inicio = time.perf_counter()
    establecer_mock_clima(mock_mode)
    try:
        # Se construye un agente por caso para impedir que el historial de un caso
        # contamine los siguientes casos de Promptfoo.
        agente = construir_agentes_centralizados(get_active_model())
        async def ejecutar_y_cerrar():
            try:
                return await ejecutar_turno_centralizado(agente, query)
            finally:
                # Los especialistas comparten el mismo modelo/cliente.
                await agente.model._client.close()

        with isolated_agenda():
            respuesta, comprobante = asyncio.run(ejecutar_y_cerrar())
        traza = _normalizar_traza(obtener_traza_herramientas())
        appointment = None
        weather = None
        faq_ids: list[str] = []
        for item in traza:
            resultado = item.get("resultado")
            if not isinstance(resultado, dict):
                continue
            if item["nombre"] == "consultar_clima":
                weather = resultado
            if item["nombre"] == "buscar_faqs":
                faq_ids.extend(
                    faq.get("id") for faq in resultado.get("faqs", []) if faq.get("id")
                )
            if item["nombre"] == "agendar_cita":
                appointment = resultado
        payload = {
            "answer": respuesta,
            "tool_calls": traza,
            "tool_sequence": [item["nombre"] for item in traza],
            "latency_ms": round((time.perf_counter() - inicio) * 1000, 2),
            "appointment": appointment,
            "weather": weather,
            "retrieved_faq_ids": faq_ids,
            "comprobante": comprobante,
            "model": get_active_model(),
            "architecture": arquitectura,
            "error": None,
        }
    except Exception as error:
        payload = {
            "answer": "",
            "tool_calls": [],
            "tool_sequence": [],
            "latency_ms": round((time.perf_counter() - inicio) * 1000, 2),
            "appointment": None,
            "weather": None,
            "retrieved_faq_ids": [],
            "comprobante": None,
            "model": get_active_model(),
            "architecture": arquitectura,
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        establecer_mock_clima(None)

    return {"output": json.dumps(payload, ensure_ascii=False), "metadata": payload}
