"""Persistencia transaccional de citas en PostgreSQL."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from core.config import Settings, get_settings


@dataclass(frozen=True)
class Cita:
    id: str
    idempotency_key: str
    nombre: str
    fecha: str  # YYYY-MM-DD
    hora: str   # HH:00
    veredicto: str
    advertencias: list[str]
    evidencia_clima: dict[str, Any]
    evaluacion_seguridad: dict[str, Any]
    arquitectura: str
    creado_en: str | None = None


def inicializar_esquema(database_url: str | None = None, table_name: str | None = None) -> None:
    settings = get_settings()
    url = database_url or settings.database_url
    tabla = table_name or settings.citas_table

    migration_file = Path(__file__).parent.parent / "db" / "002_citas.sql"
    migration_sql = migration_file.read_text(encoding="utf-8")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            # Si el nombre de la tabla configurada es distinto a 'citas', reemplazamos
            if tabla != "citas":
                migration_sql = migration_sql.replace("citas", tabla)
            cur.execute(migration_sql)
        conn.commit()


def obtener_cita_por_idempotencia(
    idempotency_key: str, database_url: str | None = None, table_name: str | None = None
) -> Cita | None:
    settings = get_settings()
    url = database_url or settings.database_url
    tabla = table_name or settings.citas_table

    query = sql.SQL("""
        SELECT id, idempotency_key, nombre, fecha::text, hora, veredicto,
               advertencias, evidencia_clima, evaluacion_seguridad, arquitectura, creado_en::text
        FROM {table}
        WHERE idempotency_key = %s
    """).format(table=sql.Identifier(tabla))

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (idempotency_key,))
            row = cur.fetchone()
            if not row:
                return None
            return Cita(
                id=str(row[0]),
                idempotency_key=str(row[1]),
                nombre=str(row[2]),
                fecha=str(row[3]),
                hora=str(row[4]),
                veredicto=str(row[5]),
                advertencias=row[6] if isinstance(row[6], list) else json.loads(row[6]),
                evidencia_clima=row[7] if isinstance(row[7], dict) else json.loads(row[7]),
                evaluacion_seguridad=row[8] if isinstance(row[8], dict) else json.loads(row[8]),
                arquitectura=str(row[9]),
                creado_en=str(row[10]),
            )


def listar_citas_fecha(
    fecha_iso: str, database_url: str | None = None, table_name: str | None = None
) -> list[Cita]:
    settings = get_settings()
    url = database_url or settings.database_url
    tabla = table_name or settings.citas_table

    query = sql.SQL("""
        SELECT id, idempotency_key, nombre, fecha::text, hora, veredicto,
               advertencias, evidencia_clima, evaluacion_seguridad, arquitectura, creado_en::text
        FROM {table}
        WHERE fecha = %s
        ORDER BY hora ASC
    """).format(table=sql.Identifier(tabla))

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(query, (fecha_iso,))
            rows = cur.fetchall()
            citas: list[Cita] = []
            for row in rows:
                citas.append(
                    Cita(
                        id=str(row[0]),
                        idempotency_key=str(row[1]),
                        nombre=str(row[2]),
                        fecha=str(row[3]),
                        hora=str(row[4]),
                        veredicto=str(row[5]),
                        advertencias=row[6] if isinstance(row[6], list) else json.loads(row[6]),
                        evidencia_clima=row[7] if isinstance(row[7], dict) else json.loads(row[7]),
                        evaluacion_seguridad=row[8] if isinstance(row[8], dict) else json.loads(row[8]),
                        arquitectura=str(row[9]),
                        creado_en=str(row[10]),
                    )
                )
            return citas


def guardar_cita(
    cita: Cita, database_url: str | None = None, table_name: str | None = None
) -> tuple[bool, str, Cita]:
    """Guarda una cita transaccionalmente respetando unicidad de franja e idempotencia.

    Retorna: (exito, mensaje, cita_resultante)
    """
    settings = get_settings()
    url = database_url or settings.database_url
    tabla = table_name or settings.citas_table

    # 1. Comprobación de idempotencia previa
    existente = obtener_cita_por_idempotencia(cita.idempotency_key, url, tabla)
    if existente:
        return True, "Cita recuperada por clave de idempotencia existente.", existente

    query = sql.SQL("""
        INSERT INTO {table} (
            id, idempotency_key, nombre, fecha, hora, veredicto,
            advertencias, evidencia_clima, evaluacion_seguridad, arquitectura
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """).format(table=sql.Identifier(tabla))

    params = (
        cita.id,
        cita.idempotency_key,
        cita.nombre,
        cita.fecha,
        cita.hora,
        cita.veredicto,
        Jsonb(cita.advertencias),
        Jsonb(cita.evidencia_clima),
        Jsonb(cita.evaluacion_seguridad),
        cita.arquitectura,
    )

    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()
        return True, "Cita agendada con éxito.", cita
    except psycopg.errors.UniqueViolation as exc:
        err_msg = str(exc).lower()
        if "citas_franja_unica" in err_msg or "fecha" in err_msg:
            return False, f"La franja horaria {cita.hora} para el día {cita.fecha} ya está ocupada.", cita
        if "idempotency" in err_msg:
            existente = obtener_cita_por_idempotencia(cita.idempotency_key, url, tabla)
            if existente:
                return True, "Cita recuperada por idempotencia concurrente.", existente
        return False, f"Conflicto de unicidad al agendar cita: {exc}", cita
    except psycopg.Error as exc:
        return False, f"Error de base de datos al registrar cita: {exc}", cita
