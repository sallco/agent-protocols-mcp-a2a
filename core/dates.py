"""Servicio determinista para resolución de fechas y ventana de pronóstico."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import ClassVar

DIAS_SEMANA: dict[str, int] = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}

MESES: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

FRANJAS_VALIDAS: list[str] = [
    "08:00",
    "09:00",
    "10:00",
    "11:00",
    "12:00",
    "13:00",
    "14:00",
    "15:00",
]


@dataclass(frozen=True)
class ResultadoFecha:
    es_valida: bool
    fecha_iso: str | None
    mensaje_error: str | None = None
    requiere_aclaracion: bool = False
    fecha_maxima: str | None = None


class DateResolver:
    """Resuelve expresiones de fechas naturales y absolutas contra un reloj inyectable."""

    DEFAULT_BASE_DATE: ClassVar[str] = "2026-09-18"
    VENTANA_DIAS: ClassVar[int] = 16  # Hoy hasta hoy + 15 inclusive

    def __init__(self, base_date: date | str | None = None) -> None:
        if base_date is None:
            self.base_date = date.fromisoformat(self.DEFAULT_BASE_DATE)
        elif isinstance(base_date, str):
            self.base_date = date.fromisoformat(base_date)
        else:
            self.base_date = base_date

    @property
    def max_date(self) -> date:
        # 16 días contando hoy: hoy + 15 días
        return self.base_date + timedelta(days=self.VENTANA_DIAS - 1)

    def resolver(self, expresion: str) -> ResultadoFecha:
        texto = expresion.strip().lower()
        if not texto:
            return ResultadoFecha(
                es_valida=False,
                fecha_iso=None,
                mensaje_error="La expresión de fecha no puede estar vacía.",
                requiere_aclaracion=True,
            )

        fecha_objetivo: date | None = None

        # 1. Expresiones relativas fijas
        if texto in {"hoy", "el día de hoy"}:
            fecha_objetivo = self.base_date
        elif texto in {"mañana", "el día de mañana"}:
            fecha_objetivo = self.base_date + timedelta(days=1)
        elif texto in {"pasado mañana", "el día pasado mañana"}:
            fecha_objetivo = self.base_date + timedelta(days=2)

        # 2. "en N días" o "en N semanas"
        if fecha_objetivo is None:
            match_dias = re.match(r"^en\s+(\d+)\s+d[ií]as?$", texto)
            if match_dias:
                dias = int(match_dias.group(1))
                fecha_objetivo = self.base_date + timedelta(days=dias)

            match_semanas = re.match(r"^en\s+(\d+)\s+semanas?$", texto)
            if match_semanas:
                semanas = int(match_semanas.group(1))
                fecha_objetivo = self.base_date + timedelta(weeks=semanas)

        # 3. "próximo <día de la semana>" o "el próximo <día de la semana>"
        if fecha_objetivo is None:
            match_dia_semana = re.match(r"^(?:el\s+)?pr[oó]ximo\s+([a-záéíóú]+)$", texto)
            if match_dia_semana:
                nombre_dia = match_dia_semana.group(1)
                if nombre_dia in DIAS_SEMANA:
                    target_weekday = DIAS_SEMANA[nombre_dia]
                    current_weekday = self.base_date.weekday()
                    # Estrictamente posterior
                    dias_adelante = (target_weekday - current_weekday) % 7
                    if dias_adelante == 0:
                        dias_adelante = 7
                    fecha_objetivo = self.base_date + timedelta(days=dias_adelante)
                else:
                    return ResultadoFecha(
                        es_valida=False,
                        fecha_iso=None,
                        mensaje_error=f"Día de la semana no reconocido: '{nombre_dia}'.",
                        requiere_aclaracion=True,
                    )

        # 4. Formato ISO YYYY-MM-DD
        if fecha_objetivo is None and re.match(r"^\d{4}-\d{2}-\d{2}$", texto):
            try:
                fecha_objetivo = date.fromisoformat(texto)
            except ValueError:
                return ResultadoFecha(
                    es_valida=False,
                    fecha_iso=None,
                    mensaje_error=f"La fecha '{texto}' no es una fecha válida en el calendario.",
                    requiere_aclaracion=False,
                )

        # 5. Formatos numéricos con barra o guión: DD/MM/YYYY o MM/DD/YYYY -> ambiguo
        if fecha_objetivo is None and re.match(r"^\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?$", texto):
            return ResultadoFecha(
                es_valida=False,
                fecha_iso=None,
                mensaje_error=(
                    f"El formato numérico '{texto}' es ambiguo. "
                    "Por favor especifique la fecha en formato ISO AAAA-MM-DD o con el nombre del mes (ej. 29 de septiembre de 2026)."
                ),
                requiere_aclaracion=True,
            )

        # 6. Formatos en español explícito: "29 de septiembre de 2026" o "29 de septiembre"
        if fecha_objetivo is None:
            match_esp = re.match(
                r"^(?:el\s+)?(\d{1,2})\s+de\s+([a-záéíóú]+)(?:\s+de\s+(\d{4}))?$", texto
            )
            if match_esp:
                dia = int(match_esp.group(1))
                nombre_mes = match_esp.group(2)
                año = int(match_esp.group(3)) if match_esp.group(3) else self.base_date.year
                if nombre_mes in MESES:
                    mes = MESES[nombre_mes]
                    try:
                        fecha_objetivo = date(año, mes, dia)
                    except ValueError:
                        return ResultadoFecha(
                            es_valida=False,
                            fecha_iso=None,
                            mensaje_error=f"Día {dia} no válido para el mes de {nombre_mes}.",
                            requiere_aclaracion=False,
                        )

        # Si no se pudo parsear
        if fecha_objetivo is None:
            return ResultadoFecha(
                es_valida=False,
                fecha_iso=None,
                mensaje_error=(
                    f"No pude interpretar la fecha '{expresion}'. "
                    "Indica una fecha como 'YYYY-MM-DD', 'mañana', 'próximo sábado' o '29 de septiembre de 2026'."
                ),
                requiere_aclaracion=True,
            )

        # Validaciones de límites temporales
        fecha_iso = fecha_objetivo.isoformat()
        fecha_max_iso = self.max_date.isoformat()

        if fecha_objetivo < self.base_date:
            return ResultadoFecha(
                es_valida=False,
                fecha_iso=fecha_iso,
                mensaje_error=f"La fecha {fecha_iso} está en el pasado (referencia actual: {self.base_date.isoformat()}).",
                requiere_aclaracion=False,
                fecha_maxima=fecha_max_iso,
            )

        if fecha_objetivo > self.max_date:
            return ResultadoFecha(
                es_valida=False,
                fecha_iso=fecha_iso,
                mensaje_error=(
                    f"La fecha solicitada ({fecha_iso}) excede la ventana máxima de pronóstico de 16 días. "
                    f"La fecha límite disponible es {fecha_max_iso}."
                ),
                requiere_aclaracion=False,
                fecha_maxima=fecha_max_iso,
            )

        return ResultadoFecha(
            es_valida=True,
            fecha_iso=fecha_iso,
            mensaje_error=None,
            requiere_aclaracion=False,
            fecha_maxima=fecha_max_iso,
        )

    def validar_franja(self, franja: str, fecha_iso: str | None = None) -> tuple[bool, str]:
        """Valida que la franja esté en las 8 permitidas y no haya pasado si la fecha es hoy."""
        franja_limpia = franja.strip()
        if len(franja_limpia) == 4 and franja_limpia[1] == ":":
            franja_limpia = "0" + franja_limpia
        # Si pasan rango como 08:00-09:00 nos quedamos con el inicio
        if "-" in franja_limpia:
            franja_limpia = franja_limpia.split("-")[0].strip()

        if franja_limpia not in FRANJAS_VALIDAS:
            return False, f"Franja '{franja}' no válida. Las franjas van de 08:00 a 15:00 en intervalos de 1 hora."

        return True, franja_limpia
