"""Pruebas unitarias para la arquitectura centralizada."""

from __future__ import annotations

import subprocess
import sys

from agents import Agent
from agents.mcp import MCPServerStreamableHttp
from agents.testing import ScriptedModel

import arch_centralizada
from arch_centralizada import construir_agentes_centralizados


def test_construccion_arquitectura_centralizada() -> None:
    orquestador = construir_agentes_centralizados()
    assert orquestador.name == "orquestador_central"

    # Verificar herramientas expuestas por as_tool()
    nombres_herramientas = [getattr(t, "name", str(t)) for t in orquestador.tools]
    assert "consultar_faqs" in nombres_herramientas
    assert "consultar_clima_seguridad" in nombres_herramientas
    assert "gestionar_agenda" in nombres_herramientas


def test_modo_remoto_no_mezcla_herramientas_locales(monkeypatch):
    agentes = {}

    def registrar(**kwargs):
        agente = Agent(**kwargs)
        agentes[agente.name] = agente
        return agente

    monkeypatch.setattr(arch_centralizada, "Agent", registrar)
    server = MCPServerStreamableHttp(params={"url": "http://127.0.0.1:8001/mcp"})
    modelo = ScriptedModel()
    orquestador = construir_agentes_centralizados(model=modelo, mcp_server=server)
    assert orquestador.mcp_servers == []
    for nombre in ("especialista_faqs", "especialista_clima_seguridad", "especialista_agenda"):
        assert agentes[nombre].tools == []
        assert agentes[nombre].mcp_servers == [server]
        assert agentes[nombre].model is modelo


def test_construccion_remota_no_importa_servicios_de_negocio():
    code = (
        "import sys; from agents.mcp import MCPServerStreamableHttp; "
        "from agents.testing import ScriptedModel; "
        "from arch_centralizada import construir_agentes_centralizados; "
        "server=MCPServerStreamableHttp(params={'url':'http://127.0.0.1:8001/mcp'}); "
        "construir_agentes_centralizados(model=ScriptedModel(),mcp_server=server); "
        "assert 'core.tools' not in sys.modules; assert 'core.faq_store' not in sys.modules; "
        "assert 'core.scheduling' not in sys.modules"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
