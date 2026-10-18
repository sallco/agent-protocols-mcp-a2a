"""Integración MCP mediante sockets HTTP reales, sin llamadas al LLM."""

import asyncio
from contextlib import asynccontextmanager
import json
import logging
from uuid import uuid4
from unittest.mock import MagicMock

from mcp import Client
from mcp.types import RequestParamsMeta
from mcp.shared.exceptions import MCPError
import pytest

from core import tools
import mcp_server
from mcp_server import crear_servidor_mcp
from tests.http_server import servidor_http


@asynccontextmanager
async def cliente_http(server):
    app = server.streamable_http_app(json_response=True, stateless_http=True)
    async with servidor_http(app) as url:
        async with Client(url + "/mcp") as client:
            yield client


def resultado_json(result):
    assert not result.is_error, result.content
    return json.loads(result.content[0].text)


def test_ctrl_c_finaliza_sin_propagar_traceback(monkeypatch, caplog):
    server = MagicMock()
    server.run.side_effect = KeyboardInterrupt
    monkeypatch.setattr(mcp_server, "crear_servidor_mcp", lambda **kwargs: server)
    caplog.set_level(logging.INFO, logger="parachute.mcp")

    mcp_server.main()

    assert "Servidor MCP detenido por el operador" in caplog.text


def test_catalogo_contratos_y_clima_del_operador(monkeypatch, caplog):
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    async def escenario():
        server = crear_servidor_mcp(mock_clima="prohibido", fecha_base="2026-09-18")
        async with cliente_http(server) as client:
            catalogo = {t.name: t for t in (await client.list_tools()).tools}
            assert set(catalogo) == {t.name for t in tools.HERRAMIENTAS_COMPARTIDAS}
            assert "mock_mode" not in catalogo["consultar_clima"].input_schema["properties"]
            assert "arquitectura" not in catalogo["agendar_cita"].input_schema["properties"]
            fecha = resultado_json(await client.call_tool("resolver_fecha", {"expresion": "mañana"}))
            assert fecha["fecha_iso"] == "2026-09-19"
            solicitud = str(uuid4())
            clima = resultado_json(await client.call_tool(
                "consultar_clima", {"fecha_iso": "2026-09-29", "mock_mode": "ideal"},
                meta=RequestParamsMeta(request_id=solicitud),
            ))
            assert clima["veredicto_global"] == "PROHIBIDO"
            evaluacion = resultado_json(await client.call_tool(
                "evaluar_condiciones", {"id_evidencia": clima["id_evidencia"]},
            ))
            assert evaluacion["veredicto"] == "PROHIBIDO"
            reserva = resultado_json(await client.call_tool("agendar_cita", {
                "nombre": "Nombre privado", "fecha_iso": "2026-09-29",
                "hora": "10:00", "id_evidencia": clima["id_evidencia"],
            }))
            assert reserva["exito"] is False
            assert reserva["veredicto"] == "PROHIBIDO"
            invalida = resultado_json(await client.call_tool("agendar_cita", {
                "nombre": "Nombre privado", "fecha_iso": "2026-09-29",
                "hora": "10:00", "id_evidencia": "evidencia-inexistente",
            }))
            assert invalida["exito"] is False
            discordante = resultado_json(await client.call_tool("agendar_cita", {
                "nombre": "Nombre privado", "fecha_iso": "2026-09-30",
                "hora": "10:00", "id_evidencia": clima["id_evidencia"],
            }))
            assert discordante["exito"] is False
            assert "Inconsistencia de evidencia" in discordante["mensaje"]
        return solicitud

    caplog.set_level(logging.INFO, logger="parachute.mcp")
    solicitud = asyncio.run(escenario())
    assert "herramienta=consultar_clima estado=completada" in caplog.text
    assert "herramienta=agendar_cita estado=rechazada" in caplog.text
    assert "duracion_ms=" in caplog.text
    assert f"solicitud={solicitud}" in caplog.text
    assert "Nombre privado" not in caplog.text


