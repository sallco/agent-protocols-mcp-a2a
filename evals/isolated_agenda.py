"""Agenda PostgreSQL nueva por caso, sin tocar las citas del usuario."""
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4

import psycopg
from psycopg import sql
from core.persistence import inicializar_esquema
from core.scheduling import SchedulingService
import core.tools as tools


@contextmanager
def isolated_agenda():
    original = tools._scheduling_service
    original_resolver = tools._date_resolver
    table = 'eval_citas_' + uuid4().hex
    settings = replace(original.settings, citas_table=table, base_date='2026-09-18')
    inicializar_esquema(settings.database_url, table)
    try:
        tools._scheduling_service = SchedulingService(settings)
        tools._date_resolver = tools._scheduling_service.date_resolver
        yield table
    finally:
        tools._scheduling_service = original
        tools._date_resolver = original_resolver
        # Solo se elimina la tabla cuyo UUID se generó en este contexto.
        with psycopg.connect(settings.database_url) as conn:
            conn.execute(sql.SQL('DROP TABLE {}').format(sql.Identifier(table)))
