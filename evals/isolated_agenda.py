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
    table = 'eval_citas_' + uuid4().hex
    settings = replace(original.settings, citas_table=table)
    inicializar_esquema(settings.database_url, table)
    try:
        tools._scheduling_service = SchedulingService(settings)
        yield table
    finally:
        tools._scheduling_service = original
        # Solo se elimina la tabla cuyo UUID se generó en este contexto.
        with psycopg.connect(settings.database_url) as conn:
            conn.execute(sql.SQL('DROP TABLE {}').format(sql.Identifier(table)))
