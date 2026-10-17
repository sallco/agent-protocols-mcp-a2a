"""Regresiones del adaptador; no usan red ni limpian tablas de citas."""
import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from evals import grader_nvidia as grader
from evals import provider_centralizada as provider


def test_grader_uses_nvidia_and_closes_client(monkeypatch):
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    client.chat.completions.create.return_value.choices = [
        SimpleNamespace(message=SimpleNamespace(content='{"category":"C"}'))
    ]
    monkeypatch.setattr(grader, 'OpenAI', factory)
    monkeypatch.setattr(grader, 'get_api_key', lambda: 'test-secret')
    monkeypatch.setattr(grader, 'get_base_url', lambda: 'https://integrate.api.nvidia.com/v1')
    monkeypatch.setattr(grader, 'get_active_model', lambda: 'z-ai/glm-5.3')
    assert grader.call_api('Pregunta')['output'] == '{"category":"C"}'
    assert client.chat.completions.create.call_args.kwargs['model'] == 'z-ai/glm-5.3'
    factory.return_value.__exit__.assert_called_once()


def test_provider_closes_client_inside_live_loop_even_after_failure(monkeypatch):
    closed = []
    async def close():
        closed.append(asyncio.get_running_loop().is_running())
    agent = SimpleNamespace(model=SimpleNamespace(_client=SimpleNamespace(close=close)))
    monkeypatch.setattr(provider, 'construir_agentes_centralizados', lambda _: agent)
    monkeypatch.setattr(provider, 'isolated_agenda', nullcontext)
    monkeypatch.setattr(provider, 'ejecutar_turno_centralizado', AsyncMock(side_effect=RuntimeError('test failure')))
    for _ in range(2):
        result = provider.call_api('test', {}, {})
        assert result['metadata']['error'] == 'RuntimeError: test failure'
    assert closed == [True, True]
