"""Endpoint HTTP para la tool `calidad_aire_prevista` (tarea `ML_09`).

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

router = APIRouter(tags=["calidad-aire-prevista"])

_VEREDICTO_POR_NIVEL = {
    "buena": Veredicto.FAVORABLE,
    "regular": Veredicto.FAVORABLE,
    "mala": Veredicto.CON_PRECAUCION,
    "muy mala": Veredicto.DESFAVORABLE,
    "sin_clasificar": Veredicto.CON_PRECAUCION,
}


@router.get("/calidad-aire-prevista", response_model=RespuestaAsistente)
def consultar_calidad_aire_prevista(
    zona: str,
    horizonte_horas: int = Query(default=6, description="Horas por delante: 1, 3 o 6."),
    momento: datetime | None = Query(
        default=None, description="Instante de referencia (ISO 8601). Si se omite, ahora."
    ),
) -> RespuestaAsistente:
    """Invoca `calidad_aire_prevista` y construye una `RespuestaAsistente` trazable."""
    r = tools.calidad_aire_prevista(zona, horizonte_horas, momento)
    pregunta = f"¿Cómo estará la calidad del aire en «{zona}» dentro de {horizonte_horas} h?"

    if r.nivel_previsto == "sin_datos":
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No hay ninguna estación de la red de calidad del aire cuyo nombre o "
                f"identificador contenga «{zona}» con lecturas recientes para construir la "
                "previsión. La resolución de «zona» es por texto sobre el nombre de la "
                "estación (ver asistente/README.md)."
            ),
            fuentes=[FuenteConsultada(dataset=r.fuente_dataset, resumen=f"Sin estaciones para «{zona}»")],
        )

    if r.valor_previsto is None:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"Estación «{r.estacion}»: hay lectura actual de {r.contaminante} "
                f"({r.valor_actual} {r.unidad or 'µg/m³'}) pero no está disponible el modelo "
                f"ONNX del horizonte {r.horizonte_horas} h (asistente/modelos/). "
                "Genéralo con `python -m modelado.export.to_onnx`."
            ),
            fuentes=[FuenteConsultada(dataset=r.fuente_dataset, resumen=f"{r.estacion}: sin modelo h{r.horizonte_horas}")],
        )

    # fiabilidad por cobertura de features históricas (mismo criterio que
    # afluencia_estimada: baja cuando faltan datos)
    if r.data_completeness >= 0.8:
        fiabilidad = NivelFiabilidad.MEDIA  # tope MEDIA: ventana de datos corta (§7.4)
    elif r.data_completeness >= 0.4:
        fiabilidad = NivelFiabilidad.BAJA
    else:
        fiabilidad = NivelFiabilidad.BAJA

    veredicto = _VEREDICTO_POR_NIVEL.get(r.nivel_previsto, Veredicto.CON_PRECAUCION)
    explicacion = (
        f"Previsión para «{r.estacion}» a {r.horizonte_horas} h: {r.contaminante} ≈ "
        f"{r.valor_previsto} {r.unidad or 'µg/m³'} (nivel simplificado: {r.nivel_previsto}; "
        f"lectura actual {r.valor_actual}). Modelo {r.modelo}. "
        f"Cobertura de features históricas: {r.data_completeness:.0%}. "
        "Índice orientativo (no el ICA oficial) y ventana de entrenamiento corta "
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
                    f"{r.contaminante} previsto {r.valor_previsto} {r.unidad or 'µg/m³'} a "
                    f"{r.horizonte_horas} h ({r.estacion}); modelo {r.modelo}"
                ),
                consultado_en=r.momento,
            )
        ],
    )
