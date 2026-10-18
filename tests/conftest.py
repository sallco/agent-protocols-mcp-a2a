"""Configuración y fixtures compartidos de pruebas."""

from __future__ import annotations

import sys
from dataclasses import replace
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from core.config import get_settings
from core.dates import DateResolver
from core.persistence import inicializar_esquema


@pytest.fixture(autouse=True)
def tabla_citas_prueba(monkeypatch):
    """Usa una tabla propia y un reloj histórico explícito, sin abrir conexiones."""
    tabla = "test_citas_" + uuid4().hex
    monkeypatch.setenv("CITAS_TABLE", tabla)
    monkeypatch.setattr(
        "core.scheduling.get_settings",
        lambda: replace(get_settings(), base_date="2026-09-18"),
    )

    # Las herramientas pueden haberse importado durante la colección de pruebas.
    tools = sys.modules.get("core.tools")
    if tools is not None:
        service = tools._scheduling_service
        monkeypatch.setattr(tools, "_scheduling_service", service)
        monkeypatch.setattr(
            service, "settings",
            replace(service.settings, citas_table=tabla, base_date="2026-09-18"),
        )
        resolver = DateResolver(base_date="2026-09-18")
        monkeypatch.setattr(service, "date_resolver", resolver)
        monkeypatch.setattr(tools, "_date_resolver", resolver)

    return tabla


@pytest.fixture
def agenda_aislada(tabla_citas_prueba):
    """Crea y elimina únicamente la tabla de la prueba que requiere PostgreSQL."""
    settings = get_settings()
    inicializar_esquema(settings.database_url, tabla_citas_prueba)
    try:
        yield tabla_citas_prueba
    finally:
        with psycopg.connect(settings.database_url) as conn:
            conn.execute(
                sql.SQL("DROP TABLE {}").format(sql.Identifier(tabla_citas_prueba))
            )