def test_busqueda_y_fallos_no_exponen_datos_internos(monkeypatch, caplog):
    async def escenario():
        server = crear_servidor_mcp()
        async with cliente_http(server) as client:
            monkeypatch.setattr(tools._faq_store, "buscar", lambda *args, **kwargs: [{
                "id": "FAQ-021", "categoria": "Requisitos", "pregunta": "Peso máximo",
                "respuesta": "100 kg", "similitud": 0.95, "estado_calidad": "valida",
            }])
            faqs = resultado_json(await client.call_tool("buscar_faqs", {"consulta": "peso máximo"}))
            assert faqs["faqs"][0]["id"] == "FAQ-021"

            def fallar(*args, **kwargs):
                raise RuntimeError("clave-secreta-interna")

            monkeypatch.setattr(tools._faq_store, "buscar", fallar)
            fallo = await client.call_tool("buscar_faqs", {"consulta": "consulta privada"})
            assert fallo.is_error
            assert "clave-secreta-interna" not in str(fallo.content)
            invalida = await client.call_tool("resolver_fecha", {})
            assert invalida.is_error
            fecha = resultado_json(await client.call_tool("resolver_fecha", {"expresion": "2026-02-30"}))
            assert fecha["es_valida"] is False

    caplog.set_level(logging.INFO, logger="parachute.mcp")
    asyncio.run(escenario())
    assert "herramienta=buscar_faqs estado=fallida" in caplog.text
    assert "herramienta=resolver_fecha estado=rechazada" in caplog.text
    assert "clave-secreta-interna" not in caplog.text
    assert "consulta privada" not in caplog.text


@pytest.mark.parametrize("modo", ["ideal", "marginal"])
def test_reservas_reales_en_tabla_aislada(agenda_aislada, modo):
    async def escenario():
        server = crear_servidor_mcp(mock_clima=modo, fecha_base="2026-09-18")
        async with cliente_http(server) as client:
            clima = resultado_json(await client.call_tool("consultar_clima", {"fecha_iso": "2026-09-29"}))
            cupos = resultado_json(await client.call_tool("consultar_disponibilidad", {"fecha_iso": "2026-09-29"}))
            assert "10:00" in cupos["franjas_libres"]
            argumentos = {
                "nombre": "Cliente HTTP", "fecha_iso": "2026-09-29",
                "hora": "10:00", "id_evidencia": clima["id_evidencia"],
            }
            reserva = resultado_json(await client.call_tool("agendar_cita", argumentos))
            assert reserva["exito"] is True
            assert reserva["veredicto"] == modo.upper()
            assert reserva["id_cita"] in reserva["comprobante"]
            if modo == "marginal":
                assert "tándem experimentado" in reserva["comprobante"]
            repetida = resultado_json(await client.call_tool("agendar_cita", argumentos))
            assert repetida["id_cita"] == reserva["id_cita"]
            argumentos["nombre"] = "Otro cliente"
            ocupada = resultado_json(await client.call_tool("agendar_cita", argumentos))
            assert ocupada["exito"] is False
            citas = resultado_json(await client.call_tool("listar_citas", {"fecha_iso": "2026-09-29"}))
            assert citas["total"] == 1

    asyncio.run(escenario())


def test_recurso_entrega_corpus_original_sin_ejecutar_herramientas(monkeypatch, caplog):
    buscar = MagicMock(side_effect=AssertionError("No debe ejecutar RAG"))
    clima = MagicMock(side_effect=AssertionError("No debe consultar clima"))
    monkeypatch.setattr(tools._faq_store, "buscar", buscar)
    monkeypatch.setattr(tools._weather_client, "consultar", clima)

    async def escenario():
        server = crear_servidor_mcp()
        async with cliente_http(server) as client:
            resources = (await client.list_resources()).resources
            assert len(resources) == 1
            assert str(resources[0].uri) == "parachute://faqs/corpus"
            result = await client.read_resource("parachute://faqs/corpus")
            assert result.contents[0].mime_type == "text/plain"
            assert result.contents[0].text == mcp_server.CORPUS_PATH.read_text(encoding="utf-8")
            assert "FAQ-021" in result.contents[0].text
            assert (await client.list_prompts()).prompts == []

    caplog.set_level(logging.INFO, logger="parachute.mcp")
    asyncio.run(escenario())
    buscar.assert_not_called()
    clima.assert_not_called()
    assert "recurso=parachute://faqs/corpus estado=completada" in caplog.text
    assert "herramienta=" not in caplog.text


def test_recurso_no_permite_leer_archivos_arbitrarios():
    async def escenario():
        async with cliente_http(crear_servidor_mcp()) as client:
            with pytest.raises(MCPError):
                await client.read_resource("file:///etc/passwd")

    asyncio.run(escenario())


def test_recurso_no_disponible_reporta_error_sin_exponer_ruta(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(mcp_server, "CORPUS_PATH", tmp_path / "ruta-privada-inexistente.txt")

    async def escenario():
        async with cliente_http(crear_servidor_mcp()) as client:
            with pytest.raises(MCPError, match="No fue posible leer el corpus de FAQs") as error:
                await client.read_resource("parachute://faqs/corpus")
            assert "ruta-privada" not in str(error.value)
            assert len((await client.list_resources()).resources) == 1

    caplog.set_level(logging.INFO, logger="parachute.mcp")
    asyncio.run(escenario())
    assert "recurso=parachute://faqs/corpus estado=fallida" in caplog.text
    assert "ruta-privada" not in caplog.text
