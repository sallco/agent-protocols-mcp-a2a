"""Terminal remota: chat, recursos y fallos, sin servicios de negocio locales."""

import asyncio
import subprocess
import sys
from unittest.mock import AsyncMock
from uuid import UUID

from a2a.helpers import new_text_message
from a2a.types import StreamResponse, Task, TaskState, TaskStatus
import httpx
import pytest

import a2a_server
from mcp_server import crear_servidor_mcp
import terminal
from tests.http_server import servidor_http
from tests.test_a2a_server import mas_simulado, resultado


def test_chat_http_con_historial_nuevo_comprobante_y_recursos(mas_simulado, monkeypatch, capsys):
    ejecutar, _ = mas_simulado
    ejecutar.side_effect = lambda agente, entrada, **kwargs: (
        resultado(entrada, "Respuesta remota"),
        "COMPROBANTE EXACTO\nCódigo: demo-123" if entrada[-1]["content"] == "Reserva" else None,
    )
    entradas = iter([
        "", "/ayuda", "/desconocido", "Reserva", "/recursos", "/recurso",
        "/recursos argumento", "/recurso parachute://faqs/corpus",
        "/recurso parachute://inexistente", "Gracias", "/nuevo", "Hola", "/salir",
    ])
    monkeypatch.setattr("builtins.input", lambda _: next(entradas))
    card = a2a_server.crear_agent_card("http://127.0.0.1:8000")
    monkeypatch.setattr(a2a_server, "crear_agent_card", lambda url: card)
    crear_cliente = AsyncMock(wraps=terminal.create_client)
    monkeypatch.setattr(terminal, "create_client", crear_cliente)

    async def escenario():
        mcp = crear_servidor_mcp()
        async with servidor_http(mcp.streamable_http_app(json_response=True, stateless_http=True)) as url_mcp:
            async with servidor_http(a2a_server.crear_aplicacion_a2a()) as url_a2a:
                card.supported_interfaces[0].url = url_a2a
                await terminal.ejecutar_chat(a2a_url=url_a2a, mcp_url=url_mcp + "/mcp")

    asyncio.run(escenario())
    salida = capsys.readouterr().out
    assert "Cliente A2A conectado" in salida
    assert salida.count("Estado: COMPLETED") == 3
    assert salida.count("COMPROBANTE EXACTO\nCódigo: demo-123") == 1
    assert "parachute://faqs/corpus" in salida
    assert "ID: FAQ-001" in salida and "ID: FAQ-120" in salida
    assert "Uso: /recursos o /recurso URI" in salida
    assert "No se pudo consultar el recurso MCP" in salida
    assert "Comando no reconocido" in salida
    assert "Nueva conversación:" in salida
    assert ejecutar.await_count == 3
    assert len(ejecutar.call_args_list[1].args[1]) == 3
    assert ejecutar.call_args_list[2].args[1] == [{"role": "user", "content": "Hola"}]
    config = crear_cliente.call_args.args[1]
    assert config.httpx_client.is_closed
    assert not config.streaming


def test_error_a2a_no_reintenta_y_conserva_contexto(monkeypatch, capsys):
    solicitudes = []

    async def enviar(request):
        solicitudes.append(request)
        if len(solicitudes) == 1:
            raise httpx.ReadTimeout("detalle privado")
        yield StreamResponse(task=Task(
            id="tarea-recuperada", context_id=request.message.context_id,
            status=TaskStatus(state=TaskState.TASK_STATE_FAILED, message=new_text_message("Fallo operativo")),
        ))

    cliente = AsyncMock()
    cliente.send_message = enviar
    cliente.__aenter__.return_value = cliente
    monkeypatch.setattr(terminal, "create_client", AsyncMock(return_value=cliente))
    entradas = iter(["Reserva", "Consulta mis citas", "salir"])
    monkeypatch.setattr("builtins.input", lambda _: next(entradas))

    asyncio.run(terminal.ejecutar_chat())

    assert len(solicitudes) == 2
    assert solicitudes[0].message.context_id == solicitudes[1].message.context_id
    UUID(solicitudes[0].message.context_id)
    assert solicitudes[0].message.message_id != solicitudes[1].message.message_id
    assert all(not request.message.task_id for request in solicitudes)
    salida = capsys.readouterr().out
    assert "No se reintentó" in salida and "incierto" in salida
    assert "Estado: FAILED" in salida and "Fallo operativo" in salida
    assert "detalle privado" not in salida
    cliente.__aexit__.assert_awaited_once()


def test_eof_cierra_cliente(monkeypatch):
    cliente = AsyncMock()
    cliente.__aenter__.return_value = cliente
    monkeypatch.setattr(terminal, "create_client", AsyncMock(return_value=cliente))

    def eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    asyncio.run(terminal.ejecutar_chat())
    cliente.__aexit__.assert_awaited_once()
    cliente.send_message.assert_not_called()


def test_fallo_inicio_sale_sin_exponer_detalles(monkeypatch, capsys):
    monkeypatch.setattr(terminal, "create_client", AsyncMock(side_effect=RuntimeError("dato privado")))
    with pytest.raises(SystemExit) as error:
        terminal.main()
    assert error.value.code == 1
    salida = capsys.readouterr().out
    assert "No se pudo iniciar el cliente A2A" in salida
    assert "dato privado" not in salida


def test_recurso_sin_a2a_no_construye_agentes(monkeypatch, capsys):
    monkeypatch.setattr(terminal, "create_client", AsyncMock(side_effect=AssertionError("No usar A2A")))

    async def escenario():
        mcp = crear_servidor_mcp()
        async with servidor_http(mcp.streamable_http_app(json_response=True, stateless_http=True)) as url:
            await terminal.mostrar_recursos("/recursos", url + "/mcp")

    asyncio.run(escenario())
    assert "parachute://faqs/corpus" in capsys.readouterr().out


def test_importar_cliente_no_carga_mas_o_servicios_locales():
    codigo = (
        "import sys, terminal; "
        "assert not {'core.tools', 'core.config', 'arch_centralizada', 'mas_mcp', "
        "'core.faq_store', 'core.scheduling'}.intersection(sys.modules)"
    )
    proceso = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True)
    assert proceso.returncode == 0, proceso.stderr
