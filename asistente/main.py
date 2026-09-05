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
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.transport_security import TransportSecuritySettings

from asistente.mcp_agent.server import mcp
from asistente.routers import (
    afluencia_estimada,
    afluencia_prevista,
    calidad_aire,
    calidad_aire_prevista,
    calidad_aire_prevista_grafo,
    chat,
    contexto_urbano,
    disponibilidad_aparcamiento,
    eventos_cercanos,
    health,
    mejor_hora_zona,
    opciones_movilidad,
    ruta_saludable,
    trafico_cercano,
    trafico_prevista,
    trafico_prevista_grafo,
)


def create_app() -> FastAPI:
    # `streamable_http_app()` sin argumentos activa por defecto (SDK `mcp`,
    # ver `mcp.server.lowlevel.server.Server.streamable_http_app`) protección
    # DNS-rebinding restringida a `host="127.0.0.1"` -- cualquier `Host` real
    # (la IP pública o `35-42-164-183.nip.io`, ver FIL_63/FIL_62) recibe
    # `421 Misdirected Request` del propio SDK MCP, antes incluso de llegar al
    # código de este proyecto. Bug real encontrado probando un cliente MCP de
    # verdad contra la instancia pública (`mcp.client.streamable_http`) --
    # `mcp.list_tools()` en proceso (usado por `asistente/chat.py`) y los
    # tests con streams en memoria (`test_mcp_transport.py`) no pasan por esta
    # comprobación, por eso quedó sin detectar hasta ahora. Se declara
    # explícitamente el host público real como permitido.
    mcp_app = mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(
            allowed_hosts=[
                "35-42-164-183.nip.io",
                "35-42-164-183.nip.io:*",
                "127.0.0.1:*",
                "localhost:*",
            ],
            allowed_origins=[
                "https://35-42-164-183.nip.io",
                "https://d2obcdu8duk47f.cloudfront.net",
                "http://127.0.0.1:*",
                "http://localhost:*",
            ],
        )
    )

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
            "`calidad_aire` (tarea 079), `trafico_cercano` (tarea 081), "
            "`afluencia_estimada` (tarea 089, ambas cruzan el grafo urbano "
            "en Neo4j con Gold), `disponibilidad_aparcamiento` (tarea 090), "
            "`eventos_cercanos` (tarea 095), `opciones_movilidad` (tarea "
            "096, sin routing real -- ver su docstring) y "
            "`calidad_aire_prevista` (tarea ML_09, previsión desde el modelo "
            "ONNX de ML_07) ya leen datos reales -- ver asistente/README.md."
        ),
        version="0.8.0",
        lifespan=lifespan,
    )
    # FIL_62/M2: la landing+chat se sirve desde S3+CloudFront, origen
    # distinto de este backend (EC2) -- sin CORS el navegador bloquearía el
    # fetch() del chat. Abierto a cualquier origen porque no hay estado de
    # sesión/cookies que proteger (el auth real vive en nginx delante de
    # este backend, ver FIL_63), mismo criterio de "no hay nada sensible
    # que filtrar" ya aplicado al resto de la API.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(calidad_aire.router)
    app.include_router(calidad_aire_prevista.router)
    app.include_router(calidad_aire_prevista_grafo.router)
    app.include_router(trafico_cercano.router)
    app.include_router(trafico_prevista.router)
    app.include_router(trafico_prevista_grafo.router)
    app.include_router(ruta_saludable.router)
    app.include_router(contexto_urbano.router)
    app.include_router(mejor_hora_zona.router)
    app.include_router(afluencia_estimada.router)
    app.include_router(afluencia_prevista.router)
    app.include_router(disponibilidad_aparcamiento.router)
    app.include_router(eventos_cercanos.router)
    app.include_router(opciones_movilidad.router)
    app.include_router(chat.router)
    app.mount("/mcp-server", mcp_app)
    return app


app = create_app()
