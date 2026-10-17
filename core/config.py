"""Configuración unificada y validación de variables de entorno para el proyecto."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Proveedor LLM (NVIDIA NIM / OpenAI-compatible)
    database_url: str
    model: str
    api_key: str
    base_url: str
    model_fallbacks: list[str]

    # Almacenamiento vectorial y persistencia
    faq_table: str
    citas_table: str
    embedding_model: str
    minimum_similarity: float

    # Open-Meteo y condiciones de salto
    openmeteo_lat: float
    openmeteo_lon: float
    openmeteo_timezone: str
    forecast_max_days: int
    base_date: str
    weather_eval_mode: str

    @classmethod
    def from_env(cls) -> "Settings":
        openai_base = os.getenv("OPENAI_BASE_URL")
        nvidia_base = os.getenv("NVIDIA_BASE_URL")
        if openai_base and nvidia_base and openai_base.strip() != nvidia_base.strip():
            raise ValueError(
                f"Conflicto de configuración: OPENAI_BASE_URL ({openai_base}) y "
                f"NVIDIA_BASE_URL ({nvidia_base}) tienen valores diferentes."
            )
        base_url = openai_base or nvidia_base or "https://integrate.api.nvidia.com/v1"

        if "nvidia.com" in base_url.lower():
            api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("OPENAI_API_KEY")
        else:
            api_key = os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY")

        database_url = os.getenv("DATABASE_URL", "postgresql://parachute:parachutepass@localhost:5432/parachutedb")
        model = os.getenv("MODEL", "z-ai/glm-5.3")
        fallbacks_raw = os.getenv(
            "MODEL_FALLBACKS",
            "z-ai/glm-5.3-flash",
        )
        model_fallbacks = [m.strip() for m in fallbacks_raw.split(",") if m.strip()]

        faq_table = os.getenv("FAQ_TABLE", "faqs")
        citas_table = os.getenv("CITAS_TABLE", "citas")
        embedding_model = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
        min_sim_raw = os.getenv("MINIMUM_SIMILARITY", "0.6")

        missing: list[str] = []
        if not api_key:
            missing.append("NVIDIA_API_KEY u OPENAI_API_KEY")
        if not database_url:
            missing.append("DATABASE_URL")
        if missing:
            raise RuntimeError(f"Faltan variables en .env: {', '.join(missing)}")

        if not faq_table.isidentifier():
            raise ValueError(f"FAQ_TABLE debe ser un identificador SQL válido, recibido: {faq_table}")
        if not citas_table.isidentifier():
            raise ValueError(f"CITAS_TABLE debe ser un identificador SQL válido, recibido: {citas_table}")

        try:
            minimum_similarity = float(min_sim_raw)
        except ValueError as exc:
            raise ValueError("MINIMUM_SIMILARITY debe ser un número flotante entre 0 y 1.") from exc

        if not (0.0 <= minimum_similarity <= 1.0):
            raise ValueError("MINIMUM_SIMILARITY debe estar comprendido entre 0.0 y 1.0.")

        openmeteo_lat = float(os.getenv("OPENMETEO_LAT", "14.013722"))
        openmeteo_lon = float(os.getenv("OPENMETEO_LON", "-90.771611"))
        openmeteo_timezone = os.getenv("OPENMETEO_TIMEZONE", "America/Guatemala")
        forecast_max_days = int(os.getenv("FORECAST_MAX_DAYS", "16"))
        base_date = os.getenv("BASE_DATE", "2026-09-18")
        weather_eval_mode = os.getenv("WEATHER_EVAL_MODE", "operativo_horario")

        return cls(
            database_url=database_url,
            model=model,
            api_key=api_key.strip(),
            base_url=base_url.strip(),
            model_fallbacks=model_fallbacks,
            faq_table=faq_table,
            citas_table=citas_table,
            embedding_model=embedding_model,
            minimum_similarity=minimum_similarity,
            openmeteo_lat=openmeteo_lat,
            openmeteo_lon=openmeteo_lon,
            openmeteo_timezone=openmeteo_timezone,
            forecast_max_days=forecast_max_days,
            base_date=base_date,
            weather_eval_mode=weather_eval_mode,
        )


def get_settings() -> Settings:
    return Settings.from_env()
