"""Matriz comparativa de rendimiento y comportamiento de las tres arquitecturas."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from arch_centralizada import construir_agentes_centralizados, ejecutar_turno_centralizado
from arch_descentralizada import construir_red_descentralizada, ejecutar_turno_descentralizado
from arch_jerarquica import construir_agentes_jerarquicos, ejecutar_turno_jerarquico


ESCENARIOS = [
    {
        "id": "faq_institucional",
        "descripcion": "Consulta pura de FAQs sobre el evento",
        "prompt": "¿Dónde se realizará el evento nacional de paracaidismo Guatemala 2026 y qué requisitos de peso aplican?",
    },
    {
        "id": "clima_seguridad",
        "descripcion": "Consulta pura de pronóstico meteorológico y veredicto de salto",
        "prompt": "¿Cuáles son las condiciones meteorológicas esperadas para el 29 de septiembre de 2026 y cuál es el veredicto de seguridad?",
    },
    {
        "id": "flujo_combinado",
        "descripcion": "Petición mixta (FAQ + Clima + Intento de Reserva)",
        "prompt": "Quiero saber si hay restricciones de edad y si puedo agendar una cita para el 29 de septiembre de 2026 a las 11:00 para Diego Calderón.",
    },
]


async def evaluar_arquitectura(nombre_arq: str, prompt: str) -> dict[str, Any]:
    inicio = time.perf_counter()
    comprobante: str | None = None
    respuesta: str = ""
    agente_final: str = ""

    if nombre_arq == "centralizada":
        orquestador = construir_agentes_centralizados()
        respuesta, comprobante = await ejecutar_turno_centralizado(orquestador, prompt)
        agente_final = orquestador.name
    elif nombre_arq == "jerarquica":
        orquestador = construir_agentes_jerarquicos()
        respuesta, comprobante = await ejecutar_turno_jerarquico(orquestador, prompt)
        agente_final = orquestador.name
    elif nombre_arq == "descentralizada":
        agente_faqs, _, _ = construir_red_descentralizada()
        respuesta, nuevo_agente, comprobante = await ejecutar_turno_descentralizado(agente_faqs, prompt)
        agente_final = nuevo_agente.name

    duracion = round(time.perf_counter() - inicio, 2)
    longitud_resp = len(respuesta)

    return {
        "arquitectura": nombre_arq,
        "latencia_segundos": duracion,
        "caracteres_respuesta": longitud_resp,
        "agente_final": agente_final,
        "comprobante_generado": bool(comprobante),
        "fragmento_respuesta": respuesta[:180] + "..." if len(respuesta) > 180 else respuesta,
    }


async def ejecutar_matriz_completa() -> list[dict[str, Any]]:
    resultados = []
    print("Iniciando ejecución de la matriz comparativa...")

    for esc in ESCENARIOS:
        print(f"\n=======================================================")
        print(f"Escenario: {esc['id']} - {esc['descripcion']}")
        print(f"=======================================================")

        for arq in ["centralizada", "jerarquica", "descentralizada"]:
            print(f"  > Evaluando arquitectura: {arq}...")
            try:
                metrica = await evaluar_arquitectura(arq, esc["prompt"])
                metrica["escenario"] = esc["id"]
                resultados.append(metrica)
                print(f"    [OK] Latencia: {metrica['latencia_segundos']}s | Agente: {metrica['agente_final']}")
            except Exception as exc:
                print(f"    [ERROR en {arq}]: {exc}")
                resultados.append({
                    "escenario": esc["id"],
                    "arquitectura": arq,
                    "error": str(exc),
                })

    output_path = Path(__file__).parent / "data" / "comparativa_arquitecturas.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nMatriz comparativa guardada exitosamente en {output_path}")
    return resultados


def main() -> None:
    asyncio.run(ejecutar_matriz_completa())


if __name__ == "__main__":
    main()
