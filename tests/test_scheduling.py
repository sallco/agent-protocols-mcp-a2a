"""Pruebas unitarias para el servicio de agendamiento y validación de evidencia."""

from __future__ import annotations

import pytest
from core.scheduling import SchedulingService
from core.weather import WeatherClient


def test_consultar_disponibilidad() -> None:
    service = SchedulingService()
    disp = service.consultar_disponibilidad("2026-09-29")
    assert disp["valida"] is True
    assert disp["total_cupos"] == 8
    assert len(disp["franjas_libres"]) + len(disp["franjas_ocupadas"]) == 8


def test_agendar_rechazo_evidencia_inexistente() -> None:
    service = SchedulingService()
    res = service.agendar_cita(
        nombre="Mario López",
        fecha_iso="2026-09-29",
        hora="10:00",
        id_evidencia="evidencia-falsa-12345",
        arquitectura="centralizada",
    )
    assert res.exito is False
    assert "No se encontró registro de evidencia" in res.mensaje


def test_agendar_rechazo_fecha_discordante() -> None:
    weather_client = WeatherClient()
    # Evidencia para el 2026-09-29
    evidencia = weather_client.consultar("2026-09-29", mock_mode="ideal")

    service = SchedulingService()
    # Intento de reservar para el 2026-09-30 con evidencia del 29
    res = service.agendar_cita(
        nombre="Mario López",
        fecha_iso="2026-09-30",
        hora="10:00",
        id_evidencia=evidencia.id_evidencia,
        arquitectura="centralizada",
    )
    assert res.exito is False
    assert "Inconsistencia de evidencia" in res.mensaje


def test_agendar_rechazo_clima_prohibido() -> None:
    weather_client = WeatherClient()
    evidencia_prohibida = weather_client.consultar("2026-09-29", mock_mode="prohibido")

    service = SchedulingService()
    res = service.agendar_cita(
        nombre="Mario López",
        fecha_iso="2026-09-29",
        hora="11:00",
        id_evidencia=evidencia_prohibida.id_evidencia,
        arquitectura="centralizada",
    )
    assert res.exito is False
    assert "PROHIBIDO" in res.mensaje


def test_agendar_exito_marginal_con_advertencias() -> None:
    weather_client = WeatherClient()
    evidencia_marginal = weather_client.consultar("2026-09-29", mock_mode="marginal")

    service = SchedulingService()
    res = service.agendar_cita(
        nombre="Valeria Sol",
        fecha_iso="2026-09-29",
        hora="12:00",
        id_evidencia=evidencia_marginal.id_evidencia,
        arquitectura="centralizada",
    )
    assert res.exito is True
    assert res.veredicto == "MARGINAL"
    assert res.comprobante is not None
    assert "COMPROBANTE OFICIAL DE RESERVA" in res.comprobante
    assert any("solo tándem experimentado" in a for a in (res.advertencias or []))
