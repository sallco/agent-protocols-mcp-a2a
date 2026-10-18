"""Pruebas unitarias para las herramientas compartidas del agente."""

from __future__ import annotations

import json
import pytest
from core.tools import (
    HERRAMIENTAS_COMPARTIDAS,
    fn_agendar_cita,
    fn_buscar_faqs,
    fn_consultar_clima,
    fn_consultar_disponibilidad,
    fn_evaluar_condiciones,
    fn_listar_citas,
    fn_resolver_fecha,
    limpiar_ultimo_comprobante,
    obtener_ultimo_comprobante,
)
import core.tools as tools


def test_escenario_del_operador_prevalece_sobre_argumentos_del_modelo(monkeypatch):
    monkeypatch.setattr(tools, "_scheduling_service", tools._scheduling_service)
    try:
        tools.configurar_herramientas(mock_clima="prohibido", fecha_base="2026-09-18")
        assert json.loads(fn_resolver_fecha("mañana"))["fecha_iso"] == "2026-09-19"
        assert tools._scheduling_service.date_resolver.base_date.isoformat() == "2026-09-18"
        clima = json.loads(fn_consultar_clima("2026-09-29", mock_mode="ideal"))
        assert clima["veredicto_global"] == "PROHIBIDO"
        assert clima["fuente"] == "mock://simulador-condiciones"
    finally:
        tools.establecer_mock_clima(None)


def test_fecha_fija_sin_simulacion_no_modifica_servicios():
    original = tools._scheduling_service
    with pytest.raises(ValueError, match="requiere --mock-clima"):
        tools.configurar_herramientas(fecha_base="2026-09-18")
    assert tools._scheduling_service is original


def test_herramientas_compartidas_registradas() -> None:
    assert len(HERRAMIENTAS_COMPARTIDAS) == 7


def test_tool_resolver_fecha() -> None:
    raw = fn_resolver_fecha("29 de septiembre de 2026")
    data = json.loads(raw)
    assert data["es_valida"] is True
    assert data["fecha_iso"] == "2026-09-29"


def test_tool_consultar_clima_y_evaluacion() -> None:
    raw_clima = fn_consultar_clima("2026-09-29", mock_mode="ideal")
    clima = json.loads(raw_clima)
    assert "id_evidencia" in clima
    assert clima["veredicto_global"] == "IDEAL"
    assert clima["es_seguro_saltar"] is True

    # Evaluar condiciones usando el id_evidencia
    raw_eval = fn_evaluar_condiciones(clima["id_evidencia"])
    eval_data = json.loads(raw_eval)
    assert eval_data["veredicto"] == "IDEAL"
    assert eval_data["es_seguro"] is True


def test_tool_agendar_y_comprobante(agenda_aislada: str) -> None:
    limpiar_ultimo_comprobante()
    # 1. Obtener evidencia
    raw_clima = fn_consultar_clima("2026-09-29", mock_mode="marginal")
    clima = json.loads(raw_clima)
    id_evidencia = clima["id_evidencia"]

    # 2. Agendar cita
    raw_reserva = fn_agendar_cita(
        nombre="Lucía Morales",
        fecha_iso="2026-09-29",
        hora="14:00",
        id_evidencia=id_evidencia,
        arquitectura="centralizada",
    )
    reserva = json.loads(raw_reserva)
    assert reserva["exito"] is True
    assert reserva["veredicto"] == "MARGINAL"
    assert obtener_ultimo_comprobante() is not None

    # 3. Listar citas
    raw_citas = fn_listar_citas("2026-09-29")
    citas_data = json.loads(raw_citas)
    assert citas_data["total"] >= 1
