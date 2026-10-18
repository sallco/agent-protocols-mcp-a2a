"""Conexión del MAS centralizado a las herramientas remotas de Parachute S.A."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
from uuid import UUID, uuid4

from agents import Agent, RunHooks, RunResult, Runner
from agents.items import TResponseInputItem
from agents.mcp import MCPServerStreamableHttp

from arch_centralizada import construir_agentes_centralizados
from core.llm import create_model, get_async_openai_client

HERRAMIENTAS_POR_ESPECIALISTA = {
    "especialista_faqs": {"buscar_faqs"},
    "especialista_clima_seguridad": {"resolver_fecha", "consultar_clima", "evaluar_condiciones"},
    "especialista_agenda": {"consultar_disponibilidad", "agendar_cita", "listar_citas"},
}


@dataclass
class ContextoTurno:
    solicitud_id: str = field(default_factory=lambda: str(uuid4()))
    comprobante: str | None = None


class CapturarComprobante(RunHooks[ContextoTurno]):
    async def on_tool_end(self, context, agent, tool, result) -> None:
        if tool.name != "agendar_cita":
            return
        texto = result["text"] if isinstance(result, dict) else result
        reserva = json.loads(texto)
        if reserva.get("exito") is True:
            comprobante = reserva.get("comprobante")
            if not isinstance(comprobante, str) or not comprobante:
                raise ValueError("La reserva confirmada no incluyó su comprobante.")
            context.context.comprobante = comprobante


def filtrar_herramientas(context, tool) -> bool:
    return tool.name in HERRAMIENTAS_POR_ESPECIALISTA.get(context.agent.name, ())


def metadatos_herramienta(context) -> dict[str, str]:
    return {"request_id": context.run_context.context.solicitud_id}


@asynccontextmanager
async def conectar_mas_mcp(
    *, mcp_url: str = "http://127.0.0.1:8001/mcp", model_name: str | None = None
) -> AsyncIterator[Agent]:
    """Mantiene MCP y el cliente LLM abiertos hasta que se detiene el consumidor."""
    async with get_async_openai_client() as client:
        async with MCPServerStreamableHttp(
            name="Parachute", params={"url": mcp_url, "timeout": 30},
            cache_tools_list=True, tool_filter=filtrar_herramientas,
            tool_meta_resolver=metadatos_herramienta,
            client_session_timeout_seconds=30, max_retry_attempts=0,
            failure_error_function=None,
        ) as server:
            yield construir_agentes_centralizados(
                model=create_model(model_name, client=client), mcp_server=server,
                hooks=CapturarComprobante(),
            )


async def ejecutar_turno_mcp(
    orquestador: Agent, entrada: str | list[TResponseInputItem],
    *, solicitud_id: str | None = None,
) -> tuple[RunResult, str | None]:
    """Devuelve el resultado nativo del SDK y el comprobante exacto de este turno."""
    contexto = ContextoTurno()
    if solicitud_id is not None:
        contexto.solicitud_id = str(UUID(solicitud_id))
    resultado = await Runner.run(
        orquestador, entrada, context=contexto, hooks=CapturarComprobante(), max_turns=20,
    )
    return resultado, contexto.comprobante
