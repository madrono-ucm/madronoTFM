"""Endpoint HTTP para la tool `calidad_aire_episodio` (`FIL_79`).

Igual que el resto de routers: prueba la tool sin cliente MCP
(`curl`/`httpx`). El agente MCP la expone también sin pasar por HTTP.
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

router = APIRouter(tags=["calidad-aire-episodio"])


@router.get("/calidad-aire-episodio", response_model=RespuestaAsistente)
def consultar_calidad_aire_episodio(
    zona: str,
    horizonte_horas: int = Query(default=6, description="Horas por delante: 1, 3 o 6."),
    momento: datetime | None = Query(
        default=None, description="Instante de referencia (ISO 8601). Si se omite, ahora."
    ),
) -> RespuestaAsistente:
    """Invoca `calidad_aire_episodio` y construye una `RespuestaAsistente`."""
    r = tools.calidad_aire_episodio(zona, horizonte_horas, momento)
    pregunta = (
        f"¿Probabilidad de episodio de contaminación cerca de «{zona}» "
        f"dentro de {horizonte_horas} h?"
    )

    if not r.disponible:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No hay estimación de episodio para «{zona}». "
                f"Motivo: {r.motivo or 'sin previsión disponible'}."
            ),
            fuentes=[FuenteConsultada(dataset=r.fuente_dataset or "gold.calidad_aire", resumen=r.motivo or "sin datos")],
        )

    veredicto = Veredicto.DESFAVORABLE if r.veredicto == "supera" else Veredicto.FAVORABLE
    if r.prob_superacion is not None and 0.35 <= r.prob_superacion <= 0.65:
        veredicto = Veredicto.CON_PRECAUCION
    explicacion = (
        f"Estación «{r.estacion}», {r.contaminante}: previsión a {r.horizonte_horas} h "
        f"≈ {r.valor_previsto} {r.unidad or 'µg/m³'} frente al umbral de referencia "
        f"OMS/UE {r.umbral} (margen {r.margen:+}). Probabilidad de superación "
        f"≈ {r.prob_superacion:.0%} → {r.veredicto}. "
        f"Derivado de la previsión de regresión ({r.modelo}); "
        f"cobertura de features {r.data_completeness:.0%}. Estimación orientativa, "
        "ventana de entrenamiento corta y pipeline de datos pausado (memoria §7.4)."
    )
    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=veredicto,
        fiabilidad=NivelFiabilidad.BAJA,
        explicacion=explicacion,
        fuentes=[
            FuenteConsultada(
                dataset=r.fuente_dataset or "gold.calidad_aire",
                resumen=(
                    f"P(superación {r.contaminante} > {r.umbral}) ≈ {r.prob_superacion:.0%} "
                    f"a {r.horizonte_horas} h ({r.estacion})"
                ),
                consultado_en=r.momento,
            )
        ],
    )
