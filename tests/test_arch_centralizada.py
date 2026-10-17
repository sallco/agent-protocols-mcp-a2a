"""Pruebas unitarias para la arquitectura centralizada."""

from __future__ import annotations

from arch_centralizada import construir_agentes_centralizados


def test_construccion_arquitectura_centralizada() -> None:
    orquestador = construir_agentes_centralizados()
    assert orquestador.name == "orquestador_central"

    # Verificar herramientas expuestas por as_tool()
    nombres_herramientas = [getattr(t, "name", str(t)) for t in orquestador.tools]
    assert "consultar_faqs" in nombres_herramientas
    assert "consultar_clima_seguridad" in nombres_herramientas
    assert "gestionar_agenda" in nombres_herramientas
