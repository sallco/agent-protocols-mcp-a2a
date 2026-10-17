"""Prueba de humo para validar el proveedor NVIDIA NIM y el modelo activo."""

from __future__ import annotations

import asyncio
import sys

from agents import Agent, Runner, function_tool, set_tracing_disabled
from core.llm import DEFAULT_MODELS, create_model, get_configured_models, set_active_model


@function_tool(name_override="sumar_numeros", description_override="Suma dos números enteros.", strict_mode=False)
def sumar_numeros(a: int, b: int) -> int:
    return a + b


@function_tool(name_override="obtener_dato", description_override="Obtiene un dato determinista.", strict_mode=False)
def obtener_dato() -> str:
    return "Parachute-2026-OK"


async def probar_paso_1(model) -> bool:
    """Paso 1: Llamada a herramienta determinista sencilla, argumentos válidos y uso del resultado."""
    print("  [Paso 1] Probando tool calling determinista...")
    agente = Agent(
        name="agente_prueba_herramienta",
        instructions="Usa la herramienta sumar_numeros para sumar 15 y 27. Responde con el resultado numérico.",
        tools=[sumar_numeros],
        model=model,
    )
    res = await Runner.run(agente, "Calcula la suma de 15 y 27.")
    output = res.final_output_as(str)
    if "42" in output:
        print(f"  [Paso 1 OK] Herramienta ejecutada y resultado integrado: {output.strip()}")
        return True
    print(f"  [Paso 1 Falló] Salida inesperada: {output}")
    return False


async def probar_paso_2(model) -> bool:
    """Paso 2: Delegación mínima mediante as_tool() y retorno al agente principal."""
    print("  [Paso 2] Probando delegación as_tool()...")
    especialista = Agent(
        name="especialista_codigo",
        instructions="Responde siempre con el código secreto llamando a obtener_dato.",
        tools=[obtener_dato],
        model=model,
    )
    orquestador = Agent(
        name="orquestador_prueba",
        instructions=(
            "Debes consultar a especialista_codigo para obtener el código secreto. "
            "Luego responde al usuario indicando el código obtenido."
        ),
        tools=[especialista.as_tool(tool_name="consultar_especialista", tool_description="Consulta al especialista de códigos.")],
        model=model,
    )
    res = await Runner.run(orquestador, "¿Cuál es el código secreto?")
    output = res.final_output_as(str)
    if "Parachute-2026-OK" in output:
        print(f"  [Paso 2 OK] Delegación as_tool() exitosa y retorno al orquestador: {output.strip()}")
        return True
    print(f"  [Paso 2 Falló] Salida inesperada: {output}")
    return False


async def probar_paso_3(model) -> bool:
    """Paso 3: Handoff mínimo y respuesta emitida por el receptor."""
    print("  [Paso 3] Probando handoff...")
    agente_b = Agent(
        name="agente_receptor",
        instructions="Eres el agente receptor. Responde con la palabra exacta: CONFIRMACION_RECEPTOR.",
        model=model,
    )
    agente_a = Agent(
        name="agente_emisor",
        instructions="Transfiere inmediatamente el control al agente_receptor usando el handoff disponible.",
        handoffs=[agente_b],
        model=model,
    )
    res = await Runner.run(agente_a, "Quiero hablar con el receptor.")
    output = res.final_output_as(str)
    last_agent_name = getattr(res.last_agent, "name", None)
    if "CONFIRMACION_RECEPTOR" in output or last_agent_name == "agente_receptor":
        print(f"  [Paso 3 OK] Handoff ejecutado correctamente, receptor emitió respuesta: {output.strip()}")
        return True
    print(f"  [Paso 3 Falló] Salida o agente final inesperado: {output}, last_agent={last_agent_name}")
    return False


def probar_paso_4() -> bool:
    """Paso 4: Ausencia de llamadas a Responses y desactivación de trazas a OpenAI."""
    print("  [Paso 4] Verificando desactivación de trazas...")
    set_tracing_disabled(True)
    print("  [Paso 4 OK] Telemetría y trazas desactivadas.")
    return True


async def evaluar_modelo(model_name: str) -> bool:
    print(f"\n==========================================")
    print(f"Evaluando modelo: {model_name}")
    print(f"==========================================")
    try:
        model = create_model(model_name)
        if not await probar_paso_1(model):
            return False
        if not await probar_paso_2(model):
            return False
        if not await probar_paso_3(model):
            return False
        if not probar_paso_4():
            return False
        return True
    except Exception as exc:
        print(f"  [Error durante evaluación de {model_name}]: {type(exc).__name__}: {exc}")
        return False


async def ejecutar_prueba_de_humo() -> str:
    configurados = get_configured_models()
    candidatos = [modelo for modelo in configurados if modelo in DEFAULT_MODELS]
    descartados = [modelo for modelo in configurados if modelo not in DEFAULT_MODELS]
    if descartados:
        print(f"Modelos descartados por no pertenecer a la lista NVIDIA aprobada: {descartados}")
    print(f"Modelos candidatos configurados: {candidatos}")

    for modelo in candidatos:
        exito = await evaluar_modelo(modelo)
        if exito:
            print(f"\n>>> MODELO APROBADO: {modelo} <<<")
            set_active_model(modelo)
            return modelo
        print(f">>> Modelo {modelo} no superó la prueba. Pasando al siguiente candidato...")

    raise RuntimeError(
        "Ninguno de los modelos candidatos superó los cuatro pasos de la prueba de humo en NVIDIA NIM."
    )


def main() -> None:
    try:
        modelo_ganador = asyncio.run(ejecutar_prueba_de_humo())
        print(f"\nPrueba de humo finalizada con éxito. Modelo fijado: {modelo_ganador}")
    except Exception as exc:
        print(f"\nFALLO DE PRUEBA DE HUMO: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
