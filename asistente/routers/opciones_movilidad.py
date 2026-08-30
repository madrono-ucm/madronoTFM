"""Endpoint HTTP para la tool `opciones_movilidad` (tarea 096).

Existe para poder probar la tool sin un cliente MCP (`curl`/`httpx` directos,
ver `asistente/README.md`) -- el propio agente MCP la expone también, sin
pasar por HTTP, vía `asistente/mcp_agent/server.py`.

`tools.opciones_movilidad` devuelve `OpcionesMovilidad` (`FIL_24`: un
contenedor con `origen`/`destino` + `opciones: list[OpcionMovilidad]`, para
que el SDK de MCP genere `output_schema`); este router construye la
`RespuestaAsistente` a partir de `.opciones`.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from asistente.mcp_agent import tools
from asistente.models.respuesta import (
    FuenteConsultada,
    NivelFiabilidad,
    RespuestaAsistente,
    Veredicto,
)

router = APIRouter(tags=["opciones-movilidad"])


@router.get("/opciones-movilidad", response_model=RespuestaAsistente)
def consultar_opciones_movilidad(
    origen: str,
    destino: str,
    momento: datetime | None = Query(
        default=None,
        description="Instante del desplazamiento (ISO 8601). Si se omite, se usa el instante actual.",
    ),
) -> RespuestaAsistente:
    """Invoca la tool `opciones_movilidad` y construye una `RespuestaAsistente` trazable."""
    opciones = tools.opciones_movilidad(origen, destino, momento).opciones
    pregunta = f"¿Cómo voy de «{origen}» a «{destino}»?"

    if not opciones:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No se ha encontrado ningún `:Lugar` del grafo cuyo nombre contenga "
                f"«{origen}» ni «{destino}». Esta tool resuelve ambos por coincidencia de "
                "texto (ver asistente/README.md) -- no hay resolución por dirección/"
                "coordenadas libres todavía."
            ),
            fuentes=[],
        )

    explicacion = (
        f"Condiciones cerca de «{origen}» y «{destino}» para {len(opciones)} modos "
        "(sin calcular una ruta ni duración real -- ver asistente/mcp_agent/tools.py): "
        + "; ".join(f"{o.modo}: {', '.join(o.incidencias)}" for o in opciones)
    )

    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=Veredicto.CON_PRECAUCION,
        fiabilidad=NivelFiabilidad.MEDIA,
        explicacion=explicacion,
        fuentes=[
            FuenteConsultada(
                dataset=opcion.fuente_dataset,
                resumen=f"{opcion.modo}: {', '.join(opcion.incidencias)}",
            )
            for opcion in opciones
        ],
    )
