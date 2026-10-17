"""Punto de entrada unificado para carga del corpus y ejecución de las tres arquitecturas."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

import arch_centralizada
import arch_descentralizada
import arch_jerarquica
import load_faqs
import smoke_test


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sistema Multiagente de FAQs, Meteorología y Calendarización para Parachute S.A."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    # 1. Comando load (ingesta de FAQs)
    commands.add_parser("load", help="Genera embeddings y carga el corpus en PostgreSQL.")

    # 2. Comando smoke-test (validación de modelos y herramientas)
    commands.add_parser("smoke-test", help="Ejecuta la prueba de humo del proveedor NVIDIA con fallback.")

    # 3. Comando benchmark (evaluación comparativa)
    commands.add_parser("benchmark", help="Ejecuta la matriz comparativa de rendimiento entre las 3 arquitecturas.")

    # 4. Comando chat (conversación interactiva en terminal)
    chat_parser = commands.add_parser("chat", help="Inicia el agente conversacional interactivo.")

    chat_parser.add_argument(
        "--arquitectura",
        choices=["centralizada", "jerarquica", "descentralizada"],
        default="centralizada",
        help="Arquitectura de orquestación multiagente a ejecutar (por defecto: centralizada).",
    )
    chat_parser.add_argument(
        "--modelo",
        type=str,
        default=None,
        help="Modelo LLM de NVIDIA NIM a utilizar (anula la configuración de entorno).",
    )
    chat_parser.add_argument(
        "--mock-clima",
        choices=["ideal", "marginal", "prohibido"],
        default=None,
        help="Modo de simulación meteorológica para pruebas y demostraciones reproducibles.",
    )

    parsed_arguments, remaining_arguments = parser.parse_known_args(arguments)
    if parsed_arguments.command == "load":
        parsed_arguments.loader_arguments = remaining_arguments
    elif remaining_arguments:
        parser.error(f"Argumentos no reconocidos: {' '.join(remaining_arguments)}")

    return parsed_arguments


def main(arguments: Sequence[str] | None = None) -> None:
    parsed_arguments = parse_arguments(arguments)

    if parsed_arguments.command == "load":
        load_faqs.main(parsed_arguments.loader_arguments)
    elif parsed_arguments.command == "smoke-test":
        smoke_test.main()
    elif parsed_arguments.command == "benchmark":
        import benchmark_arquitecturas
        benchmark_arquitecturas.main()
    elif parsed_arguments.command == "chat":

        arq = parsed_arguments.arquitectura
        if arq == "centralizada":
            arch_centralizada.main()
        elif arq == "jerarquica":
            arch_jerarquica.main()
        elif arq == "descentralizada":
            arch_descentralizada.main()


if __name__ == "__main__":
    main()
