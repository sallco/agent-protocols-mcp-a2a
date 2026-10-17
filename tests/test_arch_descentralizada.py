"""Pruebas unitarias para la arquitectura descentralizada."""

from __future__ import annotations

from arch_descentralizada import construir_red_descentralizada


def test_construccion_arquitectura_descentralizada() -> None:
    faqs, clima, agenda = construir_red_descentralizada()

    assert faqs.name == "agente_faqs"
    assert clima.name == "agente_clima"
    assert agenda.name == "agente_agenda"

    # Verificar que cada agente tiene los handoffs a sus pares configurados
    nombres_handoffs_faqs = [getattr(h, "name", str(h)) for h in faqs.handoffs]
    assert "agente_clima" in nombres_handoffs_faqs
    assert "agente_agenda" in nombres_handoffs_faqs

    nombres_handoffs_clima = [getattr(h, "name", str(h)) for h in clima.handoffs]
    assert "agente_agenda" in nombres_handoffs_clima
    assert "agente_faqs" in nombres_handoffs_clima

    nombres_handoffs_agenda = [getattr(h, "name", str(h)) for h in agenda.handoffs]
    assert "agente_clima" in nombres_handoffs_agenda
    assert "agente_faqs" in nombres_handoffs_agenda
