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
