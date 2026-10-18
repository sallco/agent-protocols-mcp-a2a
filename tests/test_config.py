"""Configuración de servicios sin exigir credenciales del modelo."""

from unittest.mock import MagicMock

import pytest

from core.config import get_settings
from core import llm


@pytest.mark.parametrize("clave", ["", "   "])
def test_servicios_sin_clave_y_modelo_rechazado_antes_de_conectar(monkeypatch, clave):
    monkeypatch.setenv("NVIDIA_API_KEY", clave)
    monkeypatch.setenv("OPENAI_API_KEY", clave)
    factory = MagicMock()
    monkeypatch.setattr(llm, "AsyncOpenAI", factory)

    assert get_settings().api_key == ""
    with pytest.raises(ValueError, match="NVIDIA_API_KEY u OPENAI_API_KEY"):
        llm.create_model()
    factory.assert_not_called()


def test_fecha_historica_del_entorno_no_fija_el_reloj_real(monkeypatch):
    monkeypatch.setenv("BASE_DATE", "2026-09-18")
    assert get_settings().base_date is None


def test_modelo_reutiliza_cliente_del_ciclo_de_vida(monkeypatch):
    cliente = object()
    factory = MagicMock()
    monkeypatch.setattr(llm, "OpenAIChatCompletionsModel", factory)
    monkeypatch.setattr(llm, "get_async_openai_client", MagicMock(side_effect=AssertionError))
    modelo = llm.create_model("modelo-prueba", client=cliente)
    assert modelo is factory.return_value
    factory.assert_called_once_with(
        model="modelo-prueba", openai_client=cliente, strict_feature_validation=False,
    )
