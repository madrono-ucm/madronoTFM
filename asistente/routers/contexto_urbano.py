"""Endpoint HTTP para la tool `contexto_urbano` (`FIL_53`).

Igual que el resto de routers: probar la tool sin un cliente MCP.
"""

from __future__ import annotations

from fastapi import APIRouter

from asistente.mcp_agent import tools
from asistente.models.respuesta import (
    FuenteConsultada,
    NivelFiabilidad,
    RespuestaAsistente,
    Veredicto,
)

router = APIRouter(tags=["contexto-urbano"])


@router.get("/contexto-urbano", response_model=RespuestaAsistente)
def consultar_contexto_urbano(lugar: str) -> RespuestaAsistente:
    """Invoca `contexto_urbano` y construye una `RespuestaAsistente`."""
    r = tools.contexto_urbano(lugar)
    pregunta = f"¿Qué hay alrededor de «{lugar}» en el grafo urbano?"

    if not r.disponible:
        return RespuestaAsistente(
            pregunta=pregunta,
            veredicto=Veredicto.CON_PRECAUCION,
            fiabilidad=NivelFiabilidad.BAJA,
            explicacion=f"No se pudo dar contexto de grafo para «{lugar}». Motivo: {r.motivo}",
            fuentes=[],
        )

    n_est = sum(len(v) for v in r.estaciones_1_salto.values())
    tipos_est = ", ".join(f"{k} ({len(v)})" for k, v in r.estaciones_1_salto.items()) or "ninguna"
    n_lug = sum(len(v) for v in r.lugares_cercanos_2_saltos.values())
    t = r.transporte
    explicacion = (
        f"«{r.lugar}» ({r.tipo}) está en el barrio {r.barrio}, distrito {r.distrito}. "
        f"A 1 salto de `PROXIMO_A`: {n_est} estaciones de medida — {tipos_est}. "
        f"A ≤2 saltos: {n_lug} lugares (parques/aparcamientos/POIs). "
        + (f"Desde la parada «{t.parada_ancla}» se alcanzan {t.alcanzables_2_saltos} paradas "
           f"a ≤2 saltos de `CONECTADO_CON` (p. ej. {', '.join(t.ejemplos[:4])})." if t and t.parada_ancla
           else "Sin parada de transporte cercana en el grafo.")
        + " Consulta multi-salto del grafo urbano reconstruido (memoria §6)."
    )
    return RespuestaAsistente(
        pregunta=pregunta,
        veredicto=Veredicto.FAVORABLE,
        fiabilidad=NivelFiabilidad.MEDIA,
        explicacion=explicacion,
        fuentes=[
            FuenteConsultada(
                dataset=r.fuente_grafo or "grafo_urbano",
                resumen=(
                    f"{r.lugar} · barrio {r.barrio} / distrito {r.distrito} · "
                    f"{n_est} estaciones a 1 salto · {t.alcanzables_2_saltos if t else 0} paradas a ≤2 saltos"
                ),
            ),
        ],
    )
