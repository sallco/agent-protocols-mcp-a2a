"""Chat A2A y consulta explícita de recursos MCP, sin agentes ni servicios locales."""

import asyncio
from uuid import uuid4

from a2a.client import ClientConfig, create_client
from a2a.helpers import get_artifact_text, get_message_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
import httpx
from mcp import Client as MCPClient
from mcp.types import TextResourceContents

AYUDA = "/nuevo | /recursos | /recurso URI | /ayuda | /salir"


async def mostrar_recursos(entrada: str, mcp_url: str) -> None:
    partes = entrada.split(maxsplit=1)
    listar = partes[0] == "/recursos"
    if len(partes) != (1 if listar else 2):
        print("Uso: /recursos o /recurso URI")
        return
    try:
        async with MCPClient(mcp_url, read_timeout_seconds=30) as client:
            if listar:
                recursos = (await client.list_resources()).resources
                for recurso in recursos:
                    print(f"{recurso.uri} — {recurso.name}")
                if not recursos:
                    print("No hay recursos disponibles.")
            else:
                resultado = await client.read_resource(partes[1])
                for contenido in resultado.contents:
                    if isinstance(contenido, TextResourceContents):
                        print(contenido.text)
                    else:
                        print("El recurso contiene datos binarios que esta terminal no muestra.")
    except Exception:
        print("No se pudo consultar el recurso MCP. Comprueba el servidor y la URI.")


async def ejecutar_chat(
    *, a2a_url: str = "http://127.0.0.1:8000", mcp_url: str = "http://127.0.0.1:8001/mcp",
) -> None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=10)) as http:
        async with await create_client(
            a2a_url, ClientConfig(streaming=False, httpx_client=http),
        ) as client:
            contexto = str(uuid4())
            print(f"Cliente A2A conectado a {a2a_url}\n{AYUDA}")
            while True:
                try:
                    texto = input("\nUsuario: ").strip()
                except EOFError:
                    return
                if not texto:
                    continue
                if texto.lower() in {"/salir", "salir", "exit", "quit"}:
                    return
                if texto == "/nuevo":
                    contexto = str(uuid4())
                    print(f"Nueva conversación: {contexto}")
                    continue
                if texto.split(maxsplit=1)[0] in {"/recursos", "/recurso"}:
                    await mostrar_recursos(texto, mcp_url)
                    continue
                if texto.startswith("/"):
                    print(AYUDA if texto == "/ayuda" else f"Comando no reconocido. {AYUDA}")
                    continue
                request = SendMessageRequest(message=new_text_message(
                    texto, role=Role.ROLE_USER, context_id=contexto,
                ))
                try:
                    async for evento in client.send_message(request):
                        if not evento.HasField("task"):
                            raise ValueError("Se esperaba una tarea del servidor Parachute.")
                        tarea = evento.task
                        contexto = tarea.context_id
                        estado = TaskState.Name(tarea.status.state).removeprefix("TASK_STATE_")
                        print(f"\nTarea: {tarea.id} | Estado: {estado}")
                        print(f"Asistente: {get_message_text(tarea.status.message)}")
                        for artefacto in tarea.artifacts:
                            if artefacto.name == "comprobante":
                                print(f"\nComprobante:\n{get_artifact_text(artefacto)}")
                except Exception:
                    print(
                        "No se pudo obtener la respuesta A2A. No se reintentó la solicitud. "
                        "Si pediste una reserva, consulta las citas antes de repetirla: "
                        "su resultado podría ser incierto."
                    )


def main(*, a2a_url: str = "http://127.0.0.1:8000",
         mcp_url: str = "http://127.0.0.1:8001/mcp") -> None:
    try:
        asyncio.run(ejecutar_chat(a2a_url=a2a_url, mcp_url=mcp_url))
    except KeyboardInterrupt:
        print("\nCliente cerrado. Interrumpir la conexión no cancela una reserva en curso.")
    except Exception:
        print("No se pudo iniciar el cliente A2A. Comprueba la URL y que el servidor esté activo.")
        raise SystemExit(1) from None
