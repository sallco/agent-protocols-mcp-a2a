"""Cliente y servidor A2A oficiales sobre HTTP real, sin inferencias externas."""

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import GetTaskRequest, Role, SendMessageRequest, TaskState
from agents import RunContextWrapper
from agents.testing import ModelStep, ScriptedModel, assistant_message
import httpx
import pytest

import a2a_server
import mas_mcp
from mcp_server import crear_servidor_mcp
from tests.http_server import servidor_http
from tests.test_mas_mcp import instalar_modelo, llamada, ultima_salida


@asynccontextmanager
async def cliente_a2a(url):
    async with httpx.AsyncClient(timeout=20) as http:
        card = await A2ACardResolver(http, url).get_agent_card()
        # El puerto efímero de pruebas se conoce después de construir la aplicación.
        card.supported_interfaces[0].url = url
        async with await create_client(card, ClientConfig(streaming=False, httpx_client=http)) as client:
            yield client


async def enviar(client, texto, contexto=None):
    request = SendMessageRequest(message=new_text_message(
        texto, role=Role.ROLE_USER, context_id=contexto,
    ))
    respuestas = [evento async for evento in client.send_message(request)]
    assert len(respuestas) == 1
    assert respuestas[0].HasField("task")
    return respuestas[0].task


def resultado(entrada, texto):
    return SimpleNamespace(
        final_output_as=lambda *args, **kwargs: texto,
        to_input_list=lambda: entrada + [{"role": "assistant", "content": texto}],
    )


@pytest.fixture
def mas_simulado(monkeypatch):
    ciclo = []

    @asynccontextmanager
    async def conectar(**kwargs):
        ciclo.append(("abierto", kwargs))
        try:
            yield object()
        finally:
            ciclo.append(("cerrado", kwargs))

    ejecutar = AsyncMock(side_effect=lambda agente, entrada, **kwargs: (
        resultado(entrada, "Respuesta de prueba"), None,
    ))
    monkeypatch.setattr(a2a_server, "conectar_mas_mcp", conectar)
    monkeypatch.setattr(a2a_server, "ejecutar_turno_mcp", ejecutar)
    return ejecutar, ciclo


def test_card_historial_aislado_tareas_y_cierre(mas_simulado, caplog):
    ejecutar, ciclo = mas_simulado

    async def escenario():
        app = a2a_server.crear_aplicacion_a2a(mcp_url="http://127.0.0.1:8123/mcp", model_name="modelo")
        async with servidor_http(app) as url:
            async with httpx.AsyncClient() as http:
                card = await A2ACardResolver(http, url).get_agent_card()
                assert card.name == "Asistente Parachute S.A."
                assert {skill.id for skill in card.skills} == {"preguntas_frecuentes", "clima_seguridad", "reservas"}
                assert card.default_input_modes == ["text/plain"]
                assert card.default_output_modes == ["text/plain"]
                assert not card.capabilities.streaming
                assert card.supported_interfaces[0].protocol_binding == "JSONRPC"
                assert card.supported_interfaces[0].protocol_version == "1.0"
            async with cliente_a2a(url) as client:
                primero = await enviar(client, "Hola")
                segundo = await enviar(client, "Continúa", primero.context_id)
                nuevo = await enviar(client, "Otra conversación")
                assert primero.status.state == segundo.status.state == nuevo.status.state == TaskState.TASK_STATE_COMPLETED
                assert primero.id != segundo.id
                assert primero.context_id == segundo.context_id != nuevo.context_id
                assert segundo.status.message.parts[0].text == "Respuesta de prueba"
                assert not segundo.artifacts
                guardada = await client.get_task(GetTaskRequest(id=primero.id))
                assert guardada.id == primero.id
                assert guardada.status.state == TaskState.TASK_STATE_COMPLETED
        entradas = [call.args[1] for call in ejecutar.call_args_list]
        assert entradas[0] == [{"role": "user", "content": "Hola"}]
        assert entradas[1] == entradas[0] + [
            {"role": "assistant", "content": "Respuesta de prueba"},
            {"role": "user", "content": "Continúa"},
        ]
        assert entradas[2] == [{"role": "user", "content": "Otra conversación"}]
        solicitudes = [call.kwargs["solicitud_id"] for call in ejecutar.call_args_list]
        assert len(set(solicitudes)) == 3
        assert all(str(UUID(solicitud)) == solicitud for solicitud in solicitudes)

    caplog.set_level(logging.INFO, logger="parachute.a2a")
    asyncio.run(escenario())
    assert ciclo == [
        (estado, {"mcp_url": "http://127.0.0.1:8123/mcp", "model_name": "modelo"})
        for estado in ("abierto", "cerrado")
    ]
    logs = [r.message for r in caplog.records if r.name == "parachute.a2a"]
    assert sum("estado=completada" in log for log in logs) == 3
    assert not any("Otra conversación" in log for log in logs)


