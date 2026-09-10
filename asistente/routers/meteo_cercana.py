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
    fecha: str | None = Query(default=None, description="YYYY-MM-DD. Si se omite, el último día disponible."),
) -> RespuestaAsistente:
    """Invoca `meteo_cercana` y construye una `RespuestaAsistente`.

    Fiabilidad `MEDIA` con `fecha` explícita, `BAJA` sin ella (`FIL_88`) --
    sin `fecha` el dato es el último disponible, estructuralmente tan
    antiguo como el resto del asistente mientras el pipeline está
    congelado; mismo contrato que `avisos_meteo`."""
    r = tools.meteo_cercana(lugar, radio_m, fecha)
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
        pregunta=pregunta, veredicto=Veredicto.FAVORABLE,
        fiabilidad=NivelFiabilidad.MEDIA if fecha else NivelFiabilidad.BAJA,
        explicacion=(
            f"Estación «{r.estacion}» (a {r.distancia_m:.0f} m de «{lugar}»): {detalle}. "
            + ("Fecha solicitada." if fecha else "Observación real; el pipeline de datos está pausado, puede no ser de hoy.")
        ),
        fuentes=[FuenteConsultada(dataset=r.fuente_dataset, resumen=f"{len(r.lecturas)} magnitudes · {r.estacion}")],
    )
