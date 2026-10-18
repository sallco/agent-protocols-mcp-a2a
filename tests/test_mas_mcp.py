"""MAS y SDK de Agents reales sobre HTTP MCP, con respuestas LLM simuladas."""

import asyncio
from contextlib import AsyncExitStack
import json
import logging
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from agents import AgentsException, RunContextWrapper
from agents.testing import ScriptedModel, ModelStep, assistant_message, function_call
from openai import AsyncOpenAI
import pytest

from core import tools
import mas_mcp
from mcp_server import crear_servidor_mcp
from tests.http_server import servidor_http


@pytest.fixture
def instalar_modelo(monkeypatch):
    clientes, conexiones = [], []
    conectar = mas_mcp.MCPServerStreamableHttp

    def registrar_conexion(**kwargs):
        conexion = conectar(**kwargs)
        conexiones.append(conexion)
        return conexion

    def nuevo_cliente():
        client = AsyncOpenAI(api_key="clave-de-prueba", base_url="http://127.0.0.1:9")
        clientes.append(client)
        return client

    def instalar(modelo):
        monkeypatch.setattr(mas_mcp, "create_model", lambda *args, **kwargs: modelo)
        monkeypatch.setattr(mas_mcp, "get_async_openai_client", nuevo_cliente)
        monkeypatch.setattr(mas_mcp, "MCPServerStreamableHttp", registrar_conexion)
        return clientes, conexiones

    return instalar


def ultima_salida(call):
    item = next(item for item in reversed(call.input) if item.get("type") == "function_call_output")
    output = item["output"]
    if isinstance(output, list):
        output = output[0]["text"]
    return json.loads(output)


def llamada(nombre, argumentos, id):
    return [function_call(nombre, argumentos, call_id=id)]


@pytest.mark.parametrize("modo", ["ideal", "marginal"])
def test_reserva_por_especialistas_con_comprobante_y_contexto_remotos(
    agenda_aislada, instalar_modelo, monkeypatch, caplog, modo,
):
    evidencia = {}

    def evaluar(call):
        evidencia.update(ultima_salida(call))
        return llamada("evaluar_condiciones", {"id_evidencia": evidencia["id_evidencia"]}, "evaluar")

    def delegar_agenda(call):
        reporte = ultima_salida(call)
        assert reporte["id_evidencia"] == evidencia["id_evidencia"]
        return llamada("gestionar_agenda", {"input": json.dumps(reporte)}, "agenda")

    modelo = ScriptedModel([
        llamada("consultar_clima_seguridad", {"input": "Clima del 2026-09-29"}, "clima"),
        llamada("resolver_fecha", {"expresion": "2026-09-29"}, "fecha"),
        llamada("consultar_clima", {"fecha_iso": "2026-09-29"}, "pronostico"),
        ModelStep.respond(evaluar),
        ModelStep.respond(lambda call: [assistant_message(json.dumps(ultima_salida(call)))]),
        ModelStep.respond(delegar_agenda),
        llamada("consultar_disponibilidad", {"fecha_iso": "2026-09-29"}, "cupos"),
        ModelStep.respond(lambda call: llamada("agendar_cita", {
            "nombre": "Cliente del MAS", "fecha_iso": "2026-09-29", "hora": "10:00",
            "id_evidencia": evidencia["id_evidencia"],
        }, "reserva")),
        [assistant_message("Reserva registrada por agenda.")],
        [assistant_message("Respuesta del asistente sin copiar el comprobante.")],
        [assistant_message("De nada.", item_id="segundo-turno")],
    ])
    clientes, conexiones = instalar_modelo(modelo)
    monkeypatch.setattr(tools, "obtener_ultimo_comprobante", lambda: pytest.fail("No debe leer el comprobante local"))
    solicitud = str(uuid4())

    async def escenario():
        server = crear_servidor_mcp(mock_clima=modo, fecha_base="2026-09-18")
        app = server.streamable_http_app(json_response=True, stateless_http=True)
        async with servidor_http(app) as url:
            async with mas_mcp.conectar_mas_mcp(mcp_url=url + "/mcp") as orquestador:
                resultado, comprobante = await mas_mcp.ejecutar_turno_mcp(
                    orquestador, "Reserva para mañana", solicitud_id=solicitud,
                )
                reserva = ultima_salida(modelo.calls[8])
                assert comprobante == reserva["comprobante"]
                assert reserva["id_cita"] in comprobante
                assert resultado.final_output == "Respuesta del asistente sin copiar el comprobante."
                assert not clientes[0].is_closed()
                for call in modelo.calls[1:5]:
                    assert {tool.name for tool in call.tools} == mas_mcp.HERRAMIENTAS_POR_ESPECIALISTA["especialista_clima_seguridad"]
                for call in modelo.calls[6:9]:
                    assert {tool.name for tool in call.tools} == mas_mcp.HERRAMIENTAS_POR_ESPECIALISTA["especialista_agenda"]
                historial = resultado.to_input_list() + [{"role": "user", "content": "Gracias"}]
                _, siguiente_comprobante = await mas_mcp.ejecutar_turno_mcp(orquestador, historial)
                assert siguiente_comprobante is None
                assert not clientes[0].is_closed()
            assert conexiones[0].session is None
        assert clientes[0].is_closed()

    caplog.set_level(logging.INFO, logger="parachute.mcp")
    asyncio.run(escenario())
    modelo.assert_complete()
    registros = [r.message for r in caplog.records if r.name == "parachute.mcp" and "herramienta=" in r.message]
    assert len(registros) == 5
    assert all(f"solicitud={solicitud}" in r for r in registros)


