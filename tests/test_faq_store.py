"""Pruebas unitarias para Settings y FAQStore."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from core.config import Settings
from core.faq_store import FAQStore


def test_settings_validation_invalid_table() -> None:
    with patch.dict(os.environ, {"FAQ_TABLE": "faqs; DROP TABLE faqs;--"}):
        with pytest.raises(ValueError, match="identificador SQL válido"):
            Settings.from_env()


def test_settings_validation_similarity_range() -> None:
    with patch.dict(os.environ, {"MINIMUM_SIMILARITY": "1.5"}):
        with pytest.raises(ValueError, match="comprendido entre 0.0 y 1.0"):
            Settings.from_env()


def test_evaluar_calidad_faqs_inconsistentes() -> None:
    settings = Settings.from_env()
    faq_store = FAQStore(settings=settings)

    assert faq_store._evaluar_calidad("FAQ-103", "El viento es de 200 km/h.") == "inconsistente"
    assert faq_store._evaluar_calidad("FAQ-025", "No hay edad límite.") == "inconsistente"
    assert faq_store._evaluar_calidad("FAQ-039", "Respirar profundo.") == "inconsistente"


def test_evaluar_calidad_faqs_insuficientes_o_validas() -> None:
    settings = Settings.from_env()
    faq_store = FAQStore(settings=settings)

    assert faq_store._evaluar_calidad("FAQ-001", "Texto corto") == "insuficiente"
    assert faq_store._evaluar_calidad("FAQ-002", "Lorem ipsum dolor sit amet consectetur adipiscing") == "insuficiente"
    assert faq_store._evaluar_calidad("FAQ-003", "El peso máximo permitido para saltar tándem es de 95 kg.") == "valida"
