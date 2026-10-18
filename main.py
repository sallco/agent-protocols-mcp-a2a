"""Punto de entrada para los servidores, el cliente remoto y las arquitecturas locales."""

from __future__ import annotations

import argparse
import importlib
from datetime import date
from typing import Sequence


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

    remote_chat = commands.add_parser("chat", help="Inicia el cliente de terminal A2A.")
    remote_chat.add_argument("--a2a-url", default="http://127.0.0.1:8000",
                             help="URL del servidor A2A para descubrir su Agent Card.")
    remote_chat.add_argument("--mcp-url", default="http://127.0.0.1:8001/mcp",
                             help="URL MCP para los comandos explícitos de recursos.")

    chat_parser = commands.add_parser(
        "chat-local", help="Inicia el agente conversacional local."
    )

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
    mcp_parser = commands.add_parser("mcp-server", help="Inicia el servidor MCP Streamable HTTP.")
    mcp_parser.add_argument("--puerto", type=int, default=8001, help="Puerto local del servidor MCP.")
    a2a_parser = commands.add_parser("a2a-server", help="Inicia el servidor A2A del MAS centralizado.")
    a2a_parser.add_argument("--puerto", type=int, default=8000, help="Puerto local del servidor A2A.")
    a2a_parser.add_argument("--mcp-url", default="http://127.0.0.1:8001/mcp",
                            help="URL del servidor MCP de herramientas.")
    a2a_parser.add_argument("--modelo", default=None, help="Modelo LLM de NVIDIA NIM.")
    for scenario_parser in (chat_parser, mcp_parser):
        scenario_parser.add_argument(
            "--mock-clima",
            choices=["ideal", "marginal", "prohibido"],
            default=None,
            help="Modo de simulación meteorológica para pruebas y demostraciones reproducibles.",
        )
        scenario_parser.add_argument(
            "--fecha-base", type=date.fromisoformat, default=None,
            help="Fecha de referencia YYYY-MM-DD para una demostración con --mock-clima.",
        )

    parsed_arguments, remaining_arguments = parser.parse_known_args(arguments)
    if parsed_arguments.command == "load":
        parsed_arguments.loader_arguments = remaining_arguments
    elif remaining_arguments:
        parser.error(f"Argumentos no reconocidos: {' '.join(remaining_arguments)}")
    if parsed_arguments.command in {"chat-local", "mcp-server"}:
        if parsed_arguments.fecha_base is not None and parsed_arguments.mock_clima is None:
            parser.error("--fecha-base requiere --mock-clima.")
    if parsed_arguments.command in {"mcp-server", "a2a-server"} and not 1 <= parsed_arguments.puerto <= 65535:
        parser.error("--puerto debe estar entre 1 y 65535.")

    return parsed_arguments


def main(arguments: Sequence[str] | None = None) -> None:
    parsed_arguments = parse_arguments(arguments)

    if parsed_arguments.command == "load":
        import load_faqs
        load_faqs.main(parsed_arguments.loader_arguments)
    elif parsed_arguments.command == "smoke-test":
        import smoke_test
        smoke_test.main()
    elif parsed_arguments.command == "benchmark":
        import benchmark_arquitecturas
        benchmark_arquitecturas.main()
    elif parsed_arguments.command == "mcp-server":
        import mcp_server
        mcp_server.main(
            mock_clima=parsed_arguments.mock_clima,
            fecha_base=(parsed_arguments.fecha_base.isoformat()
                        if parsed_arguments.fecha_base is not None else None),
            puerto=parsed_arguments.puerto,
        )
    elif parsed_arguments.command == "a2a-server":
        import a2a_server
        a2a_server.main(
            puerto=parsed_arguments.puerto, mcp_url=parsed_arguments.mcp_url,
            model_name=parsed_arguments.modelo,
        )
    elif parsed_arguments.command == "chat":
        import terminal
        terminal.main(a2a_url=parsed_arguments.a2a_url, mcp_url=parsed_arguments.mcp_url)
    elif parsed_arguments.command == "chat-local":
        from core.tools import configurar_herramientas

        configurar_herramientas(
            mock_clima=parsed_arguments.mock_clima,
            fecha_base=(parsed_arguments.fecha_base.isoformat()
                        if parsed_arguments.fecha_base is not None else None),
        )
        architecture = importlib.import_module("arch_" + parsed_arguments.arquitectura)
        architecture.main(model_name=parsed_arguments.modelo)


if __name__ == "__main__":
    main()
