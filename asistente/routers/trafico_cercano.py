"""Endpoint HTTP para la tool `trafico_cercano` (tarea 081).

Mismo motivo que `asistente/routers/calidad_aire.py` (tarea 079): probar la
tool sin un cliente MCP -- el propio agente MCP la expone también, sin pasar
por HTTP, vía `asistente/mcp_agent/server.py`.
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

router = APIRouter(tags=["trafico-cercano"])

_VEREDICTO_POR_RESUMEN = {
    "fluido": Veredicto.FAVORABLE,
    "denso": Veredicto.CON_PRECAUCION,
    "congestionado": Veredicto.DESFAVORABLE,
}


@router.get("/trafico-cercano", response_model=RespuestaAsistente)
def consultar_trafico_cercano(
    lugar: str,
    radio_m: float = Query(default=300.0, description="Radio de búsqueda en metros alrededor de `lugar`."),
    momento: datetime | None = Query(
        default=None,
        description="Instante a consultar (ISO 8601). Si se omite, se usa el instante actual.",
    ),
) -> RespuestaAsistente:
    """Invoca la tool `trafico_cercano` y construye una `RespuestaAsistente` trazable."""
    resultado = tools.trafico_cercano(lugar, radio_m, momento)
    pregunta = f"¿Cómo está el tráfico cerca de «{lugar}»?"

    if not resultado.estaciones:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No se ha encontrado ningún lugar del grafo cuyo nombre contenga «{lugar}» "
                f"con una estación de tráfico a menos de {radio_m:.0f}m. Esta tool resuelve "
                "«lugar» por coincidencia de texto sobre el nombre del nodo `:Lugar` del "
                "grafo -- ver asistente/README.md."
            ),
            fuentes=[
                FuenteConsultada(
                    dataset=resultado.fuente_grafo,
                    resumen=f"Sin lugares/estaciones coincidentes con «{lugar}» dentro de {radio_m:.0f}m",
                )
            ],
        )

    if resultado.resumen == "sin_datos":
        # El lugar y sus estaciones sí se resolvieron contra el grafo --
        # solo falta el dato de Gold para la fecha/hora consultada (p.ej.
        # una fecha fuera de la ventana con datos reales). Mensaje
        # deliberadamente distinto del caso "sin lugar/estación" de
        # arriba, para no dar a entender que el lugar no se reconoció.
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"Se han encontrado {len(resultado.estaciones)} estación(es) de tráfico a "
                f"menos de {radio_m:.0f}m de «{lugar}», pero no hay datos de tráfico para la "
                f"fecha/hora consultada ({resultado.momento.isoformat()})."
            ),
            fuentes=[
                FuenteConsultada(
                    dataset=resultado.fuente_grafo,
                    resumen=f"{len(resultado.estaciones)} estación(es) de tráfico dentro de {radio_m:.0f}m de «{lugar}»",
                    consultado_en=resultado.momento,
                ),
                FuenteConsultada(
                    dataset=resultado.fuente_gold,
                    resumen="Sin fila para la fecha/hora consultada",
                    consultado_en=resultado.momento,
                ),
            ],
        )

    fiabilidad = NivelFiabilidad.MEDIA if len(resultado.estaciones) > 1 else NivelFiabilidad.ALTA
    veredicto = _VEREDICTO_POR_RESUMEN.get(resultado.resumen, Veredicto.CON_PRECAUCION)

    mas_cercana = resultado.estaciones[0]
    explicacion = (
        f"Tráfico cerca de «{lugar}» a las {resultado.hora}:00: {len(resultado.estaciones)} "
        f"estación(es) de tráfico a menos de {radio_m:.0f}m (la más cercana, "
        f"{mas_cercana.point_id}, a {mas_cercana.distancia_m:.0f}m) -- estado general: "
        f"{resultado.resumen}. Etiqueta orientativa, no una métrica oficial -- ver "
        "asistente/mcp_agent/tools.py."
    )

    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=veredicto,
        fiabilidad=fiabilidad,
        explicacion=explicacion,
        fuentes=[
            FuenteConsultada(
                dataset=resultado.fuente_grafo,
                resumen=f"{len(resultado.estaciones)} estación(es) de tráfico dentro de {radio_m:.0f}m de «{lugar}»",
                consultado_en=resultado.momento,
            ),
            FuenteConsultada(
                dataset=resultado.fuente_gold,
                resumen=(
                    f"{mas_cercana.point_id}: intensidad {mas_cercana.avg_intensity_vph}, "
                    f"nivel de servicio {mas_cercana.avg_service_level} a las {resultado.hora}:00"
                ),
                consultado_en=resultado.momento,
            ),
        ],
    )
