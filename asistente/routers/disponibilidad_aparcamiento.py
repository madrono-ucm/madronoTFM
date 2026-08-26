"""Endpoint HTTP para la tool `disponibilidad_aparcamiento` (tarea 090).

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

router = APIRouter(tags=["disponibilidad-aparcamiento"])


@router.get("/disponibilidad-aparcamiento", response_model=RespuestaAsistente)
def consultar_disponibilidad_aparcamiento(
    zona: str,
    momento: datetime | None = Query(
        default=None,
        description="Instante a consultar (ISO 8601). Si se omite, se usa el instante actual.",
    ),
) -> RespuestaAsistente:
    """Invoca la tool `disponibilidad_aparcamiento` y construye una `RespuestaAsistente` trazable."""
    resultado = tools.disponibilidad_aparcamiento(zona, momento)
    pregunta = f"¿Hay plazas de aparcamiento libres en «{zona}»?"

    if not resultado.aparcamientos_consultados or resultado.plazas_libres is None:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No se ha encontrado ningún aparcamiento público cuyo nombre o "
                f"identificador contenga «{zona}» con datos para la fecha/hora "
                "consultada. Esta tool resuelve «zona» por coincidencia de texto sobre "
                "el nombre del aparcamiento (ver asistente/README.md) -- no hay "
                "resolución por barrio/distrito todavía (pendiente del grafo)."
            ),
            fuentes=[
                FuenteConsultada(
                    dataset=resultado.fuente_dataset,
                    resumen=f"Sin aparcamientos coincidentes con «{zona}»",
                )
            ],
        )

    ratio_libre = (
        resultado.plazas_libres / resultado.plazas_totales if resultado.plazas_totales else None
    )
    if ratio_libre is None:
        veredicto = Veredicto.CON_PRECAUCION
        fiabilidad = NivelFiabilidad.MEDIA
    elif ratio_libre >= 0.15:
        veredicto = Veredicto.FAVORABLE
        fiabilidad = NivelFiabilidad.ALTA
    elif ratio_libre > 0:
        veredicto = Veredicto.CON_PRECAUCION
        fiabilidad = NivelFiabilidad.ALTA
    else:
        veredicto = Veredicto.DESFAVORABLE
        fiabilidad = NivelFiabilidad.ALTA
    if len(resultado.aparcamientos_consultados) > 1:
        fiabilidad = NivelFiabilidad.MEDIA

    totales_texto = f" de {resultado.plazas_totales}" if resultado.plazas_totales is not None else ""
    explicacion = (
        f"Plazas libres estimadas en «{zona}» "
        f"({', '.join(resultado.aparcamientos_consultados)}) a las {resultado.hora}:00: "
        f"{resultado.plazas_libres}{totales_texto}. "
        "Suma de la ocupación media agregada de los aparcamientos coincidentes, no un "
        "conteo en tiempo real -- ver asistente/mcp_agent/tools.py."
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
                    f"{resultado.plazas_libres}{totales_texto} plazas libres a las "
                    f"{resultado.hora}:00, aparcamientos: "
                    f"{', '.join(resultado.aparcamientos_consultados)}"
                ),
                consultado_en=resultado.momento,
            )
        ],
    )
