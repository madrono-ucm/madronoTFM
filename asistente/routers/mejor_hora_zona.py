"""Endpoint HTTP para la tool `mejor_hora_zona` (`FIL_46`).

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

router = APIRouter(tags=["mejor-hora-zona"])


@router.get("/mejor-hora-zona", response_model=RespuestaAsistente)
def consultar_mejor_hora_zona(
    zona: str,
    perfil: str = Query(
        default="general",
        description="general | ciclista | sensible_aire | sensible_ruido | asma_epoc | mayor | infancia | movilidad_reducida | trabajo_exterior",
    ),
    momento: datetime | None = Query(
        default=None,
        description="Instante (ISO 8601); solo se usa su fecha. Si se omite, el último día curado.",
    ),
) -> RespuestaAsistente:
    """Invoca `mejor_hora_zona` y construye una `RespuestaAsistente`."""
    r = tools.mejor_hora_zona(zona, perfil, momento)
    pregunta = f"¿A qué hora conviene salir hoy por «{zona}» ({perfil})?"

    if not r.disponible:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No se pudo calcular la mejor hora. Motivo: {r.motivo or 'sin datos'}. "
                + (f"Distritos: {', '.join(r.zonas_disponibles)}." if r.zonas_disponibles else "")
            ),
            fuentes=[],
        )

    explicacion = (
        f"En {r.distrito} ({r.dia}, perfil {r.perfil}) la franja más limpia es "
        f"{r.franja_inicio:02d}:00–{r.franja_fin:02d}:00; la mejor hora concreta es "
        f"{r.mejor_hora:02d}:00 y la peor {r.peor_hora:02d}:00 "
        f"(−{r.reduccion_vs_peor_pct:.0f}% de exposición ponderada entre una y otra, "
        f"media de {r.n_nodos_zona} nodos del distrito). Barrido de 24 h sobre la previsión "
        "del STGNN de grafo + NO₂/O₃ interpolados + ruido diario por distrito — demostración "
        "de metodología (memoria §7.4), 3 días curados; el O₃ (pico de tarde) marca la curva. "
        "Agregado por zona, sin datos personales; describe la previsión de aire y hora, no "
        "señala barrios; apoyo a la decisión, no consejo médico."
    )
    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=Veredicto.FAVORABLE,
        fiabilidad=NivelFiabilidad.BAJA,  # tope a propósito (§7.4)
        explicacion=explicacion,
        fuentes=[
            FuenteConsultada(
                dataset="grafo_ruta.json (FIL_37/FIL_45 — grafo coords-knn8 + previsión STGNN + ruido por distrito)",
                resumen=(
                    f"{r.distrito}: mejor hora {r.mejor_hora:02d}:00, franja "
                    f"{r.franja_inicio:02d}–{r.franja_fin:02d}, perfil {r.perfil}"
                ),
            ),
        ],
    )
