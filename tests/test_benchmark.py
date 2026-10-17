"""Pruebas unitarias para los datos y estructura de la matriz comparativa."""

from __future__ import annotations

import json
from pathlib import Path


def test_archivo_comparativo_arquitecturas_valido() -> None:
    data_file = Path(__file__).parent.parent / "data" / "comparativa_arquitecturas.json"
    assert data_file.is_file(), "El archivo comparativo_arquitecturas.json debe existir."

    datos = json.loads(data_file.read_text(encoding="utf-8"))
    assert len(datos) == 9, "Deben existir 9 mediciones (3 escenarios x 3 arquitecturas)."

    arquitecturas = {"centralizada", "jerarquica", "descentralizada"}
    escenarios = {"faq_institucional", "clima_seguridad", "flujo_combinado"}

    arqs_observadas = {item["arquitectura"] for item in datos}
    escenarios_observados = {item["escenario"] for item in datos}

    assert arqs_observadas == arquitecturas
    assert escenarios_observados == escenarios

    for item in datos:
        assert item["latencia_segundos"] > 0
        assert item["caracteres_respuesta"] > 0
        assert item["agente_final"] != ""
