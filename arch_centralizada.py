"""Arquitectura Centralizada: Orquestador único con agentes especialistas vía as_tool()."""

from __future__ import annotations

import asyncio
import sys

from agents import Agent, Runner
from core.llm import create_model
from core.tools import (
    iniciar_traza_herramientas,
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


def construir_agentes_centralizados(model_name: str | None = None) -> Agent:
    """Construye la jerarquía centralizada de agentes conectada al modelo LLM."""
    model = create_model(model_name)

    # 1. Especialista en FAQs y conocimiento institucional
    agente_faqs = Agent(
        name="especialista_faqs",
        instructions=(
            "Eres el especialista en conocimiento institucional y preguntas frecuentes de Parachute S.A. "
            "Tu única tarea es responder consultas sobre el evento nacional de paracaidismo Guatemala 2026. "
            "Usa la herramienta `buscar_faqs` una sola vez con la consulta del usuario. "
            "Responde de forma concisa y directa citando los IDs de las FAQs relevantes (ej. FAQ-012). "
            "Si la información es insuficiente, no existe o no figura en las respuestas, indícalo claramente "
            "expresando que no dispones de la información y deriva a soporte@parachutesa.gt sin inventar datos "
            "ni realizar búsquedas adicionales. "
            "No definas umbrales de viento u operación técnica: eso corresponde a seguridad."
        ),
        tools=[tool_buscar_faqs],
        model=model,
    )

    # 2. Especialista en Clima y Seguridad de Salto
    agente_clima = Agent(
        name="especialista_clima_seguridad",
        instructions=(
            "Eres el especialista meteorológico y oficial de seguridad de Parachute S.A. "
            "Tu función es consultar el pronóstico oficial de Open-Meteo y emitir el veredicto técnico de salto. "
            "Pasos obligatorios:\n"
            "1. Valida y normaliza la fecha con `resolver_fecha`.\n"
            "2. Consulta el clima con `consultar_clima` usando la fecha en formato YYYY-MM-DD.\n"
            "3. Evalúa las condiciones con `evaluar_condiciones` usando el `id_evidencia` obtenido.\n"
            "Reporta de forma concisa: temperatura, viento, ráfagas, lluvia, cobertura de nubes, veredicto (IDEAL, MARGINAL o PROHIBIDO) "
            "y el `id_evidencia` exacto para reservas."
        ),
        tools=[tool_resolver_fecha, tool_consultar_clima, tool_evaluar_condiciones],
        model=model,
    )

    # 3. Especialista en Agenda y Reservas
    agente_agenda = Agent(
        name="especialista_agenda",
        instructions=(
            "Eres el encargado de calendarización y reservas de Parachute S.A. "
            "Para agendar una cita necesitas: nombre completo, fecha ISO (YYYY-MM-DD), hora (franjas 08:00 a 15:00) "
            "y un `id_evidencia` meteorológico válido obtenido previamente.\n"
            "Usa `consultar_disponibilidad` para ver los cupos libres.\n"
            "Usa `agendar_cita` para registrar la cita formalmente. Si las condiciones están PROHIBIDAS, "
            "el sistema rechazará la cita determinísticamente; si están MARGINAL, incluye la advertencia de tándem experimentado."
        ),
        tools=[tool_consultar_disponibilidad, tool_agendar_cita, tool_listar_citas],
        model=model,
    )

    # 4. Orquestador Central (único punto de contacto con el usuario)
    orquestador = Agent(
        name="orquestador_central",
        instructions=(
            "Eres el Asistente Principal de Parachute S.A. en arquitectura CENTRALIZADA. "
            "Conversas directamente con el usuario y coordinas a tres especialistas mediante herramientas:\n"
            "- `consultar_faqs`: Para dudas generales, requisitos y preguntas frecuentes del evento.\n"
            "- `consultar_clima_seguridad`: Para verificar el clima, fechas y veredictos de seguridad.\n"
            "- `gestionar_agenda`: Para revisar cupos disponibles y agendar reservas.\n\n"
            "Sé conciso, directo y profesional. Responde sin rodeos ni textos de relleno innecesarios.\n"
            "REGLAS OPERATIVAS:\n"
            "1. Para agendar una cita, PRIMERO debes consultar al especialista de clima para obtener la evaluación y su `id_evidencia`.\n"
            "2. Si el veredicto es PROHIBIDO, no procedas con la reserva; indica con claridad que la reserva queda rechazada o denegada (no puedo proceder con la reserva) por motivos de seguridad y explica amablemente las condiciones meteorológicas.\n"
            "3. Si el veredicto es MARGINAL o IDEAL, procede a agendar con el especialista de agenda pasando el `id_evidencia`.\n"
            "4. Integra la información de los especialistas en una única respuesta en español, clara, concisa y profesional."
        ),
        tools=[
            agente_faqs.as_tool(
                tool_name="consultar_faqs",
                tool_description="Consulta dudas institucionales y preguntas frecuentes de Parachute S.A.",
            ),
            agente_clima.as_tool(
                tool_name="consultar_clima_seguridad",
                tool_description="Consulta pronóstico meteorológico oficial, fechas y veredictos de salto.",
            ),
            agente_agenda.as_tool(
                tool_name="gestionar_agenda",
                tool_description="Verifica disponibilidad de franjas y agenda citas de salto con evidencia.",
            ),
        ],
        model=model,
    )

    return orquestador


async def ejecutar_turno_centralizado(
    orquestador: Agent, entrada_usuario: str, sesion: Any = None
) -> tuple[str, str | None]:
    """Ejecuta un turno en la arquitectura centralizada y retorna (respuesta_llm, comprobante)."""
    limpiar_ultimo_comprobante()
    iniciar_traza_herramientas()
    try:
        resultado = await Runner.run(orquestador, entrada_usuario, max_turns=20)
        respuesta = resultado.final_output_as(str)
        comprobante = obtener_ultimo_comprobante()
        return respuesta, comprobante
    finally:
        client = getattr(getattr(orquestador, "model", None), "openai_client", None)
        if client and hasattr(client, "close"):
            await client.close()



def main() -> None:
    print("=========================================================")
    print(" Parachute S.A. - Chat Asistente (Arquitectura Centralizada)")
    print("=========================================================")
    print("Escribe 'salir' para terminar la conversación.\n")

    orquestador = construir_agentes_centralizados()

    while True:
        try:
            usuario = input("\nUsuario: ").strip()
            if not usuario:
                continue
            if usuario.lower() in {"salir", "exit", "quit"}:
                print("Hasta pronto.")
                break

            print("\nAsistente (procesando)...")
            respuesta, comprobante = asyncio.run(ejecutar_turno_centralizado(orquestador, usuario))
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
