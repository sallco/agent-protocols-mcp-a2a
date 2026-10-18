"""Servidor HTTP local efímero para pruebas de protocolos."""

import asyncio
from contextlib import asynccontextmanager
import socket

import uvicorn


@asynccontextmanager
async def servidor_http(app):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]
        http = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="on"))
        task = asyncio.create_task(http.serve(sockets=[sock]))
        try:
            async with asyncio.timeout(10):
                while not http.started:
                    if task.done():
                        await task
                        raise RuntimeError("El servidor terminó antes de iniciar")
                    await asyncio.sleep(0.01)
            yield f"http://127.0.0.1:{port}"
        finally:
            http.should_exit = True
            try:
                await asyncio.wait_for(task, timeout=10)
            finally:
                if not task.done():
                    task.cancel()
