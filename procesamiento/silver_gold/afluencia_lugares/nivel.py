"""Fórmula de `nivel_estimado` de afluencia — fuente de verdad única (FIL_06).

Extraído de `asistente/mcp_agent/tools.py::_afluencia_estimada_impl` (tarea
089) para que lo compartan **la tool del asistente** (respuesta en vivo) y
**el job por lotes** (`procesamiento/afluencia_lugares/`, que materializa la
señal como serie temporal Gold). Un cambio de fórmula se hace aquí una vez,
no en dos sitios.

`nivel_estimado` combina tres señales de actividad urbana medidas cerca del
lugar (tráfico, ruido, ocupación de BiciMAD; la calidad del aire NO
contribuye, solo se reporta para trazabilidad). Cada señal se clasifica en
una severidad 0/1/2 con bandas de referencia aproximadas —**simplificación
deliberada documentada**, no un índice oficial de "cuánta gente hay"—, se
promedian las severidades disponibles y el promedio se reclasifica a
`bajo`/`medio`/`alto`. Sin ninguna señal: `sin_datos`.
"""

from __future__ import annotations

Bandas = "tuple[tuple[float, str], ...]"

# `avg_service_level` de tráfico (nivel de servicio, escala ~1-5).
UMBRALES_SERVICE_LEVEL: Bandas = ((1.5, "fluido"), (3.5, "denso"))
# Fallback cuando no hay `avg_service_level` pero sí `avg_occupancy_ratio` (0-1).
UMBRALES_OCCUPANCY_RATIO: Bandas = ((0.3, "fluido"), (0.6, "denso"))
# `avg_laeq_db` (ruido ambiental, dB): guía de ruido ambiental UE/OMS
# (<55 bajo, 55-70 medio, >70 alto). No mide aforo, es contaminación acústica.
UMBRALES_RUIDO_DB: Bandas = ((55.0, "bajo"), (70.0, "medio"))
# `avg_occupancy_ratio` de BiciMAD (0-1): se asume ratio más alto = estación
# más usada = más actividad alrededor (no verificado contra definición oficial).
UMBRALES_BICIMAD_OCUPACION: Bandas = ((0.3, "bajo"), (0.6, "medio"))

_SEVERIDAD_POR_ETIQUETA = {
    "fluido": 0, "bajo": 0,
    "denso": 1, "medio": 1,
    "congestionado": 2, "alto": 2,
}
_SEVERIDAD_A_NIVEL: Bandas = ((0.75, "bajo"), (1.5, "medio"))

SIN_DATOS = "sin_datos"


def clasificar(valor: float, umbrales: Bandas) -> str:
    """Primera etiqueta cuyo límite es mayor que `valor`; `"alto"` si ninguno."""
    for limite, etiqueta in umbrales:
        if valor < limite:
            return etiqueta
    return "alto"


def _media(valores: "list[float]") -> "float | None":
    limpios = [v for v in valores if v is not None]
    return sum(limpios) / len(limpios) if limpios else None


def nivel_estimado(
    *,
    service_levels: "list[float] | None" = None,
    traffic_occupancies: "list[float] | None" = None,
    noise_dbs: "list[float] | None" = None,
    bicimad_occupancies: "list[float] | None" = None,
) -> str:
    """`bajo` / `medio` / `alto` / `sin_datos` a partir de los valores de los
    sensores cercanos ya recogidos (una lista por tipo de señal).

    - Tráfico: se usa `service_levels` si hay alguno; si no, `traffic_occupancies`.
    - Ruido y BiciMAD: se promedian sus listas respectivas.
    Cada señal disponible aporta una severidad 0/1/2; el promedio se
    reclasifica. Sin ninguna señal -> `sin_datos`.
    """
    severidades: "list[int]" = []

    media_sl = _media(service_levels or [])
    if media_sl is not None:
        severidades.append(_SEVERIDAD_POR_ETIQUETA[clasificar(media_sl, UMBRALES_SERVICE_LEVEL)])
    else:
        media_occ = _media(traffic_occupancies or [])
        if media_occ is not None:
            severidades.append(_SEVERIDAD_POR_ETIQUETA[clasificar(media_occ, UMBRALES_OCCUPANCY_RATIO)])

    media_ruido = _media(noise_dbs or [])
    if media_ruido is not None:
        severidades.append(_SEVERIDAD_POR_ETIQUETA[clasificar(media_ruido, UMBRALES_RUIDO_DB)])

    media_bici = _media(bicimad_occupancies or [])
    if media_bici is not None:
        severidades.append(_SEVERIDAD_POR_ETIQUETA[clasificar(media_bici, UMBRALES_BICIMAD_OCUPACION)])

    if not severidades:
        return SIN_DATOS
    return clasificar(sum(severidades) / len(severidades), _SEVERIDAD_A_NIVEL)
