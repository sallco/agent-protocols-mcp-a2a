"""Servicio de agenda con control de cupos y verificación estricta de evidencia."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from core.config import Settings, get_settings
from core.dates import DateResolver, FRANJAS_VALIDAS
from core.persistence import Cita, guardar_cita, listar_citas_fecha
from core.safety import Veredicto
from core.weather import DatosMeteorologicos, WeatherClient


@dataclass(frozen=True)
class ResultadoAgenda:
    exito: bool
    mensaje: str
    id_cita: str | None = None
    fecha: str | None = None
    hora: str | None = None
    veredicto: str | None = None
    advertencias: list[str] | None = None
    comprobante: str | None = None


class SchedulingService:
    """Gestiona la disponibilidad y reserva de citas con validación de seguridad meteorológica."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.date_resolver = DateResolver(base_date=self.settings.base_date)

    def consultar_disponibilidad(self, fecha_iso: str) -> dict[str, Any]:
        """Devuelve las franjas horarias libres y ocupadas para una fecha dada."""
        res_fecha = self.date_resolver.resolver(fecha_iso)
        if not res_fecha.es_valida or not res_fecha.fecha_iso:
            return {
                "valida": False,
                "mensaje": res_fecha.mensaje_error or "Fecha no válida.",
                "fecha": fecha_iso,
                "franjas_libres": [],
                "franjas_ocupadas": [],
            }

        fecha_limpia = res_fecha.fecha_iso
        citas_existentes = listar_citas_fecha(fecha_limpia, self.settings.database_url, self.settings.citas_table)
        horas_ocupadas = {c.hora for c in citas_existentes}

        franjas_libres = [h for h in FRANJAS_VALIDAS if h not in horas_ocupadas]
        franjas_ocupadas = [h for h in FRANJAS_VALIDAS if h in horas_ocupadas]

        return {
            "valida": True,
            "fecha": fecha_limpia,
            "total_cupos": len(FRANJAS_VALIDAS),
            "cupos_libres": len(franjas_libres),
            "franjas_libres": franjas_libres,
            "franjas_ocupadas": franjas_ocupadas,
        }

    def agendar_cita(
        self,
        nombre: str,
        fecha_iso: str,
        hora: str,
        id_evidencia: str,
        arquitectura: str,
        idempotency_key: str | None = None,
    ) -> ResultadoAgenda:
        """Valida determinísticamente la evidencia climática y persiste la cita."""
        # 1. Validación de nombre
        nombre_limpio = nombre.strip()
        if not nombre_limpio:
            return ResultadoAgenda(
                exito=False,
                mensaje="El nombre del cliente no puede estar vacío.",
            )

        # 2. Validación de fecha
        res_fecha = self.date_resolver.resolver(fecha_iso)
        if not res_fecha.es_valida or not res_fecha.fecha_iso:
            return ResultadoAgenda(
                exito=False,
                mensaje=res_fecha.mensaje_error or "La fecha no es válida.",
            )
        fecha_validada = res_fecha.fecha_iso

        # 3. Validación de franja horaria
        valida_franja, franja_normalizada = self.date_resolver.validar_franja(hora, fecha_validada)
        if not valida_franja:
            return ResultadoAgenda(
                exito=False,
                mensaje=franja_normalizada,
            )

        # 4. GUARDARRAÍL CRÍTICO: Verificación estricta de evidencia meteorológica
        evidencia = WeatherClient.obtener_evidencia(id_evidencia)
        if not evidencia:
            return ResultadoAgenda(
                exito=False,
                mensaje=(
                    f"No se encontró registro de evidencia meteorológica con ID '{id_evidencia}'. "
                    "Debe consultar las condiciones meteorológicas antes de solicitar una reserva."
                ),
            )

        # Paridad estricta de fecha entre la evidencia y la cita solicitada
        if evidencia.fecha != fecha_validada:
            return ResultadoAgenda(
                exito=False,
                mensaje=(
                    f"Inconsistencia de evidencia: el reporte climático corresponde al día {evidencia.fecha}, "
                    f"pero se intentó agendar para el día {fecha_validada}."
                ),
            )

        # Verificación del veredicto determinista
        veredicto = evidencia.evaluacion.veredicto_global
        if veredicto == Veredicto.PROHIBIDO:
            return ResultadoAgenda(
                exito=False,
                mensaje=(
                    f"RESERVA DENEGADA POR SEGURIDAD: Las condiciones meteorológicas para {fecha_validada} "
                    f"están clasificadas como PROHIBIDO. Motivos: {'; '.join(evidencia.evaluacion.motivos)}."
                ),
                veredicto=veredicto.value,
            )

        # 5. Generación de clave de idempotencia consistente si no se proporcionó
        if not idempotency_key:
            hash_input = f"{nombre_limpio.lower()}|{fecha_validada}|{franja_normalizada}|{arquitectura}"
            idempotency_key = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:32]

        cita_id = str(uuid.uuid4())
        cita = Cita(
            id=cita_id,
            idempotency_key=idempotency_key,
            nombre=nombre_limpio,
            fecha=fecha_validada,
            hora=franja_normalizada,
            veredicto=veredicto.value,
            advertencias=evidencia.evaluacion.advertencias,
            evidencia_clima={
                "id_evidencia": evidencia.id_evidencia,
                "viento_kmh": evidencia.viento_kmh,
                "rafaga_kmh": evidencia.rafaga_kmh,
                "precipitacion_mm": evidencia.precipitacion_mm,
                "nubes_pct": evidencia.nubes_pct,
                "temperatura_c": evidencia.temperatura_c,
                "modo_agregacion": evidencia.modo_agregacion,
                "instante_consulta": evidencia.instante_consulta,
            },
            evaluacion_seguridad={
                "veredicto_global": veredicto.value,
                "motivos": evidencia.evaluacion.motivos,
                "advertencias": evidencia.evaluacion.advertencias,
                "clasificacion_variables": evidencia.evaluacion.clasificacion_variables,
            },
            arquitectura=arquitectura,
        )

        exito, msg, cita_guardada = guardar_cita(cita, self.settings.database_url, self.settings.citas_table)
        if not exito or not cita_guardada:
            return ResultadoAgenda(
                exito=False,
                mensaje=msg,
            )

        comprobante = self._generar_comprobante(cita_guardada)
        return ResultadoAgenda(
            exito=True,
            mensaje=msg,
            id_cita=cita_guardada.id,
            fecha=cita_guardada.fecha,
            hora=cita_guardada.hora,
            veredicto=cita_guardada.veredicto,
            advertencias=cita_guardada.advertencias,
            comprobante=comprobante,
        )

    def _generar_comprobante(self, cita: Cita) -> str:
        adv_str = "\n".join(f"  * {a}" for a in cita.advertencias) if cita.advertencias else "  * Ninguna"
        return (
            f"====================================================\n"
            f"           COMPROBANTE OFICIAL DE RESERVA           \n"
            f"                  PARACHUTE S.A.                    \n"
            f"====================================================\n"
            f"ID Reserva:    {cita.id}\n"
            f"Cliente:       {cita.nombre}\n"
            f"Fecha de salto:{cita.fecha}\n"
            f"Franja horaria:{cita.hora} (duración 1 hora)\n"
            f"Veredicto:     {cita.veredicto}\n"
            f"Arquitectura:  {cita.arquitectura}\n"
            f"Advertencias:\n{adv_str}\n"
            f"===================================================="
        )

    def listar_citas(self, fecha_iso: str) -> list[dict[str, Any]]:
        res_fecha = self.date_resolver.resolver(fecha_iso)
        if not res_fecha.es_valida or not res_fecha.fecha_iso:
            return []
        citas = listar_citas_fecha(res_fecha.fecha_iso, self.settings.database_url, self.settings.citas_table)
        return [
            {
                "id": c.id,
                "nombre": c.nombre,
                "fecha": c.fecha,
                "hora": c.hora,
                "veredicto": c.veredicto,
                "advertencias": c.advertencias,
                "arquitectura": c.arquitectura,
            }
            for c in citas
        ]
