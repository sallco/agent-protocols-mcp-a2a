"""Contratos y definición única de herramientas compartidas para los agentes."""

from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from time import perf_counter
from typing import Any

from agents import function_tool

from core.dates import DateResolver
from core.faq_store import FAQStore
from core.safety import Veredicto
from core.scheduling import SchedulingService
from core.weather import WeatherClient

# Instancias compartidas de servicios
_faq_store = FAQStore()
_weather_client = WeatherClient()
_scheduling_service = SchedulingService()
_date_resolver = DateResolver()

# Registro en memoria del último comprobante generado en la sesión
_ULTIMO_COMPROBANTE: str | None = None


@dataclass
class RegistroHerramienta:
    nombre: str
    argumentos: dict[str, Any] = field(default_factory=dict)
    exitosa: bool = True
    duracion_ms: float = 0.0
    error: str | None = None
    resultado: Any = None


_TRAZA_HERRAMIENTAS: ContextVar[list[RegistroHerramienta] | None] = ContextVar(
    "traza_herramientas", default=None
)
_TRAZA_GLOBAL: list[RegistroHerramienta] = []
_EVAL_MOCK_CLIMA: ContextVar[str | None] = ContextVar("eval_mock_clima", default=None)


def iniciar_traza_herramientas() -> None:
    global _TRAZA_GLOBAL
    _TRAZA_GLOBAL = []
    _TRAZA_HERRAMIENTAS.set([])


def obtener_traza_herramientas() -> list[dict[str, Any]]:
    traza = _TRAZA_GLOBAL
    return [
        {
            "nombre": item.nombre,
            "argumentos": item.argumentos,
            "exitosa": item.exitosa,
            "duracion_ms": round(item.duracion_ms, 2),
            "error": item.error,
            "resultado": item.resultado,
        }
        for item in traza
    ]


def establecer_mock_clima(modo: str | None) -> None:
    _EVAL_MOCK_CLIMA.set(modo or None)


def _registrar_herramienta(
    nombre: str,
    argumentos: dict[str, Any],
    inicio: float,
    resultado: Any = None,
    error: Exception | None = None,
) -> None:
    global _TRAZA_GLOBAL
    _TRAZA_GLOBAL.append(
        RegistroHerramienta(
            nombre=nombre,
            argumentos={key: str(value) for key, value in argumentos.items()},
            exitosa=error is None,
            duracion_ms=(perf_counter() - inicio) * 1000,
            error=str(error) if error else None,
            resultado=resultado,
        )
    )


def instrumentar_herramienta(nombre: str):
    """Registra la ejecución real de una herramienta cuando hay una traza activa."""

    def decorador(func):
        @wraps(func)
        def envoltura(*args, **kwargs):
            inicio = perf_counter()
            argumentos = {
                **{str(index): value for index, value in enumerate(args)},
                **kwargs,
            }
            try:
                resultado = func(*args, **kwargs)
            except Exception as error:
                _registrar_herramienta(nombre, argumentos, inicio, error=error)
                raise
            _registrar_herramienta(nombre, argumentos, inicio, resultado=resultado)
            return resultado

        return envoltura

    return decorador


def obtener_ultimo_comprobante() -> str | None:
    global _ULTIMO_COMPROBANTE
    return _ULTIMO_COMPROBANTE


def limpiar_ultimo_comprobante() -> None:
    global _ULTIMO_COMPROBANTE
    _ULTIMO_COMPROBANTE = None


# ==========================================
# Funciones puras de herramientas
# ==========================================

@instrumentar_herramienta("resolver_fecha")
def fn_resolver_fecha(expresion: str) -> str:
    res = _date_resolver.resolver(expresion)
    return json.dumps(
        {
            "es_valida": res.es_valida,
            "fecha_iso": res.fecha_iso,
            "mensaje_error": res.mensaje_error,
            "requiere_aclaracion": res.requiere_aclaracion,
            "fecha_maxima": res.fecha_maxima,
        },
        ensure_ascii=False,
    )


@instrumentar_herramienta("buscar_faqs")
def fn_buscar_faqs(consulta: str, limite: int = 3) -> str:
    resultados = _faq_store.buscar(consulta, limite=limite)
    if not resultados:
        return json.dumps(
            {
                "encontrados": 0,
                "mensaje": "No se encontraron FAQs oficiales relevantes con suficiente similitud.",
            },
            ensure_ascii=False,
        )

    items_limpios = []
    for r in resultados:
        item = {
            "id": r["id"],
            "categoria": r["categoria"],
            "pregunta": r["pregunta"],
            "respuesta": r["respuesta"],
            "similitud": round(r["similitud"], 3),
            "calidad": r["estado_calidad"],
        }
        if r["estado_calidad"] == "inconsistente":
            item["advertencia_seguridad"] = (
                "Esta FAQ contiene datos inconsistentes con las normas de seguridad actuales. "
                "No utilizar para definir límites de viento u operación."
            )
        items_limpios.append(item)

    return json.dumps({"encontrados": len(items_limpios), "faqs": items_limpios}, ensure_ascii=False)


