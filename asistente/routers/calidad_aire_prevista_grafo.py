"""Endpoint HTTP para la tool `calidad_aire_prevista_grafo` (`FIL_26`).

Igual que el resto de routers: existe para probar la tool sin un cliente MCP.
El agente MCP la expone también sin pasar por HTTP.
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

router = APIRouter(tags=["calidad-aire-prevista-grafo"])

_VEREDICTO_POR_NIVEL = {
    "buena": Veredicto.FAVORABLE,
    "regular": Veredicto.FAVORABLE,
    "mala": Veredicto.CON_PRECAUCION,
    "muy mala": Veredicto.DESFAVORABLE,
    "sin_clasificar": Veredicto.CON_PRECAUCION,
}


@router.get("/calidad-aire-prevista-grafo", response_model=RespuestaAsistente)
def consultar_calidad_aire_prevista_grafo(
    zona: str,
    horizonte_horas: int = Query(default=3, description="Horas por delante: 1, 3 o 6."),
    momento: datetime | None = Query(
        default=None, description="Instante de referencia (ISO 8601). Si se omite, ahora."
    ),
) -> RespuestaAsistente:
    """Invoca `calidad_aire_prevista_grafo` y construye una `RespuestaAsistente`."""
    r = tools.calidad_aire_prevista_grafo(zona, horizonte_horas, momento)
    pregunta = f"¿Cómo estará la calidad del aire en «{zona}» dentro de {horizonte_horas} h (modelo de grafo)?"

    if not r.disponible:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"El modelo de grafo (STGNN) no pudo dar una previsión para «{zona}». "
                f"Motivo: {r.motivo or 'sin datos suficientes'}."
            ),
            fuentes=[FuenteConsultada(dataset=r.fuente_dataset, resumen=f"Sin previsión de grafo para «{zona}»")],
        )

    # tope BAJA a propósito: este STGNN pierde a calidad_aire_prevista en
    # métricas puntuales con la ventana corta (§7.4) — se sirve por la
    # trazabilidad de grafo, no por precisión.
    fiabilidad = NivelFiabilidad.BAJA
    veredicto = _VEREDICTO_POR_NIVEL.get(r.nivel_previsto, Veredicto.CON_PRECAUCION)
    vecinos = ", ".join(
        f"{v.estacion or v.nodo} ({v.contaminante}, {v.importancia:.3f})" for v in r.vecinos_influyentes
    ) or "sin aristas destacadas"
    explicacion = (
        f"Previsión de grafo para «{r.estacion}» ({r.contaminante}) a {r.horizonte_horas} h: "
        f"≈ {r.valor_previsto} {r.unidad or 'µg/m³'} → {r.nivel_previsto} "
        f"(lectura actual {r.valor_actual}). {r.modelo} sobre {r.n_nodos_grafo} nodos. "
        f"Conexiones más influyentes para este nodo: {vecinos}. "
        "Modelo de grafo experimental — en métricas puntuales a 1 h lo supera "
        "`calidad_aire_prevista` (LightGBM); su aportación es la explicabilidad "
        "de grafo (demostración de metodología, memoria §7.4)."
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
                    f"{r.contaminante} previsto {r.valor_previsto} {r.unidad or 'µg/m³'} a "
                    f"{r.horizonte_horas} h ({r.estacion}); {r.modelo}"
                ),
                consultado_en=r.momento,
            ),
            FuenteConsultada(
                dataset=f"grafo STGNN ({r.grafo})",
                resumen=f"nodo {r.nodo}; vecinos influyentes: {vecinos}",
            ),
        ],
    )
