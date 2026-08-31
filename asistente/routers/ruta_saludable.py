"""Endpoint HTTP para la tool `ruta_saludable` (`FIL_37`).

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

router = APIRouter(tags=["ruta-saludable"])


@router.get("/ruta-saludable", response_model=RespuestaAsistente)
def consultar_ruta_saludable(
    origen: str,
    destino: str,
    perfil: str = Query(default="general", description="general | ciclista | sensible_aire | sensible_ruido"),
    momento: datetime | None = Query(
        default=None, description="Instante (ISO 8601). Si se omite, un día laborable curado a las 08:00."
    ),
) -> RespuestaAsistente:
    """Invoca `ruta_saludable` y construye una `RespuestaAsistente`."""
    r = tools.ruta_saludable(origen, destino, perfil, momento)
    pregunta = f"¿Cómo voy de «{origen}» a «{destino}» minimizando la exposición ({perfil})?"

    if not r.disponible:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No se pudo calcular una ruta saludable. Motivo: {r.motivo or 'sin datos'}. "
                + (f"Lugares disponibles: {', '.join(r.lugares_disponibles)}." if r.lugares_disponibles else "")
            ),
            fuentes=[],
        )

    red = r.reduccion_exposicion_pct
    explicacion = (
        f"Ruta saludable de «{r.origen}» a «{r.destino}» ({r.perfil}, {r.dia} {r.hora:02d}:00): "
        f"{r.ruta_sana.n_nodos} tramos, {r.ruta_sana.dist_m:.0f} m (+{r.delta_distancia_pct:.1f}% "
        f"sobre la ruta rápida) a cambio de −{red.get('traf', 0):.0f}% de exposición a tráfico, "
        f"−{red.get('no2', 0):.0f}% NO₂, −{red.get('o3', 0):.0f}% O₃, −{red.get('noise', 0):.0f}% ruido. "
        f"Mejor hora de salida: {r.mejor_hora_salida:02d}:00. "
        "Enrutado sobre el grafo `coords-knn8` con exposición prevista — demostración de metodología "
        "(memoria §7.4), 3 días curados; el O₃ apenas se puede esquivar (contaminante regional)."
    )
    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=Veredicto.FAVORABLE if r.delta_distancia_pct <= 15 else Veredicto.CON_PRECAUCION,
        fiabilidad=NivelFiabilidad.BAJA,  # tope a propósito (§7.4)
        explicacion=explicacion,
        fuentes=[
            FuenteConsultada(
                dataset="grafo_ruta.json (FIL_37 — grafo coords-knn8 + previsión STGNN + ruido por distrito)",
                resumen=(
                    f"ruta sana {r.ruta_sana.dist_m:.0f} m vs rápida {r.ruta_rapida.dist_m:.0f} m; "
                    f"perfil {r.perfil}; mejor hora {r.mejor_hora_salida:02d}:00"
                ),
            ),
        ],
    )
