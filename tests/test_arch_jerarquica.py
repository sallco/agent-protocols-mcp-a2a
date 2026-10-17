"""Pruebas unitarias para la arquitectura jerárquica."""

from __future__ import annotations

from arch_jerarquica import construir_agentes_jerarquicos


def test_construccion_arquitectura_jerarquica() -> None:
    orquestador = construir_agentes_jerarquicos()
    assert orquestador.name == "orquestador_raiz"

    nombres_herramientas = [getattr(t, "name", str(t)) for t in orquestador.tools]
    assert "supervisor_conocimiento" in nombres_herramientas
    assert "supervisor_operaciones" in nombres_herramientas
