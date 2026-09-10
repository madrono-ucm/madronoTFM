"""Endpoint HTTP para la tool `avisos_meteo` (`FIL_82`)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from asistente.mcp_agent import tools
from asistente.models.respuesta import (
    FuenteConsultada,
    NivelFiabilidad,
    RespuestaAsistente,
    Veredicto,
)

router = APIRouter(tags=["avisos-meteo"])

_VEREDICTO = {"verde": Veredicto.FAVORABLE, "amarillo": Veredicto.CON_PRECAUCION,
              "naranja": Veredicto.DESFAVORABLE, "rojo": Veredicto.DESFAVORABLE}


@router.get("/avisos-meteo", response_model=RespuestaAsistente)
def consultar_avisos_meteo(
    zona: str | None = Query(default=None, description="Filtro de texto sobre el nombre de zona AEMET."),
    fecha: str | None = Query(default=None, description="YYYY-MM-DD. Si se omite, el último día disponible."),
) -> RespuestaAsistente:
    """Invoca `avisos_meteo` y construye una `RespuestaAsistente`."""
    r = tools.avisos_meteo(zona, fecha)
    pregunta = "¿Hay avisos meteorológicos en Madrid?" + (f" (zona «{zona}»)" if zona else "")
    if not r.disponible:
        return RespuestaAsistente(
            pregunta=pregunta, veredicto=Veredicto.FAVORABLE, fiabilidad=NivelFiabilidad.BAJA,
            explicacion=f"No consta ningún aviso. Motivo: {r.motivo}.",
            fuentes=[FuenteConsultada(dataset=r.fuente_dataset or "gold.aemet_avisos", resumen=r.motivo or "sin avisos")],
        )
    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=_VEREDICTO.get(r.nivel or "verde", Veredicto.CON_PRECAUCION),
        fiabilidad=NivelFiabilidad.MEDIA if fecha else NivelFiabilidad.BAJA,
        explicacion=(
            f"Aviso de nivel **{r.nivel}** para el {r.fecha}"
            + (f" ({', '.join(r.zonas_afectadas)})" if r.zonas_afectadas else "")
            + (f". Fenómenos: {', '.join(r.fenomenos)}" if r.fenomenos else "")
            + (f". Vigencia {r.vigencia_desde} → {r.vigencia_hasta}" if r.vigencia_desde else "")
            + ". " + (r.motivo + "." if r.motivo else "")
        ),
        fuentes=[FuenteConsultada(dataset=r.fuente_dataset, resumen=f"nivel {r.nivel} · {r.fecha}")],
    )
