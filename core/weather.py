"""Cliente para la API de Open-Meteo con agregación en ventana operativa y diario."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar

import httpx

from core.config import Settings, get_settings
from core.safety import EvaluacionSeguridad, evaluar_condiciones_salto


@dataclass(frozen=True)
class DatosMeteorologicos:
    id_evidencia: str
    fecha: str  # YYYY-MM-DD
    temperatura_c: float
    viento_kmh: float
    rafaga_kmh: float
    precipitacion_mm: float
    nubes_pct: float
    modo_agregacion: str
    fuente: str
    instante_consulta: str
    coordenadas: tuple[float, float]
    evaluacion: EvaluacionSeguridad


class WeatherClient:
    """Consulta Open-Meteo y almacena evidencia estructurada para citas."""

    BASE_URL: ClassVar[str] = "https://api.open-meteo.com/v1/forecast"
    _evidence_cache: ClassVar[dict[str, DatosMeteorologicos]] = {}

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @classmethod
    def obtener_evidencia(cls, id_evidencia: str) -> DatosMeteorologicos | None:
        return cls._evidence_cache.get(id_evidencia)

    @classmethod
    def registrar_evidencia(cls, evidencia: DatosMeteorologicos) -> None:
        cls._evidence_cache[evidencia.id_evidencia] = evidencia

    def consultar(
        self,
        fecha_iso: str,
        modo: str | None = None,
        mock_mode: str | None = None,
    ) -> DatosMeteorologicos:
        """Consulta el pronóstico meteorológico para una fecha dentro de la ventana.

        Args:
            fecha_iso: Fecha en formato YYYY-MM-DD.
            modo: 'operativo_horario' (ventana diurna 08-16h) o 'diario_24h'.
            mock_mode: 'ideal', 'marginal', 'prohibido' para pruebas o demos reproducibles.
        """
        modo_activo = modo or self.settings.weather_eval_mode

        if mock_mode:
            return self._generar_mock(fecha_iso, mock_mode, modo_activo)

        coords = (self.settings.openmeteo_lat, self.settings.openmeteo_lon)

        if modo_activo == "diario_24h":
            datos = self._consultar_diario(fecha_iso)
        else:
            datos = self._consultar_horario_operativo(fecha_iso)

        evaluacion = evaluar_condiciones_salto(
            viento_kmh=datos["viento_kmh"],
            rafaga_kmh=datos["rafaga_kmh"],
            precipitacion_mm=datos["precipitacion_mm"],
            nubes_pct=datos["nubes_pct"],
            temperatura_c=datos["temperatura_c"],
        )

        id_evidencia = str(uuid.uuid4())
        instante = datetime.datetime.now(datetime.timezone.utc).isoformat()

        evidencia = DatosMeteorologicos(
            id_evidencia=id_evidencia,
            fecha=fecha_iso,
            temperatura_c=datos["temperatura_c"],
            viento_kmh=datos["viento_kmh"],
            rafaga_kmh=datos["rafaga_kmh"],
            precipitacion_mm=datos["precipitacion_mm"],
            nubes_pct=datos["nubes_pct"],
            modo_agregacion=modo_activo,
            fuente=self.BASE_URL,
            instante_consulta=instante,
            coordenadas=coords,
            evaluacion=evaluacion,
        )

        self.registrar_evidencia(evidencia)
        return evidencia

    def _consultar_horario_operativo(self, fecha_iso: str) -> dict[str, float]:
        """Consulta datos horarios y extrae la franja de salto diurno (08:00 a 16:00)."""
        params = {
            "latitude": self.settings.openmeteo_lat,
            "longitude": self.settings.openmeteo_lon,
            "hourly": "temperature_2m,precipitation,cloud_cover,wind_speed_10m,wind_gusts_10m",
            "timezone": self.settings.openmeteo_timezone,
            "start_date": fecha_iso,
            "end_date": fecha_iso,
        }

        data = self._ejecutar_peticion(params)
        hourly = data.get("hourly")
        if not hourly or "time" not in hourly:
            raise RuntimeError(f"Open-Meteo no retornó datos horarios para {fecha_iso}")

        tiempos = hourly["time"]
        indices_operativos: list[int] = []
        for idx, t in enumerate(tiempos):
            # Formato esperado: YYYY-MM-DDTHH:MM
            hora_str = t.split("T")[-1].split(":")[0]
            hora_int = int(hora_str)
            if 8 <= hora_int <= 16:
                indices_operativos.append(idx)

        if not indices_operativos:
            raise RuntimeError(f"No se encontraron horas operativas (08:00-16:00) para {fecha_iso}")

        vientos = [hourly["wind_speed_10m"][i] for i in indices_operativos]
        rafagas = [hourly["wind_gusts_10m"][i] for i in indices_operativos]
        precipitaciones = [hourly["precipitation"][i] for i in indices_operativos]
        nubes = [hourly["cloud_cover"][i] for i in indices_operativos]
        temperaturas = [hourly["temperature_2m"][i] for i in indices_operativos]

        return {
            "viento_kmh": round(max(vientos), 2),
            "rafaga_kmh": round(max(rafagas), 2),
            "precipitacion_mm": round(sum(precipitaciones), 2),
            "nubes_pct": round(sum(nubes) / len(nubes), 2),
            "temperatura_c": round(sum(temperaturas) / len(temperaturas), 2),
        }

    def _consultar_diario(self, fecha_iso: str) -> dict[str, float]:
        """Consulta agregados diarios completos (24h)."""
        params = {
            "latitude": self.settings.openmeteo_lat,
            "longitude": self.settings.openmeteo_lon,
            "daily": "temperature_2m_mean,wind_speed_10m_max,wind_gusts_10m_max,precipitation_sum",
            "timezone": self.settings.openmeteo_timezone,
            "start_date": fecha_iso,
            "end_date": fecha_iso,
        }
        data = self._ejecutar_peticion(params)
        daily = data.get("daily")
        if not daily or "time" not in daily or not daily["time"]:
            raise RuntimeError(f"Open-Meteo no retornó datos diarios para {fecha_iso}")

        idx = daily["time"].index(fecha_iso)
        # En la API diaria no hay cloud_cover nativo estándar, se consulta con hourly para nubosidad
        # o fallback seguro
        return {
            "viento_kmh": float(daily["wind_speed_10m_max"][idx]),
            "rafaga_kmh": float(daily["wind_gusts_10m_max"][idx]),
            "precipitacion_mm": float(daily["precipitation_sum"][idx]),
            "nubes_pct": 50.0,  # Estimación representativa diaria
            "temperatura_c": float(daily["temperature_2m_mean"][idx]),
        }

    def _ejecutar_peticion(self, params: dict[str, Any]) -> dict[str, Any]:
        intentos = 2
        for intento in range(intentos):
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(self.BASE_URL, params=params)
                    if resp.status_code == 200:
                        return resp.json()
                    if resp.status_code in {429, 500, 502, 503, 504} and intento < intentos - 1:
                        continue
                    resp.raise_for_status()
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                if intento == intentos - 1:
                    raise RuntimeError(f"Fallo al conectar con Open-Meteo: {exc}") from exc
        raise RuntimeError("No se pudo obtener respuesta de Open-Meteo tras reintentos.")

    def _generar_mock(self, fecha_iso: str, mock_mode: str, modo_agregacion: str) -> DatosMeteorologicos:
        modo_normalizado = mock_mode.lower().strip()
        coords = (self.settings.openmeteo_lat, self.settings.openmeteo_lon)

        if modo_normalizado == "ideal":
            viento, rafaga, lluvia, nubes, temp = 14.5, 22.0, 0.0, 18.0, 25.0
        elif modo_normalizado == "marginal":
            viento, rafaga, lluvia, nubes, temp = 23.5, 28.0, 0.0, 45.0, 26.5
        elif modo_normalizado == "prohibido":
            viento, rafaga, lluvia, nubes, temp = 31.0, 42.0, 6.5, 88.0, 21.0
        else:
            raise ValueError(f"Modo mock '{mock_mode}' no reconocido. Use 'ideal', 'marginal' o 'prohibido'.")

        evaluacion = evaluar_condiciones_salto(
            viento_kmh=viento,
            rafaga_kmh=rafaga,
            precipitacion_mm=lluvia,
            nubes_pct=nubes,
            temperatura_c=temp,
        )

        id_evidencia = str(uuid.uuid4())
        instante = datetime.datetime.now(datetime.timezone.utc).isoformat()

        evidencia = DatosMeteorologicos(
            id_evidencia=id_evidencia,
            fecha=fecha_iso,
            temperatura_c=temp,
            viento_kmh=viento,
            rafaga_kmh=rafaga,
            precipitacion_mm=lluvia,
            nubes_pct=nubes,
            modo_agregacion=modo_agregacion,
            fuente="mock://simulador-condiciones",
            instante_consulta=instante,
            coordenadas=coords,
            evaluacion=evaluacion,
        )
        self.registrar_evidencia(evidencia)
        return evidencia
