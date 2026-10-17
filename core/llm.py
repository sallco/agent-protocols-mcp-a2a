"""Configuración y fábrica del cliente LLM para NVIDIA NIM / OpenAI-compatible."""

from __future__ import annotations

import os
from typing import Sequence

from agents import OpenAIChatCompletionsModel, set_tracing_disabled
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

# Desactivar telemetría y exportación de trazas a OpenAI antes de instanciar agentes
set_tracing_disabled(True)

DEFAULT_MODELS: list[str] = [
    "z-ai/glm-5.3",
    "z-ai/glm-5.3-flash",
]


_ACTIVE_MODEL: str | None = None


def get_base_url() -> str:
    openai_base = os.getenv("OPENAI_BASE_URL")
    nvidia_base = os.getenv("NVIDIA_BASE_URL")
    if openai_base and nvidia_base and openai_base.strip() != nvidia_base.strip():
        raise ValueError(
            f"Conflicto de configuración: OPENAI_BASE_URL ({openai_base}) y "
            f"NVIDIA_BASE_URL ({nvidia_base}) tienen valores diferentes."
        )
    base_url = openai_base or nvidia_base or "https://integrate.api.nvidia.com/v1"
    return base_url.strip()


def get_api_key() -> str:
    base_url = get_base_url()
    if "nvidia.com" in base_url.lower():
        api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("OPENAI_API_KEY")
    else:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise ValueError("No se encontró NVIDIA_API_KEY u OPENAI_API_KEY en el entorno.")
    return api_key.strip()


def get_configured_models() -> list[str]:
    primary_model = os.getenv("MODEL") or os.getenv("NVIDIA_MODEL")
    fallbacks_raw = os.getenv("MODEL_FALLBACKS", "")
    fallbacks = [m.strip() for m in fallbacks_raw.split(",") if m.strip()]

    candidates: list[str] = []
    configured = []
    if primary_model and primary_model.strip():
        configured.append(primary_model.strip())
    configured.extend(fallback for fallback in fallbacks if fallback not in configured)
    for modelo in configured:
        if modelo in DEFAULT_MODELS:
            candidates.append(modelo)
    for default in DEFAULT_MODELS:
        if default not in candidates:
            candidates.append(default)
    return candidates


def set_active_model(model_name: str) -> None:
    global _ACTIVE_MODEL
    _ACTIVE_MODEL = model_name


def get_active_model() -> str:
    global _ACTIVE_MODEL
    if _ACTIVE_MODEL:
        return _ACTIVE_MODEL
    candidates = get_configured_models()
    return candidates[0] if candidates else DEFAULT_MODELS[0]


def get_async_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=get_base_url(),
        api_key=get_api_key(),
    )


def create_model(model_name: str | None = None) -> OpenAIChatCompletionsModel:
    """Crea una instancia de OpenAIChatCompletionsModel vinculada a AsyncOpenAI."""
    chosen_model = model_name or get_active_model()
    client = get_async_openai_client()
    return OpenAIChatCompletionsModel(
        model=chosen_model,
        openai_client=client,
        strict_feature_validation=False,
    )
