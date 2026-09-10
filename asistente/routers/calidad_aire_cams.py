"""Endpoint HTTP para la tool `calidad_aire_cams` (`FIL_80`).

Prueba la tool sin cliente MCP; el agente MCP la expone también sin HTTP.
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

router = APIRouter(tags=["calidad-aire-cams"])


@router.get("/calidad-aire-cams", response_model=RespuestaAsistente)
def consultar_calidad_aire_cams(
    contaminante: str = Query(description="NO2 / O3 / PM10 / PM2.5 / SO2 (texto libre)."),
    fecha: str | None = Query(default=None, description="Fecha de validez YYYY-MM-DD. Si se omite, la última disponible."),
) -> RespuestaAsistente:
    """Invoca `calidad_aire_cams` y construye una `RespuestaAsistente`."""
    r = tools.calidad_aire_cams(contaminante, fecha)
    pregunta = f"¿Qué previsión da Copernicus CAMS para {contaminante}" + (f" el {fecha}?" if fecha else "?")

    if not r.disponible:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=f"No hay previsión CAMS disponible. Motivo: {r.motivo}.",
            fuentes=[FuenteConsultada(dataset=r.fuente_dataset or "gold.cams_calidad_aire", resumen=r.motivo or "sin datos")],
        )

    explicacion = (
        f"Copernicus CAMS ({r.contaminante}) para el {r.fecha_validez}: "
        f"media ≈ {r.avg_ugm3} {r.unidad or 'µg/m³'}, máx ≈ {r.max_ugm3}. "
        f"Emitida {r.emitido_en}. Leadtimes {r.leadtime_horas} h. "
        f"{r.motivo + '. ' if r.motivo else ''}"
        "Es una previsión de modelo atmosférico de área (no por estación), "
        "independiente de los modelos propios — sirve de contraste."
    )
    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=Veredicto.FAVORABLE,
        fiabilidad=NivelFiabilidad.MEDIA if not r.motivo else NivelFiabilidad.BAJA,
        explicacion=explicacion,
        fuentes=[
            FuenteConsultada(
                dataset=r.fuente_dataset,
                resumen=f"CAMS {r.contaminante} {r.fecha_validez}: avg {r.avg_ugm3} {r.unidad or 'µg/m³'}",
            )
        ],
    )
