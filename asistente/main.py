"""Punto de entrada de la app FastAPI del asistente conversacional «Madroño».

`create_app()` (patrón *application factory*, recomendado por la propia
documentación de FastAPI para poder crear instancias frescas de la app en
los tests, ver `asistente/tests/test_app.py`) construye la app e incluye los
routers disponibles. Hoy solo hay un router (`health`, tarea 044); los
routers reales que expongan `RespuestaAsistente` (ver
`asistente/models/respuesta.py`) son trabajo de una tarea futura, cuando
exista Gold real del que leer.

El agente MCP (`asistente/mcp_agent/`) se define y se prueba por separado en
esta tarea, sin montarlo todavía en esta app HTTP — ver el docstring de
`asistente/mcp_agent/server.py` para el porqué.
"""

from __future__ import annotations

from fastapi import FastAPI

from asistente.routers import health


def create_app() -> FastAPI:
    app = FastAPI(
        title="Madroño - asistente conversacional",
        description=(
            "Esqueleto del servicio del asistente conversacional de "
            "movilidad y vida urbana de Madrid (memoria del TFM, apartados "
            "5.2 y 6.7). Sin lógica de negocio real todavía: ver "
            "asistente/README.md."
        ),
        version="0.1.0",
    )
    app.include_router(health.router)
    return app


app = create_app()
