"""Pruebas unitarias para el cliente de meteorología y agregación de variables."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from core.safety import Veredicto
from core.weather import WeatherClient


def test_mock_fixtures_ideal() -> None:
    client = WeatherClient()
    evidencia = client.consultar("2026-09-29", mock_mode="ideal")

    assert evidencia.evaluacion.veredicto_global == Veredicto.IDEAL
    assert evidencia.evaluacion.es_seguro_saltar is True
    assert evidencia.viento_kmh == 14.5
    assert evidencia.precipitacion_mm == 0.0

    # Recuperación desde caché de evidencia
    recuperada = WeatherClient.obtener_evidencia(evidencia.id_evidencia)
    assert recuperada is not None
    assert recuperada.id_evidencia == evidencia.id_evidencia


def test_mock_fixtures_marginal() -> None:
    client = WeatherClient()
    evidencia = client.consultar("2026-09-29", mock_mode="marginal")

    assert evidencia.evaluacion.veredicto_global == Veredicto.MARGINAL
    assert evidencia.evaluacion.es_seguro_saltar is True
    assert any("solo tándem experimentado" in adv for adv in evidencia.evaluacion.advertencias)


def test_mock_fixtures_prohibido() -> None:
    client = WeatherClient()
    evidencia = client.consultar("2026-09-29", mock_mode="prohibido")

    assert evidencia.evaluacion.veredicto_global == Veredicto.PROHIBIDO
    assert evidencia.evaluacion.es_seguro_saltar is False


def test_agregacion_horaria_operativa() -> None:
    client = WeatherClient()

    # Simulamos respuesta de 24 horas (00:00 a 23:00)
    tiempos = [f"2026-09-29T{h:02d}:00" for h in range(24)]
    # Lluvia solo en la noche (hora 20), en horas de salto (08 a 16) lluvia = 0
    precipitaciones = [5.0 if h >= 19 else 0.0 for h in range(24)]
    # Vientos moderados en el día
    vientos = [12.0 + (h % 5) for h in range(24)]
    rafagas = [v + 5.0 for v in vientos]
    nubes = [25.0 for _ in range(24)]
    temperaturas = [24.0 for _ in range(24)]

    mock_json = {
        "hourly": {
            "time": tiempos,
            "wind_speed_10m": vientos,
            "wind_gusts_10m": rafagas,
            "precipitation": precipitaciones,
            "cloud_cover": nubes,
            "temperature_2m": temperaturas,
        }
    }

    with patch.object(client, "_ejecutar_peticion", return_value=mock_json):
        evidencia = client.consultar("2026-09-29", modo="operativo_horario")
        # En la franja 08-16h la lluvia acumulada debe ser 0.0 a pesar de llover a las 20:00
        assert evidencia.precipitacion_mm == 0.0
        assert evidencia.evaluacion.veredicto_global == Veredicto.IDEAL
