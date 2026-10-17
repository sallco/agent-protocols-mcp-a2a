"""Suite de pruebas de integración para concurrencia, idempotencia y reglas de seguridad."""

from __future__ import annotations

import concurrent.futures
import uuid
import pytest

from core.dates import DateResolver
from core.faq_store import FAQStore
from core.persistence import Cita, guardar_cita, listar_citas_fecha
from core.safety import Veredicto, evaluar_condiciones_salto
from core.scheduling import SchedulingService
from core.weather import WeatherClient


def test_concurrencia_dos_reservas_misma_franja() -> None:
    """Dos intentos concurrentes para exactamente la misma franja deben resultar en 1 reserva."""
    weather_client = WeatherClient()
    evidencia = weather_client.consultar("2026-09-29", mock_mode="ideal")
    service = SchedulingService()

    fecha = "2026-09-29"
    hora = "15:00"  # Franja a disputar

    def intentar_reserva(nombre: str) -> bool:
        res = service.agendar_cita(
            nombre=nombre,
            fecha_iso=fecha,
            hora=hora,
            id_evidencia=evidencia.id_evidencia,
            arquitectura="centralizada",
        )
        return res.exito

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(intentar_reserva, "Usuario Concurrente 1")
        f2 = executor.submit(intentar_reserva, "Usuario Concurrente 2")
        resultados = [f1.result(), f2.result()]

    # Exactamente una reserva exitosa y una rechazada
    assert resultados.count(True) == 1
    assert resultados.count(False) == 1

    # Verificar que solo hay 1 registro para las 15:00 en esa fecha
    citas_dia = service.listar_citas(fecha)
    citas_franja = [c for c in citas_dia if c["hora"] == hora]
    assert len(citas_franja) == 1


def test_reintento_idempotente_misma_clave() -> None:
    """Reintentar con la misma clave de idempotencia retorna el mismo ID sin duplicar."""
    weather_client = WeatherClient()
    evidencia = weather_client.consultar("2026-09-29", mock_mode="ideal")
    service = SchedulingService()

    idemp_key = f"idemp-test-{uuid.uuid4()}"

    res1 = service.agendar_cita(
        nombre="Sofía Castillo",
        fecha_iso="2026-09-29",
        hora="09:00",
        id_evidencia=evidencia.id_evidencia,
        arquitectura="centralizada",
        idempotency_key=idemp_key,
    )
    assert res1.exito is True

    # Segundo intento con idéntica clave de idempotencia
    res2 = service.agendar_cita(
        nombre="Sofía Castillo",
        fecha_iso="2026-09-29",
        hora="09:00",
        id_evidencia=evidencia.id_evidencia,
        arquitectura="centralizada",
        idempotency_key=idemp_key,
    )
    assert res2.exito is True
    assert res2.id_cita == res1.id_cita


def test_aislamiento_de_faq_103_frente_a_seguridad() -> None:
    """FAQ-103 cita 200 km/h; el evaluador de seguridad debe rechazar vientos > 28 km/h."""
    faq_store = FAQStore()
    assert faq_store._evaluar_calidad("FAQ-103", "200 km/h") == "inconsistente"

    # Si alguien quisiera saltar con 30 km/h (menor a 200 km/h de la FAQ pero mayor a 28 km/h de seguridad)
    evaluacion = evaluar_condiciones_salto(
        viento_kmh=30.0,
        rafaga_kmh=25.0,
        precipitacion_mm=0.0,
        nubes_pct=20.0,
        temperatura_c=24.0,
    )
    # Debe ser PROHIBIDO
    assert evaluacion.veredicto_global == Veredicto.PROHIBIDO
    assert evaluacion.es_seguro_saltar is False


def test_reserva_marginal_con_advertencia_persistida() -> None:
    """Una reserva en condiciones marginales debe persistirse con su advertencia de tándem."""
    weather_client = WeatherClient()
    evidencia = weather_client.consultar("2026-09-29", mock_mode="marginal")
    service = SchedulingService()

    res = service.agendar_cita(
        nombre="Esteban Prado",
        fecha_iso="2026-09-29",
        hora="08:00",
        id_evidencia=evidencia.id_evidencia,
        arquitectura="jerarquica",
    )
    assert res.exito is True
    assert res.veredicto == "MARGINAL"
    assert any("solo tándem experimentado" in adv for adv in (res.advertencias or []))


def test_limites_ventana_con_reloj_fijo() -> None:
    """Prueba transversal de la ventana de 16 días con base 2026-09-18."""
    resolver = DateResolver(base_date="2026-09-18")

    # 1. Fecha del evento
    assert resolver.resolver("2026-09-29").es_valida is True

    # 2. Último día de ventana
    assert resolver.resolver("2026-10-03").es_valida is True

    # 3. Día siguiente (fuera de ventana)
    res_fuera = resolver.resolver("2026-10-04")
    assert res_fuera.es_valida is False
    assert res_fuera.fecha_maxima == "2026-10-03"
