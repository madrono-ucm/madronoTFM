"""Endpoint HTTP para la tool `trafico_prevista` (`FIL_13`).

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

router = APIRouter(tags=["trafico-prevista"])

_VEREDICTO_POR_NIVEL = {
    "fluido": Veredicto.FAVORABLE,
    "denso": Veredicto.CON_PRECAUCION,
    "congestionado": Veredicto.DESFAVORABLE,
}


@router.get("/trafico-prevista", response_model=RespuestaAsistente)
def consultar_trafico_prevista(
    lugar: str,
    horizonte_horas: int = Query(default=6, description="Horas por delante: 1, 3 o 6."),
    radio_m: float = Query(default=300.0, description="Radio de búsqueda de puntos de tráfico (m)."),
    momento: datetime | None = Query(
        default=None, description="Instante de referencia (ISO 8601). Si se omite, ahora."
    ),
) -> RespuestaAsistente:
    """Invoca `trafico_prevista` y construye una `RespuestaAsistente` trazable."""
    r = tools.trafico_prevista(lugar, horizonte_horas, radio_m, momento)
    pregunta = f"¿Cómo estará el tráfico cerca de «{lugar}» dentro de {horizonte_horas} h?"

    if r.nivel_previsto == "sin_datos":
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No hay ningún punto de medida de tráfico a {radio_m:.0f} m "
                f"de «{lugar}» en el grafo, o `gold.trafico_por_punto_hora` no tiene lecturas "
                "recientes para construir la previsión. La resolución de «lugar» es por texto "
                "sobre el grafo (ver asistente/README.md)."
            ),
            fuentes=[FuenteConsultada(dataset=r.fuente_dataset, resumen=f"Sin puntos de tráfico para «{lugar}»")],
        )

    if r.valor_previsto is None:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"Punto «{r.punto_id}»: hay lectura actual de nivel de servicio "
                f"({r.valor_actual}) pero no está disponible el modelo ONNX del horizonte "
                f"{r.horizonte_horas} h (asistente/modelos/). Genéralo con "
                "`python -m modelado.export.to_onnx --modelo madrono-trafico-h<H>`."
            ),
            fuentes=[FuenteConsultada(dataset=r.fuente_dataset, resumen=f"{r.punto_id}: sin modelo h{r.horizonte_horas}")],
        )

    if r.data_completeness >= 0.8:
        fiabilidad = NivelFiabilidad.MEDIA  # tope MEDIA: ventana de datos corta (§7.4)
    else:
        fiabilidad = NivelFiabilidad.BAJA

    veredicto = _VEREDICTO_POR_NIVEL.get(r.nivel_previsto, Veredicto.CON_PRECAUCION)
    explicacion = (
        f"Previsión de tráfico cerca de «{r.lugar}» a {r.horizonte_horas} h (punto {r.punto_id}): "
        f"nivel de servicio ≈ {r.valor_previsto} → {r.nivel_previsto} "
        f"(lectura actual {r.valor_actual}). Modelo {r.modelo}. "
        f"Cobertura de features históricas: {r.data_completeness:.0%}; "
        f"ventana de datos {r.ventana_datos}. "
        "Etiqueta simplificada (no la escala oficial completa) y ventana de entrenamiento "
        "corta (demostración de metodología, ver memoria §7.4)."
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
                    f"{r.horizonte_horas} h (punto {r.punto_id}); modelo {r.modelo}"
                ),
                consultado_en=r.momento,
            ),
            FuenteConsultada(dataset=r.fuente_grafo or "neo4j", resumen=f"punto de tráfico ≤{radio_m} m de «{lugar}»"),
        ],
    )
