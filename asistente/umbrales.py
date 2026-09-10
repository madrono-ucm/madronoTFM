"""Umbrales OMS/UE de referencia para contaminantes atmosféricos -- fuente
única para que `asistente/mcp_agent/tools.py`, `viz/build_mapa_animado.py`,
`viz/build_grafo_ruta.py` y `viz/rutas.py` no mantengan copias
independientes que puedan desincronizarse en silencio (`FIL_87`, hallazgo
de `VIC_39`: los cuatro coincidían en estos valores a fecha de esa QA, pero
sin ningún módulo compartido que lo garantice si alguien actualiza un
límite en un solo sitio tras revisar la normativa).
"""

from __future__ import annotations

# Límite/umbral horario de referencia por contaminante (µg/m³), usado *solo*
# para elegir de forma simple qué contaminante destacar cuando una zona/hora
# reporta varios, o para normalizar una puntuación -- no es un cálculo del
# Índice de Calidad del Aire oficial (que combina más señales y periodos de
# promediado distintos por contaminante). NO2/SO2/O3 usan su límite/umbral
# horario oficial; PM10/PM2.5/CO no tienen límite horario oficial, así que
# se usa su límite diario/anual/8h como referencia aproximada --
# deliberadamente simple, ver `asistente/README.md`.
LIMITE_REFERENCIA_UGM3: dict[str, float] = {
    "NO2": 200.0,
    "SO2": 350.0,
    "O3": 180.0,
    "PM10": 50.0,
    "PM2.5": 25.0,
    "CO": 10_000.0,  # 10 mg/m3
}

# Cortes de banda OMS/UE de 4 niveles (usados para colorear el mapa animado,
# `viz/build_mapa_animado.py`) -- un esquema de clasificación distinto del
# límite único de arriba: el corte que coincide con `LIMITE_REFERENCIA_UGM3`
# no está siempre en la misma posición (para NO2 es el último corte, para
# O3 es el penúltimo), porque son umbrales regulatorios distintos con
# semántica propia (guía OMS, objetivo UE, umbral de información, umbral de
# alerta), no el mismo número reetiquetado cuatro veces.
BANDAS_UGM3: dict[str, list[float]] = {
    "no2": [25, 40, 100, 200],
    "o3": [100, 120, 180, 240],
}
