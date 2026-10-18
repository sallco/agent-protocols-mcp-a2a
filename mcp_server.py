"""Herramientas de Parachute S.A. mediante MCP Streamable HTTP."""

from __future__ import annotations

import json
import logging
from functools import wraps
from time import perf_counter
from uuid import UUID, uuid4

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from core import tools

logger = logging.getLogger("parachute.mcp")


def crear_servidor_mcp(
    *, mock_clima: str | None = None, fecha_base: str | None = None
) -> MCPServer:
    """Construye el único servidor del proceso y fija el escenario del operador."""
    tools.configurar_herramientas(mock_clima=mock_clima, fecha_base=fecha_base)

    def consultar_clima(fecha_iso: str) -> str:
        return tools.fn_consultar_clima(fecha_iso)

    def agendar_cita(nombre: str, fecha_iso: str, hora: str, id_evidencia: str) -> str:
        return tools.fn_agendar_cita(nombre, fecha_iso, hora, id_evidencia)

    funciones = {
        "resolver_fecha": tools.fn_resolver_fecha,
        "buscar_faqs": tools.fn_buscar_faqs,
        "consultar_clima": consultar_clima,
        "evaluar_condiciones": tools.fn_evaluar_condiciones,
        "consultar_disponibilidad": tools.fn_consultar_disponibilidad,
        "agendar_cita": agendar_cita,
        "listar_citas": tools.fn_listar_citas,
    }

    async def registrar_ejecucion(ctx, call_next):
        if ctx.method != "tools/call":
            return await call_next(ctx)
        params = ctx.params or {}
        nombre = params.get("name")
        nombre = nombre if isinstance(nombre, str) and nombre in funciones else "desconocida"
        meta = params.get("_meta") or {}
        if not isinstance(meta, dict):
            meta = {}
        try:
            solicitud = str(UUID(str(meta.get("request_id", ""))))
        except ValueError:
            solicitud = str(uuid4())
        inicio = perf_counter()
        estado = "fallida"
        trace_token = tools._TRAZA_HERRAMIENTAS.set(None)
        mock_token = tools._EVAL_MOCK_CLIMA.set(mock_clima)
        try:
            result = await call_next(ctx)
            output = CallToolResult.model_validate(result)
            if not output.is_error:
                payload = json.loads(output.content[0].text)
                if payload.get("error"):
                    estado = "fallida"
                elif any(payload.get(key) is False for key in ("exito", "es_valida", "valida")):
                    estado = "rechazada"
                else:
                    estado = "completada"
            return result
        finally:
            tools._EVAL_MOCK_CLIMA.reset(mock_token)
            tools._TRAZA_HERRAMIENTAS.reset(trace_token)
            logger.info(
                "herramienta=%s estado=%s duracion_ms=%.2f solicitud=%s",
                nombre, estado, (perf_counter() - inicio) * 1000, solicitud,
            )

    server = MCPServer("Parachute S.A.", middleware=[registrar_ejecucion])

    def proteger(func):
        @wraps(func)
        def ejecutar(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                # Los errores internos pueden contener credenciales o datos personales.
                raise ToolError("No fue posible ejecutar la herramienta.") from None
        return ejecutar

    for tool in tools.HERRAMIENTAS_COMPARTIDAS:
        server.tool(name=tool.name, description=tool.description, structured_output=False)(
            proteger(funciones[tool.name])
        )

    return server


def main(
    *, mock_clima: str | None = None, fecha_base: str | None = None, puerto: int = 8001
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    server = crear_servidor_mcp(mock_clima=mock_clima, fecha_base=fecha_base)
    logger.info(
        "Iniciando MCP en http://127.0.0.1:%s/mcp clima=%s fecha_base=%s",
        puerto, mock_clima or "real", fecha_base or "actual de Guatemala",
    )
    server.run(
        transport="streamable-http", host="127.0.0.1", port=puerto,
        json_response=True, stateless_http=True,
    )
