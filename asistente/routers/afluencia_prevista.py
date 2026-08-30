"""Endpoint HTTP para la tool `afluencia_prevista` (`FIL_14`).

Igual que el resto de routers: existe para probar la tool sin un cliente MCP
(`curl`/`httpx`). El agente MCP la expone también sin pasar por HTTP
(`asistente/mcp_agent/server.py`).
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

router = APIRouter(tags=["afluencia-prevista"])

_VEREDICTO_POR_NIVEL = {
    "bajo": Veredicto.FAVORABLE,
    "medio": Veredicto.CON_PRECAUCION,
    "alto": Veredicto.DESFAVORABLE,
}


@router.get("/afluencia-prevista", response_model=RespuestaAsistente)
def consultar_afluencia_prevista(
    lugar: str,
    horizonte_horas: int = Query(default=6, description="Horas por delante: 1, 3 o 6."),
    radio_m: float = Query(default=300.0, description="Radio de búsqueda de sensores (m)."),
    momento: datetime | None = Query(
        default=None, description="Instante de referencia (ISO 8601). Si se omite, ahora."
    ),
) -> RespuestaAsistente:
    """Invoca `afluencia_prevista` y construye una `RespuestaAsistente` trazable."""
    r = tools.afluencia_prevista(lugar, horizonte_horas, radio_m, momento)
    pregunta = f"¿Cuánta actividad habrá cerca de «{lugar}» dentro de {horizonte_horas} h?"

    if not r.disponible:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No hay previsión de afluencia para «{lugar}». "
                f"Motivo: {r.motivo or 'sin datos suficientes'}. "
                + (f"Nivel actual estimado: {r.nivel_actual}. " if r.nivel_actual else "")
                + "La resolución de «lugar» es por texto sobre el grafo (ver asistente/README.md)."
            ),
            fuentes=[FuenteConsultada(dataset=r.fuente_dataset, resumen=f"Sin previsión para «{lugar}»")],
        )

    fiabilidad = (
        NivelFiabilidad.MEDIA if r.data_completeness >= 0.8 else NivelFiabilidad.BAJA
    )  # tope MEDIA: ventana corta (§7.4) + ruido/BiciMAD por persistencia
    veredicto = _VEREDICTO_POR_NIVEL.get(r.nivel_previsto, Veredicto.CON_PRECAUCION)
    explicacion = (
        f"Previsión de actividad urbana cerca de «{r.lugar}» a {r.horizonte_horas} h: "
        f"severidad combinada ≈ {r.valor_previsto}/2 → {r.nivel_previsto} "
        f"(nivel actual: {r.nivel_actual}). Señal derivada — "
        f"señales: {', '.join(r.senales_usadas)}. {r.modelo}. "
        f"Cobertura de features de la previsión de tráfico: {r.data_completeness:.0%}; "
        f"ventana de datos {r.ventana_datos}. "
        "Sólo el tráfico tiene modelo de previsión; ruido y BiciMAD van por persistencia "
        "(demostración de metodología, ver memoria §7.4)."
    )
    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=veredicto,
        fiabilidad=fiabilidad,
        explicacion=explicacion,
        fuentes=[
            FuenteConsultada(
                dataset=r.fuente_dataset,
                resumen=(
                    f"severidad prevista {r.valor_previsto}/2 ({r.nivel_previsto}) a "
                    f"{r.horizonte_horas} h; {r.modelo}"
                ),
                consultado_en=r.momento,
            ),
            FuenteConsultada(
                dataset=r.fuente_grafo or "neo4j",
                resumen=f"sensores ≤{radio_m:.0f} m de «{lugar}»",
            ),
        ],
    )
