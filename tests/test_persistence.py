"""Pruebas unitarias y de integración para la persistencia transaccional de citas."""

from __future__ import annotations

import uuid
import pytest
from core.persistence import Cita, guardar_cita, listar_citas_fecha, obtener_cita_por_idempotencia


@pytest.mark.parametrize("cita_id", [
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000002",
])
def test_guardar_cita_y_recuperacion_idempotente(agenda_aislada: str, cita_id: str) -> None:
    # Repetir clave y franja exige aislamiento real entre ambos casos.
    idempotency_key = "test-idemp-aislamiento"
    fecha = "2026-09-29"
    hora = "08:00"

    cita = Cita(
        id=cita_id,
        idempotency_key=idempotency_key,
        nombre="Carlos Ruiz",
        fecha=fecha,
        hora=hora,
        veredicto="IDEAL",
        advertencias=[],
        evidencia_clima={"viento": 14.0, "lluvia": 0.0},
        evaluacion_seguridad={"seguro": True},
        arquitectura="centralizada",
    )

    exito, mensaje, cita_guardada = guardar_cita(cita)
    assert exito is True
    assert cita_guardada.id == cita_id

    # Prueba de idempotencia: reintentar con la misma idempotency_key
    exito_reintento, msg_reintento, cita_reintento = guardar_cita(cita)
    assert exito_reintento is True
    assert "idempotencia" in msg_reintento.lower()
    assert cita_reintento.id == cita_id

    # Prueba de franja duplicada con otra idempotency_key
    cita_conflicto = Cita(
        id=str(uuid.uuid4()),
        idempotency_key=f"otro-key-{uuid.uuid4()}",
        nombre="Ana Gómez",
        fecha=fecha,
        hora=hora,  # Mismo día y franja
        veredicto="IDEAL",
        advertencias=[],
        evidencia_clima={"viento": 14.0},
        evaluacion_seguridad={"seguro": True},
        arquitectura="centralizada",
    )
    exito_conflicto, msg_conflicto, _ = guardar_cita(cita_conflicto)
    assert exito_conflicto is False
    assert "ya está ocupada" in msg_conflicto.lower()

    # Listar citas de la fecha
    citas_dia = listar_citas_fecha(fecha)
    assert any(c.id == cita_id for c in citas_dia)


def test_rechazo_veredicto_prohibido_en_bd(agenda_aislada: str) -> None:
    # La restricción SQL CHECK citas_veredicto_valido solo admite IDEAL o MARGINAL
    cita_prohibida = Cita(
        id=str(uuid.uuid4()),
        idempotency_key=f"prohibida-{uuid.uuid4()}",
        nombre="Test Prohibido",
        fecha="2026-09-30",
        hora="09:00",
        veredicto="PROHIBIDO",
        advertencias=["Viento huracanado"],
        evidencia_clima={"viento": 50.0},
        evaluacion_seguridad={"seguro": False},
        arquitectura="centralizada",
    )
    exito, msg, _ = guardar_cita(cita_prohibida)
    assert exito is False
    assert "error de base de datos" in msg.lower() or "check" in msg.lower()
