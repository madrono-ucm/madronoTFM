"""Endpoint HTTP para la tool `meteo_cercana` (`FIL_82`)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from asistente.mcp_agent import tools
from asistente.models.respuesta import (
    FuenteConsultada,
    NivelFiabilidad,
    RespuestaAsistente,
    Veredicto,
)

router = APIRouter(tags=["meteo-cercana"])


@router.get("/meteo-cercana", response_model=RespuestaAsistente)
def consultar_meteo_cercana(
    lugar: str,
    radio_m: float = Query(default=1500.0, description="Radio de búsqueda de estación meteo (m)."),
) -> RespuestaAsistente:
    """Invoca `meteo_cercana` y construye una `RespuestaAsistente`."""
    r = tools.meteo_cercana(lugar, radio_m)
    pregunta = f"¿Qué tiempo hace cerca de «{lugar}»?"
    if not r.disponible:
        return RespuestaAsistente(
            pregunta=pregunta, veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=f"No hay meteorología para «{lugar}». Motivo: {r.motivo}.",
            fuentes=[FuenteConsultada(dataset=r.fuente_dataset or "gold.meteorologia", resumen=r.motivo or "sin datos")],
        )
    detalle = ", ".join(
        f"{l.magnitud} {l.valor} ({l.fecha} {l.hora:02d}h)" if l.hora is not None else f"{l.magnitud} {l.valor}"
        for l in r.lecturas
    )
    return RespuestaAsistente(
        pregunta=pregunta, veredicto=Veredicto.FAVORABLE, fiabilidad=NivelFiabilidad.MEDIA,
        explicacion=(
            f"Estación «{r.estacion}» (a {r.distancia_m:.0f} m de «{lugar}»): {detalle}. "
            "Observación real; el pipeline de datos está pausado, puede no ser de hoy."
        ),
        fuentes=[FuenteConsultada(dataset=r.fuente_dataset, resumen=f"{len(r.lecturas)} magnitudes · {r.estacion}")],
    )
