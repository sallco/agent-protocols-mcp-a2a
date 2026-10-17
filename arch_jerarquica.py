"""Arquitectura Jerárquica: Orquestador raíz con supervisores de dominio intermedios."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from agents import Agent, Runner
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


def construir_agentes_jerarquicos(model_name: str | None = None) -> Agent:
    """Construye la jerarquía de dos niveles: Raíz -> Supervisores -> Agentes Hoja."""
    model = create_model(model_name)

    # =========================================================================
    # DOMINIO 1: CONOCIMIENTO INSTITUCIONAL Y POLÍTICAS
    # =========================================================================

    agente_faqs = Agent(
        name="agente_faqs_hoja",
        instructions=(
            "Eres el especialista en preguntas frecuentes de Parachute S.A. "
            "Usa `buscar_faqs` para recuperar información oficial. Cita los IDs de FAQs. "
            "No inventes datos de políticas si no aparecen en los resultados."
        ),
        tools=[tool_buscar_faqs],
        model=model,
    )

    agente_politicas = Agent(
        name="agente_politicas_escalamiento",
        instructions=(
            "Eres el oficial de políticas y escalamiento de atención al cliente de Parachute S.A. "
            "Explicas restricciones institucionales, políticas de reembolso, requisitos de edad o peso, "
            "y orientas al usuario a soporte@parachutesa.gt cuando las FAQs sean insuficientes."
        ),
        tools=[],
        model=model,
    )

    supervisor_conocimiento = Agent(
        name="supervisor_conocimiento",
        instructions=(
            "Eres el Supervisor del Dominio de Conocimiento de Parachute S.A. "
            "Tu responsabilidad es coordinar al agente de FAQs y al agente de políticas. "
            "Atiende consultas generales del evento, dudas sobre Parachute S.A. y escalamiento de casos."
        ),
        tools=[
            agente_faqs.as_tool(
                tool_name="consultar_faqs_hoja",
                tool_description="Consulta el repositorio de preguntas frecuentes.",
            ),
            agente_politicas.as_tool(
                tool_name="consultar_politicas_escalamiento",
                tool_description="Consulta aclaraciones de políticas y canales de escalamiento.",
            ),
        ],
        model=model,
    )

    # =========================================================================
    # DOMINIO 2: OPERACIONES DE VUELO Y CALENDARIZACIÓN
    # =========================================================================

    agente_clima_hoja = Agent(
        name="agente_clima_hoja",
        instructions=(
            "Eres el técnico meteorológico. Resuelve la fecha con `resolver_fecha` y consulta "
            "el pronóstico oficial con `consultar_clima`. Retorna los datos y el `id_evidencia`."
        ),
        tools=[tool_resolver_fecha, tool_consultar_clima],
        model=model,
    )

    agente_evaluacion_hoja = Agent(
        name="agente_evaluacion_hoja",
        instructions=(
            "Eres el analista de seguridad de vuelo. Evalúa determinísticamente las condiciones "
            "utilizando `evaluar_condiciones` con el `id_evidencia`. Devuelve el veredicto (IDEAL, MARGINAL o PROHIBIDO)."
        ),
        tools=[tool_evaluar_condiciones],
        model=model,
    )

    agente_agenda_hoja = Agent(
        name="agente_agenda_hoja",
        instructions=(
            "Eres el encargado de calendarización. Consulta cupos con `consultar_disponibilidad` "
            "y registra reservas con `agendar_cita` pasando el `id_evidencia` previamente validado. "
            "También puedes listar citas con `listar_citas`."
        ),
        tools=[tool_consultar_disponibilidad, tool_agendar_cita, tool_listar_citas],
        model=model,
    )

    supervisor_operaciones = Agent(
        name="supervisor_operaciones",
        instructions=(
            "Eres el Supervisor de Operaciones de Vuelo y Agenda de Parachute S.A. "
            "IMPOSITOR DE FLUJO SECUENCIAL: Para agendar una cita debes coordinar estrictamente:\n"
            "1. Invocar a `obtener_pronostico_clima` para la fecha deseada.\n"
            "2. Invocar a `evaluar_seguridad_vuelo` con el `id_evidencia` resultante.\n"
            "3. Si el veredicto es PROHIBIDO, DETÉN la reserva e informa la prohibición.\n"
            "4. Si es IDEAL o MARGINAL, invoca a `gestionar_reserva` para completar la cita con el `id_evidencia`.\n"
            "Devuelve un resumen operativo completo al orquestador raíz."
        ),
        tools=[
            agente_clima_hoja.as_tool(
                tool_name="obtener_pronostico_clima",
                tool_description="Obtiene datos meteorológicos oficiales y su id_evidencia.",
            ),
            agente_evaluacion_hoja.as_tool(
                tool_name="evaluar_seguridad_vuelo",
                tool_description="Evalúa determinísticamente la seguridad de vuelo a partir de una evidencia.",
            ),
            agente_agenda_hoja.as_tool(
                tool_name="gestionar_reserva",
                tool_description="Revisa cupos y registra la cita en el sistema.",
            ),
        ],
        model=model,
    )

    # =========================================================================
    # NIVEL SUPERIOR: ORQUESTADOR RAÍZ
    # =========================================================================

    orquestador_raiz = Agent(
        name="orquestador_raiz",
        instructions=(
            "Eres el Asistente Director de Parachute S.A. en arquitectura JERÁRQUICA. "
            "Interactúas con el usuario y delegas en dos supervisores de alto nivel:\n"
            "- `supervisor_conocimiento`: Para responder dudas, preguntas frecuentes y políticas del evento.\n"
            "- `supervisor_operaciones`: Para todo lo referente a pronóstico climático, seguridad de vuelo y reservas de saltos.\n\n"
            "Sintetiza la respuesta final de forma cortés, precisa y en español. Si se confirmó una cita, incluye sus detalles."
        ),
        tools=[
            supervisor_conocimiento.as_tool(
                tool_name="supervisor_conocimiento",
                tool_description="Coordina el dominio de conocimiento, FAQs y políticas institucionales.",
            ),
            supervisor_operaciones.as_tool(
                tool_name="supervisor_operaciones",
                tool_description="Coordina el dominio de operaciones: clima, evaluación técnica y agendamiento de citas.",
            ),
        ],
        model=model,
    )

    return orquestador_raiz


async def ejecutar_turno_jerarquico(
    orquestador: Agent, entrada_usuario: str, sesion: Any = None
) -> tuple[str, str | None]:
    """Ejecuta un turno en la arquitectura jerárquica y retorna (respuesta_llm, comprobante)."""
    limpiar_ultimo_comprobante()
    resultado = await Runner.run(orquestador, entrada_usuario, max_turns=20)
    respuesta = resultado.final_output_as(str)
    comprobante = obtener_ultimo_comprobante()
    return respuesta, comprobante


def main() -> None:
    print("=========================================================")
    print(" Parachute S.A. - Chat Asistente (Arquitectura Jerárquica)")
    print("=========================================================")
    print("Escribe 'salir' para terminar la conversación.\n")

    orquestador = construir_agentes_jerarquicos()

    while True:
        try:
            usuario = input("\nUsuario: ").strip()
            if not usuario:
                continue
            if usuario.lower() in {"salir", "exit", "quit"}:
                print("Hasta pronto.")
                break

            print("\nAsistente (procesando jerarquía)...")
            respuesta, comprobante = asyncio.run(ejecutar_turno_jerarquico(orquestador, usuario))
            print(f"\nAsistente:\n{respuesta}\n")
            if comprobante:
                print(comprobante)
        except (KeyboardInterrupt, EOFError):
            print("\nSesión finalizada.")
            break
        except Exception as exc:
            print(f"\n[Error en turno]: {exc}")


if __name__ == "__main__":
    main()
