"""Pruebas unitarias para el servicio determinista de fechas."""

from __future__ import annotations

from datetime import date

from core.dates import DateResolver, FRANJAS_VALIDAS


def test_base_date_and_relative_expressions() -> None:
    resolver = DateResolver(base_date="2026-09-18")

    res_hoy = resolver.resolver("hoy")
    assert res_hoy.es_valida is True
    assert res_hoy.fecha_iso == "2026-09-18"

    res_manana = resolver.resolver("mañana")
    assert res_manana.es_valida is True
    assert res_manana.fecha_iso == "2026-09-19"

    res_pasado_manana = resolver.resolver("pasado mañana")
    assert res_pasado_manana.es_valida is True
    assert res_pasado_manana.fecha_iso == "2026-09-20"


def test_proximo_dia_semana() -> None:
    # 2026-09-18 es viernes. El próximo sábado es mañana 2026-09-19.
    resolver = DateResolver(base_date="2026-09-18")
    res_sabado = resolver.resolver("próximo sábado")
    assert res_sabado.es_valida is True
    assert res_sabado.fecha_iso == "2026-09-19"

    # El próximo viernes estrictamente posterior es en 7 días: 2026-09-25
    res_viernes = resolver.resolver("el próximo viernes")
    assert res_viernes.es_valida is True
    assert res_viernes.fecha_iso == "2026-09-25"


def test_evento_nacional_y_ventana_16_dias() -> None:
    resolver = DateResolver(base_date="2026-09-18")

    # Fecha del evento nacional: 29 de septiembre de 2026 (día 11)
    res_evento = resolver.resolver("29 de septiembre de 2026")
    assert res_evento.es_valida is True
    assert res_evento.fecha_iso == "2026-09-29"

    # Límite superior de la ventana: 2026-10-03 (16 días contando hoy)
    res_limite = resolver.resolver("2026-10-03")
    assert res_limite.es_valida is True
    assert res_limite.fecha_iso == "2026-10-03"

    # Fuera de ventana: 2026-10-04 (día 17) -> Debe rechazarse e indicar la fecha máxima
    res_fuera = resolver.resolver("2026-10-04")
    assert res_fuera.es_valida is False
    assert "excede la ventana máxima" in res_fuera.mensaje_error
    assert res_fuera.fecha_maxima == "2026-10-03"


def test_fecha_en_el_pasado() -> None:
    resolver = DateResolver(base_date="2026-09-18")
    res_pasada = resolver.resolver("2026-09-17")
    assert res_pasada.es_valida is False
    assert "en el pasado" in res_pasada.mensaje_error


def test_fecha_ambigua_solicita_aclaracion() -> None:
    resolver = DateResolver(base_date="2026-09-18")
    res_ambigua = resolver.resolver("05/10/2026")
    assert res_ambigua.es_valida is False
    assert res_ambigua.requiere_aclaracion is True


def test_validar_franjas() -> None:
    resolver = DateResolver(base_date="2026-09-18")
    valida, franja = resolver.validar_franja("08:00")
    assert valida is True
    assert franja == "08:00"

    valida_rango, franja_r = resolver.validar_franja("14:00 - 15:00")
    assert valida_rango is True
    assert franja_r == "14:00"

    invalida, _ = resolver.validar_franja("18:00")
    assert invalida is False
