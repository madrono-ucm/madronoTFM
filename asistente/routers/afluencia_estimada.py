"""Endpoint HTTP para la tool `afluencia_estimada` (tarea 089).

Mismo motivo que `asistente/routers/trafico_cercano.py` (tarea 081): probar
la tool sin un cliente MCP -- el propio agente MCP la expone también, sin
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

router = APIRouter(tags=["afluencia-estimada"])

_VEREDICTO_POR_NIVEL = {
    "bajo": Veredicto.FAVORABLE,
    "medio": Veredicto.CON_PRECAUCION,
    "alto": Veredicto.DESFAVORABLE,
}


@router.get("/afluencia-estimada", response_model=RespuestaAsistente)
def consultar_afluencia_estimada(
    lugar: str,
    radio_m: float = Query(default=300.0, description="Radio de búsqueda en metros alrededor de `lugar`."),
    momento: datetime | None = Query(
        default=None,
        description="Instante a consultar (ISO 8601). Si se omite, se usa el instante actual.",
    ),
) -> RespuestaAsistente:
    """Invoca la tool `afluencia_estimada` y construye una `RespuestaAsistente` trazable."""
    resultado = tools.afluencia_estimada(lugar, radio_m, momento)
    pregunta = f"¿Cómo de concurrido está «{lugar}»?"

    total_nodos = len(resultado.trafico) + len(resultado.ruido) + len(resultado.bicimad) + len(resultado.calidad_aire)
    if resultado.nivel_estimado == "sin_datos" or total_nodos == 0:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No se ha encontrado ningún lugar del grafo cuyo nombre contenga «{lugar}» "
                f"con tráfico, ruido, BiciMAD o calidad del aire a menos de {radio_m:.0f}m, o no "
                "hay datos para la fecha/hora consultada. No es un conteo de personas -- ver "
                "asistente/README.md."
            ),
            fuentes=[
                FuenteConsultada(
                    dataset=resultado.fuente_grafo,
                    resumen=f"Sin nodos coincidentes con «{lugar}» dentro de {radio_m:.0f}m",
                )
            ],
        )

    fiabilidad = NivelFiabilidad.MEDIA if total_nodos > 1 else NivelFiabilidad.ALTA
    veredicto = _VEREDICTO_POR_NIVEL.get(resultado.nivel_estimado, Veredicto.CON_PRECAUCION)

    senales_presentes = [
        nombre
        for nombre, lista in (
            ("tráfico", resultado.trafico),
            ("ruido", resultado.ruido),
            ("BiciMAD", resultado.bicimad),
            ("calidad del aire", resultado.calidad_aire),
        )
        if lista
    ]

    explicacion = (
        f"Actividad urbana estimada cerca de «{lugar}»"
        + (f" a las {resultado.hora}:00" if resultado.hora is not None else "")
        + f": nivel {resultado.nivel_estimado}, combinando {', '.join(senales_presentes)} "
        f"a menos de {radio_m:.0f}m. Aproximación por actividad urbana general "
        "(tráfico/ruido/movilidad activa), no un conteo de personas -- ver "
        "asistente/mcp_agent/tools.py."
    )

    fuentes = [
        FuenteConsultada(
            dataset=resultado.fuente_grafo,
            resumen=f"{total_nodos} nodo(s) dentro de {radio_m:.0f}m de «{lugar}» ({', '.join(senales_presentes)})",
            consultado_en=resultado.momento,
        )
    ]
    for dataset in resultado.fuentes_gold:
        fuentes.append(
            FuenteConsultada(
                dataset=dataset,
                resumen=f"Señal consultada a las {resultado.hora}:00" if resultado.hora is not None else "Señal consultada",
                consultado_en=resultado.momento,
            )
        )

    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=veredicto,
        fiabilidad=fiabilidad,
        explicacion=explicacion,
        fuentes=fuentes,
    )