def test_turnos_simultaneos_se_serializan_solo_en_su_contexto(mas_simulado):
    ejecutar, _ = mas_simulado

    async def escenario():
        entro = asyncio.Event()
        liberar = asyncio.Event()
        entradas = []

        async def turno(agente, entrada, **kwargs):
            texto = entrada[-1]["content"]
            entradas.append(entrada)
            if texto == "primero":
                entro.set()
                await liberar.wait()
            return resultado(entrada, "respuesta " + texto), None

        ejecutar.side_effect = turno
        async with servidor_http(a2a_server.crear_aplicacion_a2a()) as url:
            async with cliente_a2a(url) as client:
                primero = asyncio.create_task(enviar(client, "primero", "misma-conversacion"))
                await asyncio.wait_for(entro.wait(), 5)
                segundo = asyncio.create_task(enviar(client, "segundo", "misma-conversacion"))
                try:
                    independiente = await asyncio.wait_for(enviar(client, "otro", "otra-conversacion"), 5)
                    assert independiente.status.state == TaskState.TASK_STATE_COMPLETED
                    assert [entrada[-1]["content"] for entrada in entradas] == ["primero", "otro"]
                finally:
                    liberar.set()
                await asyncio.gather(primero, segundo)
                assert entradas[-1] == [
                    {"role": "user", "content": "primero"},
                    {"role": "assistant", "content": "respuesta primero"},
                    {"role": "user", "content": "segundo"},
                ]

    asyncio.run(escenario())


def test_error_no_reintenta_ni_guarda_historial_o_expone_detalles(mas_simulado, caplog):
    ejecutar, _ = mas_simulado
    ejecutar.side_effect = RuntimeError("detalle interno privado")

    async def escenario():
        async with servidor_http(a2a_server.crear_aplicacion_a2a()) as url:
            async with cliente_a2a(url) as client:
                fallida = await enviar(client, "Reserva")
                assert fallida.status.state == TaskState.TASK_STATE_FAILED
                assert "incierto" in fallida.status.message.parts[0].text
                assert "privado" not in str(fallida)
                assert not fallida.artifacts
                ejecutar.assert_awaited_once()
                ejecutar.side_effect = lambda agente, entrada, **kwargs: (resultado(entrada, "Recuperado"), None)
                recuperada = await enviar(client, "Consulta mis citas", fallida.context_id)
                assert recuperada.status.state == TaskState.TASK_STATE_COMPLETED
                assert ejecutar.call_args.args[1] == [{"role": "user", "content": "Consulta mis citas"}]

    caplog.set_level(logging.INFO, logger="parachute.a2a")
    asyncio.run(escenario())
    assert "error=RuntimeError" in caplog.text
    assert "detalle interno privado" not in caplog.text


@pytest.mark.parametrize("mensaje", [
    {"role": "ROLE_USER", "parts": [{"text": "   "}]},
    {"role": "ROLE_USER", "parts": [{"text": ""}]},
    {"role": "ROLE_USER", "parts": []},
    {"role": "ROLE_AGENT", "parts": [{"text": "Hola"}]},
    {"role": "ROLE_USER", "parts": [{"raw": "YWJj", "mediaType": "image/png"}]},
])
def test_rechaza_entradas_invalidas_sin_invocar_mas(mas_simulado, mensaje):
    ejecutar, _ = mas_simulado

    async def escenario():
        async with servidor_http(a2a_server.crear_aplicacion_a2a()) as url:
            async with httpx.AsyncClient() as http:
                respuesta = await http.post(url, json={
                    "jsonrpc": "2.0", "id": "entrada-invalida", "method": "SendMessage",
                    "params": {"message": {"messageId": "entrada", **mensaje}},
                })
                assert "error" in respuesta.json()
                ejecutar.assert_not_awaited()

    asyncio.run(escenario())


