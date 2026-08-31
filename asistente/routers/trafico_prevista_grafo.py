"""Endpoint HTTP para la tool `trafico_prevista_grafo` (`FIL_31`).

Igual que el resto de routers: existe para probar la tool sin un cliente MCP.
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

router = APIRouter(tags=["trafico-prevista-grafo"])

_VEREDICTO_POR_NIVEL = {
    "fluido": Veredicto.FAVORABLE,
    "denso": Veredicto.CON_PRECAUCION,
    "congestionado": Veredicto.DESFAVORABLE,
}


@router.get("/trafico-prevista-grafo", response_model=RespuestaAsistente)
def consultar_trafico_prevista_grafo(
    lugar: str,
    horizonte_horas: int = Query(default=3, description="Horas por delante: 1, 3 o 6."),
    radio_m: float = Query(default=300.0, description="Radio de búsqueda de puntos de tráfico (m)."),
    momento: datetime | None = Query(
        default=None, description="Instante de referencia (ISO 8601). Si se omite, ahora."
    ),
) -> RespuestaAsistente:
    """Invoca `trafico_prevista_grafo` y construye una `RespuestaAsistente`."""
    r = tools.trafico_prevista_grafo(lugar, horizonte_horas, radio_m, momento)
    pregunta = f"¿Cómo estará el tráfico cerca de «{lugar}» dentro de {horizonte_horas} h (modelo de grafo)?"

    if not r.disponible:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"El modelo de grafo (STGNN) no pudo dar una previsión de tráfico para «{lugar}». "
                f"Motivo: {r.motivo or 'sin datos suficientes'}."
            ),
            fuentes=[FuenteConsultada(dataset=r.fuente_dataset, resumen=f"Sin previsión de grafo para «{lugar}»")],
        )

    # tope BAJA a propósito: STGNN experimental con ventana corta (§7.4).
    fiabilidad = NivelFiabilidad.BAJA
    veredicto = _VEREDICTO_POR_NIVEL.get(r.nivel_previsto, Veredicto.CON_PRECAUCION)
    vecinos = ", ".join(f"{v.nodo} ({v.importancia:.3f})" for v in r.vecinos_influyentes) or "sin aristas destacadas"
    explicacion = (
        f"Previsión de grafo cerca de «{r.lugar}» a {r.horizonte_horas} h (punto {r.punto_id}): "
        f"nivel de servicio ≈ {r.valor_previsto} → {r.nivel_previsto} "
        f"(lectura actual {r.valor_actual}). {r.modelo} sobre {r.n_nodos_grafo} nodos. "
        f"Conexiones más influyentes: {vecinos}. "
        "Modelo de grafo experimental — se sirve por la explicabilidad de grafo, no por precisión "
        "(demostración de metodología, memoria §7.4)."
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
                    f"nivel de servicio previsto {r.valor_previsto} ({r.nivel_previsto}) a "
                    f"{r.horizonte_horas} h (punto {r.punto_id}); {r.modelo}"
                ),
                consultado_en=r.momento,
            ),
            FuenteConsultada(
                dataset=f"grafo STGNN ({r.grafo})",
                resumen=f"punto {r.punto_id}; vecinos influyentes: {vecinos}",
            ),
        ],
    )