def test_especialista_faqs_solo_ve_su_herramienta(instalar_modelo, monkeypatch):
    modelo = ScriptedModel([
        llamada("consultar_faqs", {"input": "Peso máximo"}, "faq"),
        llamada("buscar_faqs", {"consulta": "peso máximo"}, "buscar"),
        [assistant_message("El máximo es 100 kg (FAQ-021).")],
        [assistant_message("100 kg (FAQ-021).")],
    ])
    instalar_modelo(modelo)
    monkeypatch.setattr(tools._faq_store, "buscar", lambda *args, **kwargs: [{
        "id": "FAQ-021", "categoria": "Requisitos", "pregunta": "Peso máximo",
        "respuesta": "100 kg", "similitud": 0.95, "estado_calidad": "valida",
    }])

    async def escenario():
        server = crear_servidor_mcp()
        app = server.streamable_http_app(json_response=True, stateless_http=True)
        async with servidor_http(app) as url:
            async with mas_mcp.conectar_mas_mcp(mcp_url=url + "/mcp") as orquestador:
                resultado, comprobante = await mas_mcp.ejecutar_turno_mcp(orquestador, "Peso máximo")
                assert "FAQ-021" in resultado.final_output
                assert comprobante is None

    asyncio.run(escenario())
    assert {tool.name for tool in modelo.calls[1].tools} == {"buscar_faqs"}
    modelo.assert_complete()


def test_caida_de_mcp_se_propaga_sin_reintentar_reserva(instalar_modelo):
    modelo = ScriptedModel([
        llamada("gestionar_agenda", {"input": "Reservar"}, "agenda-caida"),
        llamada("agendar_cita", {
            "nombre": "Cliente", "fecha_iso": "2026-09-29", "hora": "10:00",
            "id_evidencia": "sin-evidencia",
        }, "reserva-caida"),
    ])
    clientes, conexiones = instalar_modelo(modelo)

    async def escenario():
        server = crear_servidor_mcp()
        app = server.streamable_http_app(json_response=True, stateless_http=True)
        async with AsyncExitStack() as stack:
            url = await stack.enter_async_context(servidor_http(app))
            async with mas_mcp.conectar_mas_mcp(mcp_url=url + "/mcp") as orquestador:
                # Cargar el catálogo antes de apagar HTTP simula perder la respuesta al invocar.
                contexto = RunContextWrapper(context=mas_mcp.ContextoTurno())
                agente = SimpleNamespace(name="especialista_agenda")
                await conexiones[0].list_tools(contexto, agente)
                await stack.aclose()
                with pytest.raises(AgentsException):
                    await mas_mcp.ejecutar_turno_mcp(orquestador, "Reserva")
                assert conexiones[0].max_retry_attempts == 0
        assert clientes[0].is_closed()
        assert conexiones[0].session is None

    asyncio.run(escenario())
    modelo.assert_complete()


def test_error_del_consumidor_cierra_ambas_conexiones(instalar_modelo):
    clientes, conexiones = instalar_modelo(ScriptedModel())

    async def escenario():
        server = crear_servidor_mcp()
        app = server.streamable_http_app(json_response=True, stateless_http=True)
        async with servidor_http(app) as url:
            with pytest.raises(RuntimeError, match="fallo del consumidor"):
                async with mas_mcp.conectar_mas_mcp(mcp_url=url + "/mcp"):
                    raise RuntimeError("fallo del consumidor")
        assert clientes[0].is_closed()
        assert conexiones[0].session is None

    asyncio.run(escenario())


def test_comprobantes_se_aislan_entre_contextos_concurrentes():
    async def escenario():
        primero, segundo = mas_mcp.ContextoTurno(), mas_mcp.ContextoTurno()
        hook = mas_mcp.CapturarComprobante()
        herramienta = SimpleNamespace(name="agendar_cita")
        await asyncio.gather(*[
            hook.on_tool_end(
                RunContextWrapper(context=ctx), None, herramienta,
                {"type": "text", "text": json.dumps({"exito": True, "comprobante": texto})},
            )
            for ctx, texto in [(primero, "comprobante A"), (segundo, "comprobante B")]
        ])
        assert primero.comprobante == "comprobante A"
        assert segundo.comprobante == "comprobante B"
        assert primero.solicitud_id != segundo.solicitud_id

    asyncio.run(escenario())


def test_reserva_rechazada_no_genera_comprobante_y_confirmacion_incompleta_falla():
    async def escenario():
        estado = mas_mcp.ContextoTurno()
        contexto = RunContextWrapper(context=estado)
        hook = mas_mcp.CapturarComprobante()
        herramienta = SimpleNamespace(name="agendar_cita")
        await hook.on_tool_end(contexto, None, herramienta, {
            "type": "text", "text": json.dumps({"exito": False, "comprobante": None}),
        })
        assert estado.comprobante is None
        with pytest.raises(ValueError, match="no incluyó su comprobante"):
            await hook.on_tool_end(contexto, None, herramienta, {
                "type": "text", "text": json.dumps({"exito": True, "comprobante": None}),
            })

    asyncio.run(escenario())


def test_error_al_conectar_mcp_cierra_cliente_llm(instalar_modelo, monkeypatch):
    clientes, _ = instalar_modelo(ScriptedModel())
    conexion = MagicMock()
    conexion.__aenter__ = AsyncMock(side_effect=RuntimeError("MCP no disponible"))
    conexion.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(mas_mcp, "MCPServerStreamableHttp", MagicMock(return_value=conexion))

    async def escenario():
        with pytest.raises(RuntimeError, match="MCP no disponible"):
            async with mas_mcp.conectar_mas_mcp():
                pytest.fail("No debe entregar un MAS sin conexión MCP")
        assert clientes[0].is_closed()

    asyncio.run(escenario())
