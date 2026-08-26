"""Endpoint HTTP para la tool `eventos_cercanos` (tarea 095).

Existe para poder probar la tool sin un cliente MCP (`curl`/`httpx` directos,
ver `asistente/README.md`) -- el propio agente MCP la expone también, sin
pasar por HTTP, vía `asistente/mcp_agent/server.py`.

A diferencia del resto de routers (`calidad_aire.py`, `trafico_cercano.py`,
`disponibilidad_aparcamiento.py`), `tools.eventos_cercanos` devuelve
`list[EventoCercano]`, no un único modelo con `momento`/`fuente_dataset` --
este router construye la `RespuestaAsistente` a partir de la lista
directamente, sin desempaquetar ningún campo compartido.
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

router = APIRouter(tags=["eventos-cercanos"])


@router.get("/eventos-cercanos", response_model=RespuestaAsistente)
def consultar_eventos_cercanos(
    lugar: str,
    radio_m: float = Query(default=500.0, description="Radio de búsqueda en metros alrededor de `lugar`."),
    momento: datetime | None = Query(
        default=None,
        description="Instante de referencia (ISO 8601). Se buscan eventos hasta 30 días después. Si se omite, se usa el instante actual.",
    ),
) -> RespuestaAsistente:
    """Invoca la tool `eventos_cercanos` y construye una `RespuestaAsistente` trazable."""
    eventos = tools.eventos_cercanos(lugar, radio_m, momento)
    pregunta = f"¿Hay algún evento cerca de «{lugar}» próximamente?"
    # A diferencia de `calidad_aire`/`trafico_cercano` (que siempre devuelven
    # una instancia con `fuente_dataset`, incluso sin coincidencias),
    # `eventos_cercanos` devuelve una lista vacía sin ningún dato de origen
    # que leer -- se fija aquí el mismo literal que
    # `tools._FUENTE_AGENDA_EVENTOS_SILVER` en vez de depender de que la
    # lista no esté vacía.
    fuente_dataset = "silver.agenda_eventos"

    if not eventos:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=(
                f"No se ha encontrado ningún `:Lugar` del grafo cuyo nombre contenga "
                f"«{lugar}», o ningún evento de la agenda municipal en un radio de "
                f"{radio_m:.0f}m en los próximos 30 días. Esta tool resuelve «lugar» "
                "por coincidencia de texto (ver asistente/README.md)."
            ),
            fuentes=[
                FuenteConsultada(
                    dataset=fuente_dataset,
                    resumen=f"Sin eventos cercanos a «{lugar}»",
                )
            ],
        )

    primero = eventos[0]
    explicacion = (
        f"{len(eventos)} evento(s) encontrado(s) cerca de «{lugar}» (radio {radio_m:.0f}m) "
        f"en los próximos 30 días. El más cercano: «{primero.nombre}» en «{primero.lugar}», "
        f"a {primero.distancia_m:.0f}m, {primero.inicio:%d/%m %H:%M}."
    )

    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=Veredicto.FAVORABLE,
        fiabilidad=NivelFiabilidad.ALTA if len(eventos) == 1 else NivelFiabilidad.MEDIA,
        explicacion=explicacion,
        fuentes=[
            FuenteConsultada(
                dataset=evento.fuente_dataset,
                resumen=(
                    f"«{evento.nombre}» en «{evento.lugar}», {evento.distancia_m:.0f}m, "
                    f"{evento.inicio:%d/%m %H:%M}"
                ),
                consultado_en=evento.inicio,
            )
            for evento in eventos[:5]
        ],
    )
