"""Arquitectura Descentralizada: Red de pares autónomos coordinados mediante handoffs."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from agents import Agent, Runner, handoff
from core.llm import create_model
from core.tools import (
    limpiar_ultimo_comprobante,
    obtener_ultimo_comprobante,
    tool_agendar_cita,
    tool_buscar_faqs,
    tool_consultar_clima,
    tool_consultar_disponibilidad,
    tool_evaluar_condiciones,
    tool_listar_citas,
    tool_resolver_fecha,
)


def construir_red_descentralizada(model_name: str | None = None) -> tuple[Agent, Agent, Agent]:
    """Construye los tres agentes especialistas con transferencias de control bidireccionales."""
    model = create_model(model_name)

    # 1. Agente FAQs (atención inicial y conocimiento)
    agente_faqs = Agent(
        name="agente_faqs",
        instructions=(
            "Eres el Agente Especialista en FAQs y atención institucional de Parachute S.A. "
            "Respondes directamente al usuario sobre detalles del evento, preguntas frecuentes y dudas generales. "
            "Usa la herramienta `buscar_faqs` y cita las FAQs oficiales.\n\n"
            "TRANSFERENCIA DE CONTROL (HANDOFFS):\n"
            "- Si el usuario desea consultar el clima, fechas o saber si es seguro saltar, "
            "transfiere el control inmediatamente a `agente_clima`.\n"
            "- Si el usuario desea reservar, consultar franjas o listar citas, "
            "transfiere el control inmediatamente a `agente_agenda`.\n"
            "Cuando la consulta sea de tu dominio, responde de forma amable y completa."
        ),
        tools=[tool_buscar_faqs],
        model=model,
    )

    # 2. Agente Clima y Seguridad Técnica
    agente_clima = Agent(
        name="agente_clima",
        instructions=(
            "Eres el Agente Oficial Meteorológico y de Seguridad de Parachute S.A. "
            "Hablas directamente con el usuario sobre condiciones climáticas y viabilidad de salto.\n"
            "Usa `resolver_fecha`, `consultar_clima` y `evaluar_condiciones`.\n"
            "Comunica con precisión: viento, ráfagas, lluvia, nubosidad, el veredicto (IDEAL, MARGINAL o PROHIBIDO) "
            "y menciona el `id_evidencia` obtenido.\n\n"
            "TRANSFERENCIA DE CONTROL (HANDOFFS):\n"
            "- Si las condiciones permiten saltar (IDEAL o MARGINAL) y el usuario desea proceder a reservar, "
            "transfiere el control a `agente_agenda` indicando la fecha y el `id_evidencia`.\n"
            "- Si el usuario hace preguntas generales o sobre el evento, transfiere a `agente_faqs`."
        ),
        tools=[tool_resolver_fecha, tool_consultar_clima, tool_evaluar_condiciones],
        model=model,
    )

    # 3. Agente Agenda y Reservas
    agente_agenda = Agent(
        name="agente_agenda",
        instructions=(
            "Eres el Agente de Calendarización y Reservas de Parachute S.A. "
            "Atiendes directamente al usuario para agendar citas de salto.\n"
            "Usa `consultar_disponibilidad`, `agendar_cita` y `listar_citas`.\n"
            "REGLA CRÍTICA: No puedes agendar sin un `id_evidencia` climático válido. "
            "Si no cuentas con el reporte meteorológico para la fecha solicitada, "
            "debes transferir inmediatamente el control a `agente_clima` para que evalúe las condiciones primero.\n\n"
            "TRANSFERENCIA DE CONTROL (HANDOFFS):\n"
            "- Si necesitas evaluación climática previa, transfiere a `agente_clima`.\n"
            "- Si el usuario tiene dudas institucionales o del evento, transfiere a `agente_faqs`."
        ),
        tools=[tool_consultar_disponibilidad, tool_agendar_cita, tool_listar_citas],
        model=model,
    )

    # Configuración de handoffs circulares/cruzados entre los pares
    agente_faqs.handoffs = [agente_clima, agente_agenda]
    agente_clima.handoffs = [agente_agenda, agente_faqs]
    agente_agenda.handoffs = [agente_clima, agente_faqs]

    return agente_faqs, agente_clima, agente_agenda


async def ejecutar_turno_descentralizado(
    agente_actual: Agent, entrada_usuario: str
) -> tuple[str, Agent, str | None]:
    """Ejecuta un turno en la arquitectura descentralizada con límite de handoffs.

    Retorna: (respuesta_llm, nuevo_agente_activo, comprobante)
    """
    limpiar_ultimo_comprobante()
    # Límite estricto de turnos/handoffs para evitar ciclos infinitos entre pares
    resultado = await Runner.run(agente_actual, entrada_usuario, max_turns=6)
    respuesta = resultado.final_output_as(str)
    nuevo_agente = resultado.last_agent or agente_actual
    comprobante = obtener_ultimo_comprobante()
    return respuesta, nuevo_agente, comprobante


def main() -> None:
    print("==========================================================")
    print(" Parachute S.A. - Chat Asistente (Arquitectura Descentralizada)")
    print("==========================================================")
    print("Escribe 'salir' para terminar la conversación.\n")

    agente_faqs, agente_clima, agente_agenda = construir_red_descentralizada()
    agente_activo = agente_faqs  # FAQ inicia por defecto

    while True:
        try:
            usuario = input(f"\nUsuario (agente actual: {agente_activo.name}): ").strip()
            if not usuario:
                continue
            if usuario.lower() in {"salir", "exit", "quit"}:
                print("Hasta pronto.")
                break

            print("\nAsistente (procesando red descentralizada)...")
            respuesta, agente_activo, comprobante = asyncio.run(
                ejecutar_turno_descentralizado(agente_activo, usuario)
            )
            print(f"\n[{agente_activo.name}]:\n{respuesta}\n")
            if comprobante:
                print(comprobante)
        except (KeyboardInterrupt, EOFError):
            print("\nSesión finalizada.")
            break
        except Exception as exc:
            print(f"\n[Error en turno]: {exc}")


if __name__ == "__main__":
    main()
