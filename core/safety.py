"""Evaluador determinista de condiciones meteorológicas para salto en paracaídas."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Veredicto(str, Enum):
    IDEAL = "IDEAL"
    MARGINAL = "MARGINAL"
    PROHIBIDO = "PROHIBIDO"


@dataclass(frozen=True)
class EvaluacionSeguridad:
    veredicto_global: Veredicto
    es_seguro_saltar: bool  # True para IDEAL o MARGINAL; False para PROHIBIDO
    motivos: list[str]
    advertencias: list[str]
    clasificacion_variables: dict[str, str]
    datos_normalizados: dict[str, float]


def _validar_numero(valor: Any, nombre: str, minimo: float | None = None, maximo: float | None = None) -> float:
    try:
        val = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"El valor de {nombre} ({valor}) no es un número válido.") from exc

    if math.isnan(val) or math.isinf(val):
        raise ValueError(f"El valor de {nombre} no puede ser NaN ni infinito.")

    if minimo is not None and val < minimo:
        raise ValueError(f"El valor de {nombre} ({val}) no puede ser menor a {minimo}.")
    if maximo is not None and val > maximo:
        raise ValueError(f"El valor de {nombre} ({val}) no puede ser mayor a {maximo}.")

    return val


def evaluar_condiciones_salto(
    viento_kmh: float,
    rafaga_kmh: float,
    precipitacion_mm: float,
    nubes_pct: float,
    temperatura_c: float,
) -> EvaluacionSeguridad:
    """Evalúa determinísticamente las variables meteorológicas según las reglas de seguridad.

    Umbrales aplicados:
    - Viento: < 20 IDEAL, [20, 28] MARGINAL, > 28 PROHIBIDO
    - Ráfagas: <= 35 IDEAL, > 35 PROHIBIDO
    - Precipitación: 0.0 IDEAL, > 0.0 PROHIBIDO
    - Nubes: < 30 IDEAL, [30, 75] MARGINAL, > 75 PROHIBIDO
    - Temperatura: Informativa, no veta.
    """
    v_viento = _validar_numero(viento_kmh, "viento_kmh", minimo=0.0)
    v_rafaga = _validar_numero(rafaga_kmh, "rafaga_kmh", minimo=0.0)
    v_precipitacion = _validar_numero(precipitacion_mm, "precipitacion_mm", minimo=0.0)
    v_nubes = _validar_numero(nubes_pct, "nubes_pct", minimo=0.0, maximo=100.0)
    v_temperatura = _validar_numero(temperatura_c, "temperatura_c")

    clasificacion: dict[str, str] = {}
    motivos: list[str] = []
    advertencias: list[str] = []
    estados: list[Veredicto] = []

    # 1. Viento en superficie
    if v_viento < 20.0:
        clasificacion["viento"] = Veredicto.IDEAL.value
        estados.append(Veredicto.IDEAL)
    elif 20.0 <= v_viento <= 28.0:
        clasificacion["viento"] = Veredicto.MARGINAL.value
        estados.append(Veredicto.MARGINAL)
        motivos.append(f"Viento en superficie ({v_viento:.1f} km/h) en rango marginal [20-28 km/h].")
        advertencias.append("Viento marginal: solo tándem experimentado.")
    else:
        clasificacion["viento"] = Veredicto.PROHIBIDO.value
        estados.append(Veredicto.PROHIBIDO)
        motivos.append(f"Viento en superficie ({v_viento:.1f} km/h) excede el límite máximo de 28 km/h.")

    # 2. Ráfagas de viento
    if v_rafaga <= 35.0:
        clasificacion["rafagas"] = Veredicto.IDEAL.value
        estados.append(Veredicto.IDEAL)
    else:
        clasificacion["rafagas"] = Veredicto.PROHIBIDO.value
        estados.append(Veredicto.PROHIBIDO)
        motivos.append(f"Ráfagas de viento ({v_rafaga:.1f} km/h) superan el umbral crítico de 35 km/h.")

    # 3. Precipitación
    if v_precipitacion == 0.0:
        clasificacion["precipitacion"] = Veredicto.IDEAL.value
        estados.append(Veredicto.IDEAL)
    else:
        clasificacion["precipitacion"] = Veredicto.PROHIBIDO.value
        estados.append(Veredicto.PROHIBIDO)
        motivos.append(f"Precipitación detectada ({v_precipitacion:.1f} mm); prohibido saltar con lluvia.")

    # 4. Cobertura de nubes (proxy de visibilidad)
    if v_nubes < 30.0:
        clasificacion["nubes"] = Veredicto.IDEAL.value
        estados.append(Veredicto.IDEAL)
    elif 30.0 <= v_nubes <= 75.0:
        clasificacion["nubes"] = Veredicto.MARGINAL.value
        estados.append(Veredicto.MARGINAL)
        motivos.append(f"Cobertura nubosa ({v_nubes:.1f}%) en rango marginal [30%-75%].")
        advertencias.append("Nubosidad moderada: visibilidad reducida respecto al óptimo.")
    else:
        clasificacion["nubes"] = Veredicto.PROHIBIDO.value
        estados.append(Veredicto.PROHIBIDO)
        motivos.append(f"Cobertura nubosa excesiva ({v_nubes:.1f}% > 75%); no se garantiza visibilidad de salto.")

    # 5. Temperatura (informativa, sin veto)
    clasificacion["temperatura"] = "INFORMATIVO"

    # Composición del peor estado
    if Veredicto.PROHIBIDO in estados:
        veredicto_global = Veredicto.PROHIBIDO
        es_seguro = False
    elif Veredicto.MARGINAL in estados:
        veredicto_global = Veredicto.MARGINAL
        es_seguro = True
    else:
        veredicto_global = Veredicto.IDEAL
        es_seguro = True
        motivos.append("Todas las condiciones se encuentran dentro de los parámetros ideales.")

    return EvaluacionSeguridad(
        veredicto_global=veredicto_global,
        es_seguro_saltar=es_seguro,
        motivos=motivos,
        advertencias=advertencias,
        clasificacion_variables=clasificacion,
        datos_normalizados={
            "viento_kmh": v_viento,
            "rafaga_kmh": v_rafaga,
            "precipitacion_mm": v_precipitacion,
            "nubes_pct": v_nubes,
            "temperatura_c": v_temperatura,
        },
    )
