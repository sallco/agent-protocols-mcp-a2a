"""Configuración y fixtures compartidos de pruebas."""

from __future__ import annotations

import psycopg
import pytest
from core.config import get_settings


@pytest.fixture(autouse=True)
def limpiar_citas_entre_pruebas():
    """Limpia la tabla de citas antes de cada prueba para evitar colisiones de franjas."""
    settings = get_settings()
    try:
        with psycopg.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM citas WHERE nombre LIKE 'Test%' OR nombre LIKE '%Concurrente%' OR nombre LIKE '%Carlos%' OR nombre LIKE '%Lucía%' OR nombre LIKE '%Sofía%' OR nombre LIKE '%Valeria%' OR nombre LIKE '%Esteban%'")
            conn.commit()
    except Exception:
        pass
    yield
