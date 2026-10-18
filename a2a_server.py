"""Servidor A2A del MAS centralizado, con herramientas exclusivamente remotas."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import logging
from time import perf_counter
from uuid import uuid4

from a2a.helpers import new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Role
from a2a.utils.errors import InvalidParamsError, TaskNotCancelableError
from agents import Agent
from agents.items import TResponseInputItem
from starlette.applications import Starlette
import uvicorn

from mas_mcp import conectar_mas_mcp, ejecutar_turno_mcp

logger = logging.getLogger("parachute.a2a")


def crear_agent_card(url: str) -> AgentCard:
    return AgentCard(
        name="Asistente Parachute S.A.",
        description="Atención al cliente, clima y seguridad, y reservas de paracaidismo.",
        version="1.0.0", default_input_modes=["text/plain"],
        default_output_modes=["text/plain"], capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[AgentInterface(
            protocol_binding="JSONRPC", protocol_version="1.0", url=url,
        )],
        skills=[
            AgentSkill(
                id="preguntas_frecuentes", name="Preguntas frecuentes",
                description="Consulta las FAQs de Parachute con referencias al corpus.",
                tags=["faqs", "paracaidismo"], examples=["¿Cuál es el peso máximo?"],
            ),
            AgentSkill(
                id="clima_seguridad", name="Clima y seguridad",
                description="Consulta el pronóstico y evalúa las condiciones para saltar.",
                tags=["clima", "seguridad"], examples=["¿Se puede saltar mañana?"],
            ),
            AgentSkill(
                id="reservas", name="Gestión de reservas",
                description="Consulta cupos y registra reservas con evidencia meteorológica válida.",
                tags=["agenda", "reservas"], examples=["Quiero reservar un salto."],
            ),
        ],
    )


@dataclass
class Conversacion:
    historial: list[TResponseInputItem] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class EjecutorParachute(AgentExecutor):
    def __init__(self) -> None:
        self.orquestador: Agent | None = None
        self.conversaciones: dict[str, Conversacion] = {}

    async def execute(self, context: RequestContext, event_queue) -> None:
        mensaje = context.message
        if (mensaje is None or mensaje.role != Role.ROLE_USER or not mensaje.parts
                or any(parte.WhichOneof("content") != "text" or not parte.text for parte in mensaje.parts)
                or not context.get_user_input().strip()):
            raise InvalidParamsError(message="Se requiere un mensaje de usuario con texto no vacío.")

        tarea = context.current_task or new_task_from_user_message(mensaje)
        if context.current_task is None:
            await event_queue.enqueue_event(tarea)
        updater = TaskUpdater(event_queue, tarea.id, tarea.context_id)
        solicitud = str(uuid4())
        inicio = perf_counter()
        identificadores = (solicitud, tarea.id, tarea.context_id)
        logger.info("inicio solicitud=%s tarea=%r contexto=%r", *identificadores)
        await updater.start_work()
        conversacion = self.conversaciones.setdefault(tarea.context_id, Conversacion())
        try:
            async with conversacion.lock:
                if self.orquestador is None:
                    raise RuntimeError("El MAS no está conectado.")
                entrada = conversacion.historial + [{"role": "user", "content": context.get_user_input()}]
                resultado, comprobante = await ejecutar_turno_mcp(
                    self.orquestador, entrada, solicitud_id=solicitud,
                )
                respuesta = resultado.final_output_as(str, raise_if_incorrect_type=True)
                historial = resultado.to_input_list()
                if comprobante is not None:
                    await updater.add_artifact([new_text_part(comprobante)], name="comprobante")
                await updater.complete(message=updater.new_agent_message([new_text_part(respuesta)]))
                conversacion.historial = historial
        except Exception as error:
            logger.error(
                "fallo solicitud=%s tarea=%r contexto=%r error=%s duracion_ms=%.1f",
                *identificadores, type(error).__name__, (perf_counter() - inicio) * 1000,
            )
            await updater.failed(message=updater.new_agent_message([new_text_part(
                "No se pudo completar la solicitud. Si solicitaste una reserva, "
                "consulta las citas antes de volver a intentarlo: su resultado podría ser incierto."
            )]))
            return
        logger.info(
            "fin solicitud=%s tarea=%r contexto=%r estado=completada duracion_ms=%.1f",
            *identificadores, (perf_counter() - inicio) * 1000,
        )

    async def cancel(self, context: RequestContext, event_queue) -> None:
        # Cancelar una llamada no revierte una reserva que MCP ya haya registrado.
        raise TaskNotCancelableError(message="No se cancelan solicitudes de resultado potencialmente incierto.")


def crear_aplicacion_a2a(
    *, mcp_url: str = "http://127.0.0.1:8001/mcp", model_name: str | None = None,
    url: str = "http://127.0.0.1:8000",
) -> Starlette:
    ejecutor = EjecutorParachute()
    card = crear_agent_card(url)
    handler = DefaultRequestHandler(
        agent_executor=ejecutor, task_store=InMemoryTaskStore(), agent_card=card,
        validate_input_modes=True,
    )

    @asynccontextmanager
    async def lifespan(app):
        async with conectar_mas_mcp(mcp_url=mcp_url, model_name=model_name) as orquestador:
            ejecutor.orquestador = orquestador
            logger.info("MAS conectado a MCP; servidor A2A listo")
            try:
                yield
            finally:
                ejecutor.orquestador = None
                ejecutor.conversaciones.clear()
        logger.info("Conexiones MCP y LLM cerradas")

    return Starlette(
        routes=create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/"),
        lifespan=lifespan,
    )


def main(*, puerto: int = 8000, mcp_url: str = "http://127.0.0.1:8001/mcp",
         model_name: str | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    url = f"http://127.0.0.1:{puerto}"
    logger.info("Iniciando A2A en %s; Agent Card: %s/.well-known/agent-card.json", url, url)
    try:
        uvicorn.run(
            crear_aplicacion_a2a(mcp_url=mcp_url, model_name=model_name, url=url),
            host="127.0.0.1", port=puerto,
        )
    except KeyboardInterrupt:
        pass
