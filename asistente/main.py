"""Punto de entrada de la app FastAPI del asistente conversacional «Madroño».

`create_app()` (patrón *application factory*, recomendado por la propia
documentación de FastAPI para poder crear instancias frescas de la app en
los tests, ver `asistente/tests/test_app.py`) construye la app e incluye los
routers disponibles.

Tarea 079: el agente MCP (`asistente/mcp_agent/server.py`) se monta aquí
dentro de la app FastAPI vía `FastAPI.mount()`, ahora que tiene una `tool`
real que servir. `MCPServer.streamable_http_app()` devuelve una sub-app
Starlette cuyo propio `lifespan` arranca/para el
`StreamableHTTPSessionManager` que gestiona las sesiones MCP (ver el código
de `mcp.server.lowlevel.server.Server.streamable_http_app`, que construye la
sub-app con `lifespan=lambda app: session_manager.run()`). `FastAPI.mount()`
por sí solo **no** propaga el `lifespan` de una sub-app montada -- solo el de
la app raíz se ejecuta en un despliegue real (Uvicorn solo invoca el
`lifespan` de la ASGI app de nivel superior). Por eso el `lifespan` de la app
principal entra explícitamente en el `lifespan_context` de la sub-app MCP
usando `contextlib.AsyncExitStack` (patrón documentado por el propio SDK de
MCP para este caso exacto: montar `streamable_http_app()` bajo otro
framework ASGI).
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from asistente.mcp_agent.server import mcp
from asistente.routers import calidad_aire, health, trafico_cercano


def create_app() -> FastAPI:
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(mcp_app.router.lifespan_context(mcp_app))
            yield

    app = FastAPI(
        title="Madroño - asistente conversacional",
        description=(
            "Servicio del asistente conversacional de movilidad y vida "
            "urbana de Madrid (memoria del TFM, apartados 5.2 y 6.7). "
            "`calidad_aire` (tarea 079) y `trafico_cercano` (tarea 081, "
            "cruza el grafo urbano en Neo4j con Gold) ya leen datos reales; "
            "el resto de `tools` siguen pendientes -- ver asistente/README.md."
        ),
        version="0.3.0",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(calidad_aire.router)
    app.include_router(trafico_cercano.router)
    app.mount("/mcp-server", mcp_app)
    return app


app = create_app()
