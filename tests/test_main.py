"""Opciones de ejecución local sin llamadas al proveedor ni a la base de datos."""

import importlib
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import main
from core import tools


@pytest.mark.parametrize("arquitectura", ["centralizada", "jerarquica", "descentralizada"])
def test_opciones_llegan_a_herramientas_y_arquitectura(monkeypatch, arquitectura):
    chat = MagicMock()
    configure = MagicMock()
    monkeypatch.setitem(sys.modules, "arch_" + arquitectura, SimpleNamespace(main=chat))
    monkeypatch.setattr(tools, "configurar_herramientas", configure)

    main.main([
        "chat-local", "--arquitectura", arquitectura, "--modelo", "modelo-prueba",
        "--mock-clima", "prohibido", "--fecha-base", "2026-09-18",
    ])

    configure.assert_called_once_with(mock_clima="prohibido", fecha_base="2026-09-18")
    chat.assert_called_once_with(model_name="modelo-prueba")


@pytest.mark.parametrize("arquitectura,constructor", [
    ("centralizada", "construir_agentes_centralizados"),
    ("jerarquica", "construir_agentes_jerarquicos"),
    ("descentralizada", "construir_red_descentralizada"),
])
def test_chat_local_construye_agentes_con_modelo_elegido(monkeypatch, arquitectura, constructor):
    module = importlib.import_module("arch_" + arquitectura)
    factory = MagicMock(return_value=(SimpleNamespace(name="FAQs"), None, None)
                        if arquitectura == "descentralizada" else SimpleNamespace())
    monkeypatch.setattr(module, constructor, factory)
    monkeypatch.setattr("builtins.input", lambda _: "salir")

    module.main(model_name="modelo-prueba")

    factory.assert_called_once_with("modelo-prueba")


@pytest.mark.parametrize("argumentos", [
    ["chat-local", "--fecha-base", "2026-09-18"],
    ["chat-local", "--mock-clima", "ideal", "--fecha-base", "2026-02-30"],
    ["chat-local", "--mock-clima", "desconocido"],
])
def test_rechaza_configuracion_invalida(argumentos):
    with pytest.raises(SystemExit) as error:
        main.parse_arguments(argumentos)
    assert error.value.code == 2


def test_comando_mcp_envia_opciones_al_servidor(monkeypatch):
    start = MagicMock()
    monkeypatch.setitem(sys.modules, "mcp_server", SimpleNamespace(main=start))
    main.main([
        "mcp-server", "--puerto", "8101", "--mock-clima", "marginal",
        "--fecha-base", "2026-09-18",
    ])
    start.assert_called_once_with(mock_clima="marginal", fecha_base="2026-09-18", puerto=8101)


@pytest.mark.parametrize("argumentos", [
    ["mcp-server", "--fecha-base", "2026-09-18"],
    ["mcp-server", "--mock-clima", "ideal", "--fecha-base", "2026-02-30"],
    ["mcp-server", "--puerto", "0"],
    ["mcp-server", "--puerto", "65536"],
])
def test_rechaza_opciones_mcp_invalidas(argumentos):
    with pytest.raises(SystemExit) as error:
        main.parse_arguments(argumentos)
    assert error.value.code == 2


def test_ayuda_no_importa_servicios_locales():
    code = (
        "import sys, main; "
        "assert 'core.tools' not in sys.modules; "
        "assert 'arch_centralizada' not in sys.modules; "
        "main.parse_arguments(['--help'])"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "chat-local" in result.stdout


def test_comando_a2a_envia_opciones_al_servidor(monkeypatch):
    start = MagicMock()
    monkeypatch.setitem(sys.modules, "a2a_server", SimpleNamespace(main=start))
    main.main(["a2a-server", "--puerto", "8100", "--mcp-url", "http://127.0.0.1:8101/mcp", "--modelo", "modelo"])
    start.assert_called_once_with(puerto=8100, mcp_url="http://127.0.0.1:8101/mcp", model_name="modelo")


@pytest.mark.parametrize("puerto", ["0", "65536"])
def test_rechaza_puerto_a2a_invalido(puerto):
    with pytest.raises(SystemExit) as error:
        main.parse_arguments(["a2a-server", "--puerto", puerto])
    assert error.value.code == 2


def test_chat_utiliza_cliente_remoto(monkeypatch):
    start = MagicMock()
    monkeypatch.setitem(sys.modules, "terminal", SimpleNamespace(main=start))
    main.main(["chat", "--a2a-url", "http://127.0.0.1:8100", "--mcp-url", "http://127.0.0.1:8101/mcp"])
    start.assert_called_once_with(a2a_url="http://127.0.0.1:8100", mcp_url="http://127.0.0.1:8101/mcp")


@pytest.mark.parametrize("opcion,valor", [
    ("--arquitectura", "centralizada"), ("--modelo", "modelo"),
    ("--mock-clima", "ideal"), ("--fecha-base", "2026-09-18"),
])
def test_chat_no_acepta_configurar_servicios_locales(opcion, valor):
    with pytest.raises(SystemExit) as error:
        main.parse_arguments(["chat", opcion, valor])
    assert error.value.code == 2
