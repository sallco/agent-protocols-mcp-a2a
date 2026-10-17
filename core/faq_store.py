"""Buscador semántico de FAQs en PostgreSQL + pgvector con filtro de calidad."""

from __future__ import annotations

import re
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from sentence_transformers import SentenceTransformer

from core.config import Settings, get_settings

# IDs de FAQs con contradicciones o inconsistencias conocidas según análisis del corpus
FAQS_INCONSISTENTES: set[str] = {
    "FAQ-025",  # Respuesta no responde sobre la edad máxima
    "FAQ-039",  # Respuesta no responde sobre manejo de ansiedad
    "FAQ-103",  # Cita 200 km/h (velocidad de caída libre) en lugar de límite de viento
}


class FAQStore:
    """Acceso y recuperación semántica de FAQs con evaluación de calidad."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._encoder: SentenceTransformer | None = None

    @property
    def encoder(self) -> SentenceTransformer:
        if self._encoder is None:
            self._encoder = SentenceTransformer(self.settings.embedding_model)
        return self._encoder

    def _evaluar_calidad(self, faq_id: str, respuesta: str) -> str:
        """Determina el estado de calidad de una FAQ recuperada."""
        if faq_id in FAQS_INCONSISTENTES:
            return "inconsistente"
        # Detección de respuestas de relleno o vacías
        resp_limpia = respuesta.strip().lower()
        if len(resp_limpia) < 15 or "lorem" in resp_limpia or "texto de relleno" in resp_limpia:
            return "insuficiente"
        return "valida"

    def buscar(self, consulta: str, limite: int = 3) -> list[dict[str, Any]]:
        """Realiza búsqueda por similitud coseno sobre la tabla de FAQs."""
        limite = max(1, min(int(limite), 5))
        consulta_normalizada = re.sub(r"([?!])\1+", r"\1", consulta.strip())
        if not consulta_normalizada:
            return []

        embedding = self.encoder.encode(consulta_normalizada, normalize_embeddings=True).tolist()

        # Construcción segura de la consulta SQL utilizando sql.Identifier
        query = sql.SQL("""
            SELECT id, categoria, pregunta, respuesta, metadata,
                   1 - (embedding <=> %s::vector) AS similitud
            FROM {table}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """).format(table=sql.Identifier(self.settings.faq_table))

        try:
            with psycopg.connect(self.settings.database_url) as connection:
                register_vector(connection)
                with connection.cursor() as cursor:
                    cursor.execute(query, (embedding, embedding, limite))
                    if not cursor.description:
                        return []
                    columns = [column.name for column in cursor.description]
                    rows = cursor.fetchall()
                    results: list[dict[str, Any]] = []
                    for row in rows:
                        item = dict(zip(columns, row))
                        item["similitud"] = float(item["similitud"])
                        item["estado_calidad"] = self._evaluar_calidad(
                            str(item["id"]), str(item["respuesta"])
                        )
                        results.append(item)

                    return [
                        r for r in results if r["similitud"] >= self.settings.minimum_similarity
                    ]
        except psycopg.Error as exc:
            raise RuntimeError(f"Error de base de datos al buscar FAQs: {exc}") from exc
