"""Endpoint HTTP para la tool `consulta_grafo` (FIL_67).

Igual que el resto de routers: permite probar la tool sin cliente MCP
(`curl`/`httpx`), el agente MCP la expone también sin pasar por HTTP.

`tools.consulta_grafo` devuelve `ConsultaGrafo` (contenedor con
`plantilla`/`parametros`/`filas`); este router construye la
`RespuestaAsistente` trazable a partir de `.filas`.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from asistente.mcp_agent import tools
from asistente.models.respuesta import (
    FuenteConsultada,
    NivelFiabilidad,
    RespuestaAsistente,
    Veredicto,
)

router = APIRouter(tags=["consulta-grafo"])


@router.get("/consulta-grafo", response_model=RespuestaAsistente)
def consultar_grafo(
    plantilla: str = Query(description="Nombre de la plantilla de consulta (ver la tool `consulta_grafo`)."),
    lugar: str = Query(default="", description="Nombre parcial de un :Lugar del grafo."),
    radio_m: float = Query(default=300.0, description="Radio de búsqueda en metros (útil máx. ~300)."),
    contaminante: str = Query(default="", description="Solo `aire_que_mide`: NO2/O3/PM10/PM2.5/…"),
    estacion_id: str = Query(default="", description="Solo `lineas_de_parada`: id completo del nodo parada."),
    linea: str = Query(default="", description="Solo `paradas_de_linea`."),
    modo: str = Query(default="", description="Solo `paradas_de_linea`: metro/emt/metro_ligero."),
) -> RespuestaAsistente:
    """Invoca `consulta_grafo` y construye una `RespuestaAsistente`."""
    r = tools.consulta_grafo(plantilla, lugar, radio_m, contaminante, estacion_id, linea, modo)
    pregunta = f"Consulta del grafo urbano: plantilla «{plantilla}» ({r.parametros})."

    if not r.disponible:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No se pudo resolver la consulta. Motivo: {r.motivo}. "
                f"Plantillas disponibles: {', '.join(r.plantillas_disponibles)}."
            ),
            fuentes=[FuenteConsultada(dataset=r.fuente_grafo, resumen=r.motivo or "sin resultado")],
        )

    muestra = "; ".join(
        ", ".join(f"{k}={v}" for k, v in fila.items()) for fila in r.filas[:3]
    ) or "(0 filas)"
    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=Veredicto.FAVORABLE if r.n_filas else Veredicto.CON_PRECAUCION,
        fiabilidad=NivelFiabilidad.ALTA if r.n_filas else NivelFiabilidad.BAJA,
        explicacion=(
            f"La plantilla «{plantilla}» devolvió {r.n_filas} fila(s) del grafo urbano real. "
            f"Primeras: {muestra}."
        ),
        fuentes=[
            FuenteConsultada(dataset=r.fuente_grafo, resumen=f"{r.n_filas} filas · plantilla {plantilla}"),
        ],
    )