def test_comprobante_exacto_mas_mcp_y_postgres(agenda_aislada, instalar_modelo, caplog):
    evidencia = {}

    def reservar(call):
        evidencia.update(ultima_salida(call))
        return llamada("gestionar_agenda", {"input": json.dumps(evidencia)}, "agenda")

    modelo = ScriptedModel([
        llamada("consultar_clima_seguridad", {"input": "Clima 2026-09-29"}, "clima"),
        llamada("consultar_clima", {"fecha_iso": "2026-09-29"}, "pronostico"),
        ModelStep.respond(lambda call: [assistant_message(json.dumps(ultima_salida(call)))]),
        ModelStep.respond(reservar),
        ModelStep.respond(lambda call: llamada("agendar_cita", {
            "nombre": "Cliente A2A", "fecha_iso": "2026-09-29", "hora": "10:00",
            "id_evidencia": evidencia["id_evidencia"],
        }, "reserva")),
        [assistant_message("Reserva registrada.")],
        [assistant_message("Tu reserva está lista.")],
        [assistant_message("De nada.", item_id="siguiente")],
    ])
    clientes, conexiones = instalar_modelo(modelo)

    async def escenario():
        mcp = crear_servidor_mcp(mock_clima="ideal", fecha_base="2026-09-18")
        async with servidor_http(mcp.streamable_http_app(json_response=True, stateless_http=True)) as url_mcp:
            app = a2a_server.crear_aplicacion_a2a(mcp_url=url_mcp + "/mcp")
            async with servidor_http(app) as url:
                async with cliente_a2a(url) as client:
                    tarea = await enviar(client, "Reserva para el 29 de septiembre")
                    assert tarea.status.state == TaskState.TASK_STATE_COMPLETED
                    assert tarea.status.message.parts[0].text == "Tu reserva está lista."
                    assert len(tarea.artifacts) == 1
                    assert tarea.artifacts[0].name == "comprobante"
                    assert tarea.artifacts[0].parts[0].text == ultima_salida(modelo.calls[5])["comprobante"]
                    siguiente = await enviar(client, "Gracias", tarea.context_id)
                    assert not siguiente.artifacts
            assert conexiones[0].session is None
            assert clientes[0].is_closed()

    caplog.set_level(logging.INFO)
    asyncio.run(escenario())
    modelo.assert_complete()
    inicio = next(r.message for r in caplog.records if r.name == "parachute.a2a" and r.message.startswith("inicio"))
    solicitud = inicio.split("solicitud=", 1)[1].split()[0]
    logs_mcp = [r.message for r in caplog.records if r.name == "parachute.mcp" and "herramienta=" in r.message]
    assert len(logs_mcp) == 2
    assert all(f"solicitud={solicitud}" in log for log in logs_mcp)


def test_caida_real_mcp_se_entrega_como_tarea_fallida(instalar_modelo):
    modelo = ScriptedModel([
        llamada("gestionar_agenda", {"input": "Reservar"}, "agenda-caida"),
        llamada("agendar_cita", {
            "nombre": "Cliente A2A", "fecha_iso": "2026-09-29", "hora": "10:00",
            "id_evidencia": "sin-evidencia",
        }, "reserva-caida"),
    ])
    clientes, conexiones = instalar_modelo(modelo)

    async def escenario():
        mcp = crear_servidor_mcp()
        async with AsyncExitStack() as stack:
            url_mcp = await stack.enter_async_context(servidor_http(
                mcp.streamable_http_app(json_response=True, stateless_http=True),
            ))
            async with servidor_http(a2a_server.crear_aplicacion_a2a(mcp_url=url_mcp + "/mcp")) as url:
                await conexiones[0].list_tools(
                    RunContextWrapper(context=mas_mcp.ContextoTurno()),
                    SimpleNamespace(name="especialista_agenda"),
                )
                await stack.aclose()
                async with cliente_a2a(url) as client:
                    tarea = await enviar(client, "Reserva")
                    assert tarea.status.state == TaskState.TASK_STATE_FAILED
                    assert not tarea.artifacts
                    assert "incierto" in tarea.status.message.parts[0].text
        assert clientes[0].is_closed()
        assert conexiones[0].session is None
        assert conexiones[0].max_retry_attempts == 0

    asyncio.run(escenario())
    modelo.assert_complete()
