"""Pruebas unitarias para el evaluador determinista de seguridad de saltos."""

from __future__ import annotations

import pytest
from core.safety import Veredicto, evaluar_condiciones_salto


def test_fronteras_viento() -> None:
    # 19.99 -> IDEAL
    res = evaluar_condiciones_salto(19.99, 25.0, 0.0, 20.0, 24.0)
    assert res.veredicto_global == Veredicto.IDEAL

    # 20.0 -> MARGINAL con advertencia tándem
    res = evaluar_condiciones_salto(20.0, 25.0, 0.0, 20.0, 24.0)
    assert res.veredicto_global == Veredicto.MARGINAL
    assert any("solo tándem experimentado" in adv for adv in res.advertencias)

    # 28.0 -> MARGINAL
    res = evaluar_condiciones_salto(28.0, 25.0, 0.0, 20.0, 24.0)
    assert res.veredicto_global == Veredicto.MARGINAL

    # 28.01 -> PROHIBIDO
    res = evaluar_condiciones_salto(28.01, 25.0, 0.0, 20.0, 24.0)
    assert res.veredicto_global == Veredicto.PROHIBIDO
    assert res.es_seguro_saltar is False


def test_fronteras_rafagas() -> None:
    # 35.0 -> IDEAL (si los demás son ideales)
    res = evaluar_condiciones_salto(15.0, 35.0, 0.0, 20.0, 24.0)
    assert res.veredicto_global == Veredicto.IDEAL

    # 35.01 -> PROHIBIDO
    res = evaluar_condiciones_salto(15.0, 35.01, 0.0, 20.0, 24.0)
    assert res.veredicto_global == Veredicto.PROHIBIDO


def test_fronteras_precipitacion() -> None:
    # 0.0 -> IDEAL
    res = evaluar_condiciones_salto(15.0, 25.0, 0.0, 20.0, 24.0)
    assert res.veredicto_global == Veredicto.IDEAL

    # 0.01 -> PROHIBIDO
    res = evaluar_condiciones_salto(15.0, 25.0, 0.01, 20.0, 24.0)
    assert res.veredicto_global == Veredicto.PROHIBIDO


def test_fronteras_nubes() -> None:
    # 29.99 -> IDEAL
    res = evaluar_condiciones_salto(15.0, 25.0, 0.0, 29.99, 24.0)
    assert res.veredicto_global == Veredicto.IDEAL

    # 30.0 -> MARGINAL
    res = evaluar_condiciones_salto(15.0, 25.0, 0.0, 30.0, 24.0)
    assert res.veredicto_global == Veredicto.MARGINAL

    # 75.0 -> MARGINAL
    res = evaluar_condiciones_salto(15.0, 25.0, 0.0, 75.0, 24.0)
    assert res.veredicto_global == Veredicto.MARGINAL

    # 75.01 -> PROHIBIDO
    res = evaluar_condiciones_salto(15.0, 25.0, 0.0, 75.01, 24.0)
    assert res.veredicto_global == Veredicto.PROHIBIDO


def test_temperatura_no_veta() -> None:
    # Temperatura extrema pero sin veto
    res_frio = evaluar_condiciones_salto(15.0, 20.0, 0.0, 10.0, 2.0)
    assert res_frio.veredicto_global == Veredicto.IDEAL

    res_calor = evaluar_condiciones_salto(15.0, 20.0, 0.0, 10.0, 42.0)
    assert res_calor.veredicto_global == Veredicto.IDEAL


def test_valores_invalidos_lanzan_error() -> None:
    with pytest.raises(ValueError, match="no puede ser menor"):
        evaluar_condiciones_salto(-5.0, 20.0, 0.0, 10.0, 25.0)

    with pytest.raises(ValueError, match="NaN ni infinito"):
        evaluar_condiciones_salto(float("nan"), 20.0, 0.0, 10.0, 25.0)

    with pytest.raises(ValueError, match="no puede ser mayor"):
        evaluar_condiciones_salto(15.0, 20.0, 0.0, 110.0, 25.0)
