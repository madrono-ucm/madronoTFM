"""Endpoint HTTP para la tool `calidad_aire` (tarea 079).

Existe para poder probar la tool sin un cliente MCP (`curl`/`httpx` directos,
ver `asistente/README.md`) -- el propio agente MCP la expone también, sin
pasar por HTTP, vía `asistente/mcp_agent/server.py`.
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

router = APIRouter(tags=["calidad-aire"])

_VEREDICTO_POR_INDICE = {
    "buena": Veredicto.FAVORABLE,
    "regular": Veredicto.FAVORABLE,
    "mala": Veredicto.CON_PRECAUCION,
    "muy mala": Veredicto.DESFAVORABLE,
    "sin_clasificar": Veredicto.CON_PRECAUCION,
}


@router.get("/calidad-aire", response_model=RespuestaAsistente)
def consultar_calidad_aire(
    zona: str,
    momento: datetime | None = Query(
        default=None,
        description="Instante a consultar (ISO 8601). Si se omite, se usa el instante actual.",
    ),
) -> RespuestaAsistente:
    """Invoca la tool `calidad_aire` y construye una `RespuestaAsistente` trazable."""
    resultado = tools.calidad_aire(zona, momento)
    pregunta = f"¿Cómo está la calidad del aire en «{zona}»?"

    if resultado.indice_calidad == "sin_datos":
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No se ha encontrado ninguna estación de la red de calidad del aire "
                f"cuyo nombre o identificador contenga «{zona}» con datos para la fecha/hora "
                "consultada. Esta tool resuelve «zona» por coincidencia de texto sobre el "
                "nombre de la estación (ver asistente/README.md) -- no hay resolución por "
                "barrio/distrito todavía (pendiente del grafo, tareas 067-071)."
            ),
            fuentes=[
                FuenteConsultada(
                    dataset=resultado.fuente_dataset,
                    resumen=f"Sin estaciones coincidentes con «{zona}»",
                )
            ],
        )

    fiabilidad = (
        NivelFiabilidad.MEDIA
        if resultado.indice_calidad == "sin_clasificar" or len(resultado.estaciones_consultadas) > 1
        else NivelFiabilidad.ALTA
    )
    veredicto = _VEREDICTO_POR_INDICE.get(resultado.indice_calidad, Veredicto.CON_PRECAUCION)

    explicacion = (
        f"Calidad del aire en «{zona}» ({', '.join(resultado.estaciones_consultadas)}) "
        f"a las {resultado.hora}:00: {resultado.contaminante_principal} = "
        f"{resultado.valor:.1f} {resultado.unidad} (índice simplificado: {resultado.indice_calidad}). "
        "Índice orientativo, no el Índice de Calidad del Aire oficial -- ver "
        "asistente/mcp_agent/tools.py."
    )

    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=veredicto,
        fiabilidad=fiabilidad,
        explicacion=explicacion,
        fuentes=[
            FuenteConsultada(
                dataset=resultado.fuente_dataset,
                resumen=(
                    f"{resultado.contaminante_principal} promedio {resultado.valor:.1f} "
                    f"{resultado.unidad} a las {resultado.hora}:00, estaciones: "
                    f"{', '.join(resultado.estaciones_consultadas)}"
                ),
                consultado_en=resultado.momento,
            )
        ],
    )
