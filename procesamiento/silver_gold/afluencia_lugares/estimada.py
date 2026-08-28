"""Construcción de filas Gold de `afluencia_lugares` a partir de la señal
**derivada** de sensores vía el grafo (FIL_06 parte 2, sustituye a Google
Popular Times).

Puro: sin `neo4j`, sin `boto3`, sin Spark. El job de Glue
(`glue_estimada.py`) hace la E/S (SSM → Neo4j → Athena) y llama a
`fila_gold` una vez por `:Lugar`. La fórmula de `nivel_estimado` vive en
`nivel.py` (compartida con la tool en vivo del asistente, tarea 089).

Esquema de una fila Gold (`afluencia_lugares_por_lugar_fecha_hora`):

    lugar_id, tipo, lat, lon, date, hora,
    nivel_estimado,                     # bajo|medio|alto|sin_datos
    n_trafico, n_ruido, n_bicimad, n_calidad_aire,   # nº de sensores cercanos con dato
    avg_service_level, avg_laeq_db, avg_bicimad_occ, avg_aqi_value,
    data_completeness,                  # 0..4 -> de cuántas de las 4 señales había dato
    schema_version, processed_at
"""

from __future__ import annotations

from datetime import datetime

from .nivel import SIN_DATOS, nivel_estimado

SCHEMA_VERSION = 1

# `tipo` del sensor en el grafo -> señal de afluencia. `trafico`/`ruido`/
# `calidad_aire` son `:EstacionMedida`; `bicimad` es `:ParadaTransporte`.
_TIPOS_SENSOR = ("trafico", "ruido", "calidad_aire", "bicimad")


def sensores_por_tipo(filas_proximo_a: "list[dict]") -> "dict[str, dict[str, float]]":
    """Agrupa los resultados de la consulta `PROXIMO_A` del grafo por `tipo`
    de sensor, devolviendo `{tipo: {id_real: distancia_m}}`. `id_real` es el
    identificador tras el prefijo `"<fuente>:"` del nodo (mismo criterio que
    `asistente/mcp_agent/tools.py::_agregar_por_id`); si el mismo sensor
    aparece por varios `:Lugar` coincidentes, se queda la distancia mínima.
    """
    salida: "dict[str, dict[str, float]]" = {t: {} for t in _TIPOS_SENSOR}
    for fila in filas_proximo_a:
        tipo = fila.get("tipo")
        nodo_id = fila.get("id") or ""
        dist = fila.get("distancia_m")
        if tipo not in salida or dist is None or ":" not in nodo_id:
            continue
        id_real = nodo_id.split(":", 1)[1]
        actual = salida[tipo].get(id_real)
        if actual is None or dist < actual:
            salida[tipo][id_real] = dist
    return salida


def _media(valores: "list") -> "float | None":
    limpios = [v for v in valores if v is not None]
    return sum(limpios) / len(limpios) if limpios else None


def fila_gold(
    *,
    lugar: dict,
    sensores: "dict[str, dict[str, float]]",
    valores_gold: "dict[str, dict[str, dict]]",
    fecha: str,
    hora: int,
    processed_at: datetime,
) -> dict:
    """Una fila Gold para un `:Lugar`.

    - `lugar`: `{"id", "tipo", "lat", "lon"}`.
    - `sensores`: salida de `sensores_por_tipo` (por tipo -> id_real -> dist).
    - `valores_gold`: por tipo -> id_real -> fila Gold ya filtrada a la
      `hora` objetivo, con las columnas que necesita cada señal
      (`avg_service_level`/`avg_occupancy_ratio` para tráfico, `avg_laeq_db`
      para ruido, `avg_occupancy_ratio` para bicimad, `avg_value` para
      calidad del aire).
    """
    service_levels: "list[float]" = []
    traffic_occ: "list[float]" = []
    for sid in sensores.get("trafico", {}):
        g = valores_gold.get("trafico", {}).get(sid) or {}
        if g.get("avg_service_level") is not None:
            service_levels.append(g["avg_service_level"])
        if g.get("avg_occupancy_ratio") is not None:
            traffic_occ.append(g["avg_occupancy_ratio"])

    noise = [
        (valores_gold.get("ruido", {}).get(sid) or {}).get("avg_laeq_db")
        for sid in sensores.get("ruido", {})
    ]
    bici = [
        (valores_gold.get("bicimad", {}).get(sid) or {}).get("avg_occupancy_ratio")
        for sid in sensores.get("bicimad", {})
    ]
    aqi = [
        (valores_gold.get("calidad_aire", {}).get(sid) or {}).get("avg_value")
        for sid in sensores.get("calidad_aire", {})
    ]

    nivel = nivel_estimado(
        service_levels=service_levels,
        traffic_occupancies=traffic_occ,
        noise_dbs=[v for v in noise if v is not None],
        bicimad_occupancies=[v for v in bici if v is not None],
    )

    n_trafico = len(
        [
            sid
            for sid in sensores.get("trafico", {})
            if (valores_gold.get("trafico", {}).get(sid) or {}).get("avg_service_level") is not None
            or (valores_gold.get("trafico", {}).get(sid) or {}).get("avg_occupancy_ratio") is not None
        ]
    )
    n_ruido = len([v for v in noise if v is not None])
    n_bicimad = len([v for v in bici if v is not None])
    n_calidad = len([v for v in aqi if v is not None])
    data_completeness = sum(1 for n in (n_trafico, n_ruido, n_bicimad, n_calidad) if n)

    return {
        "schema_version": SCHEMA_VERSION,
        "lugar_id": lugar["id"],
        "tipo": lugar.get("tipo"),
        "lat": lugar.get("lat"),
        "lon": lugar.get("lon"),
        "date": fecha,
        "hora": hora,
        "nivel_estimado": nivel,
        "n_trafico": int(n_trafico),
        "n_ruido": int(n_ruido),
        "n_bicimad": int(n_bicimad),
        "n_calidad_aire": int(n_calidad),
        "avg_service_level": _media(service_levels),
        "avg_laeq_db": _media(noise),
        "avg_bicimad_occ": _media(bici),
        "avg_aqi_value": _media(aqi),
        "data_completeness": data_completeness,
        "processed_at": processed_at.isoformat(),
    }


def es_sin_datos(fila: dict) -> bool:
    return fila["nivel_estimado"] == SIN_DATOS