@instrumentar_herramienta("consultar_clima")
def fn_consultar_clima(fecha_iso: str, mock_mode: str = "") -> str:
    try:
        res_fecha = _date_resolver.resolver(fecha_iso)
        if not res_fecha.es_valida or not res_fecha.fecha_iso:
            return json.dumps({"error": res_fecha.mensaje_error or "Fecha fuera de ventana."}, ensure_ascii=False)

        mock = mock_mode.strip() if mock_mode else _EVAL_MOCK_CLIMA.get()
        evidencia = _weather_client.consultar(res_fecha.fecha_iso, mock_mode=mock)
        return json.dumps(
            {
                "id_evidencia": evidencia.id_evidencia,
                "fecha": evidencia.fecha,
                "temperatura_c": evidencia.temperatura_c,
                "viento_kmh": evidencia.viento_kmh,
                "rafaga_kmh": evidencia.rafaga_kmh,
                "precipitacion_mm": evidencia.precipitacion_mm,
                "nubes_pct": evidencia.nubes_pct,
                "modo_agregacion": evidencia.modo_agregacion,
                "veredicto_global": evidencia.evaluacion.veredicto_global.value,
                "es_seguro_saltar": evidencia.evaluacion.es_seguro_saltar,
                "motivos": evidencia.evaluacion.motivos,
                "advertencias": evidencia.evaluacion.advertencias,
                "fuente": evidencia.fuente,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": f"Fallo al consultar el clima: {exc}"}, ensure_ascii=False)


@instrumentar_herramienta("evaluar_condiciones")
def fn_evaluar_condiciones(id_evidencia: str) -> str:
    evidencia = _weather_client.obtener_evidencia(id_evidencia)
    if not evidencia:
        return json.dumps(
            {"error": f"No se encontró evidencia meteorológica con ID '{id_evidencia}'."},
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "id_evidencia": evidencia.id_evidencia,
            "fecha": evidencia.fecha,
            "veredicto": evidencia.evaluacion.veredicto_global.value,
            "es_seguro": evidencia.evaluacion.es_seguro_saltar,
            "motivos": evidencia.evaluacion.motivos,
            "advertencias": evidencia.evaluacion.advertencias,
            "variables": evidencia.evaluacion.clasificacion_variables,
        },
        ensure_ascii=False,
    )


@instrumentar_herramienta("consultar_disponibilidad")
def fn_consultar_disponibilidad(fecha_iso: str) -> str:
    disp = _scheduling_service.consultar_disponibilidad(fecha_iso)
    return json.dumps(disp, ensure_ascii=False)


@instrumentar_herramienta("agendar_cita")
def fn_agendar_cita(
    nombre: str,
    fecha_iso: str,
    hora: str,
    id_evidencia: str,
    arquitectura: str = "centralizada",
) -> str:
    global _ULTIMO_COMPROBANTE
    res = _scheduling_service.agendar_cita(
        nombre=nombre,
        fecha_iso=fecha_iso,
        hora=hora,
        id_evidencia=id_evidencia,
        arquitectura=arquitectura,
    )
    if res.exito and res.comprobante:
        _ULTIMO_COMPROBANTE = res.comprobante

    return json.dumps(
        {
            "exito": res.exito,
            "mensaje": res.mensaje,
            "id_cita": res.id_cita,
            "fecha": res.fecha,
            "hora": res.hora,
            "veredicto": res.veredicto,
            "advertencias": res.advertencias or [],
            "comprobante": res.comprobante,
        },
        ensure_ascii=False,
    )


@instrumentar_herramienta("listar_citas")
def fn_listar_citas(fecha_iso: str) -> str:
    citas = _scheduling_service.listar_citas(fecha_iso)
    return json.dumps({"fecha": fecha_iso, "total": len(citas), "citas": citas}, ensure_ascii=False)


# ==========================================
# Envoltorios de herramientas para el SDK
# ==========================================

tool_resolver_fecha = function_tool(
    fn_resolver_fecha,
    name_override="resolver_fecha",
    description_override="Resuelve una expresión de fecha natural o relativa (ej. 'mañana', 'próximo sábado', '29 de septiembre') a formato ISO YYYY-MM-DD validando la ventana de 16 días.",
    strict_mode=False,
)

tool_buscar_faqs = function_tool(
    fn_buscar_faqs,
    name_override="buscar_faqs",
    description_override="Busca respuestas oficiales en las FAQs de Parachute S.A. relevantes para una consulta.",
    strict_mode=False,
)

tool_consultar_clima = function_tool(
    fn_consultar_clima,
    name_override="consultar_clima",
    description_override="Consulta el pronóstico meteorológico oficial de Open-Meteo para una fecha ISO (YYYY-MM-DD). Devuelve datos normalizados y un id_evidencia.",
    strict_mode=False,
)

tool_evaluar_condiciones = function_tool(
    fn_evaluar_condiciones,
    name_override="evaluar_condiciones",
    description_override="Evalúa determinísticamente las reglas de seguridad de salto a partir de un id_evidencia registrado.",
    strict_mode=False,
)

tool_consultar_disponibilidad = function_tool(
    fn_consultar_disponibilidad,
    name_override="consultar_disponibilidad",
    description_override="Consulta las franjas horarias disponibles y ocupadas para saltar en una fecha ISO (YYYY-MM-DD).",
    strict_mode=False,
)

tool_agendar_cita = function_tool(
    fn_agendar_cita,
    name_override="agendar_cita",
    description_override="Registra y confirma una cita de salto en paracaídas validando la evidencia meteorológica previa.",
    strict_mode=False,
)

tool_listar_citas = function_tool(
    fn_listar_citas,
    name_override="listar_citas",
    description_override="Lista las citas confirmadas registradas en el sistema para una fecha ISO (YYYY-MM-DD).",
    strict_mode=False,
)

HERRAMIENTAS_COMPARTIDAS = [
    tool_resolver_fecha,
    tool_buscar_faqs,
    tool_consultar_clima,
    tool_evaluar_condiciones,
    tool_consultar_disponibilidad,
    tool_agendar_cita,
    tool_listar_citas,
]
