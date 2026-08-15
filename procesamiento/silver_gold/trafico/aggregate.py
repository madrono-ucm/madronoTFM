"""Agregación Silver -> Gold del dataset `trafico`: media por punto de medida y hora.

Criterio de agregación (ver `procesamiento/README.md` para la justificación
completa): se agrupa por `(point_id, fecha, hora)` en vez de por distrito.
Cruzar con `barrios_distritos_madrid` (tarea 010) para agregar por distrito
es una mejora natural, pero exigiría resolver qué distrito contiene cada
punto de tráfico (un `point-in-polygon` con las geometrías de barrios) — ese
cruce es justo el tipo de relación espacial que la tarea 043 (grafo Neo4j)
va a modelar explícitamente; anticiparlo aquí con una heurística ad-hoc
duplicaría ese trabajo con peor información (sin el grafo, solo se podría
aproximar por bounding box o vecino más cercano). Para un piloto de una sola
fuente, la agregación por punto de medida ya reduce el volumen de Silver
(una fila cada ~5 minutos por sensor) a una fila por hora sin perder
resolución espacial, y es la agregación mínima que cualquier consumidor de
Gold necesitaría de todos modos antes de, más adelante, volver a agregar por
distrito.
"""

from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Optional

SCHEMA_VERSION = 1


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _avg(values: "list[Optional[float]]") -> Optional[float]:
    present = [v for v in values if v is not None]
    return mean(present) if present else None


def aggregate_silver_to_gold(records: "list[dict]", processed_at: datetime) -> "list[dict]":
    """Agrega registros Silver de `trafico` por punto de medida y hora (Madrid).

    La hora de agregación se deriva de `measured_at` (ya en hora de Madrid,
    tareas 034-039), truncado a la hora en punto. Un registro sin
    `measured_at` parseable se ignora (no debería ocurrir: Silver ya exige
    `measured_at` válido en su puerta de calidad, ver `transform.py`).
    """
    buckets: "dict[tuple[str, str, int], list[dict]]" = {}

    for record in records:
        measured_at = _parse_iso(record.get("measured_at"))
        point_id = record.get("point_id")
        if measured_at is None or not point_id:
            continue
        key = (point_id, measured_at.date().isoformat(), measured_at.hour)
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (point_id, date_str, hour), bucket in sorted(buckets.items()):
        measured_ats = sorted(
            m for m in (_parse_iso(r.get("measured_at")) for r in bucket) if m is not None
        )
        location = bucket[0].get("location") or {}
        intensities = [r.get("intensity_vph") for r in bucket]

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "point_id": point_id,
                "subarea": bucket[0].get("subarea"),
                "date": date_str,
                "hour": hour,
                "samples_count": len(bucket),
                "first_measured_at": measured_ats[0].isoformat() if measured_ats else None,
                "last_measured_at": measured_ats[-1].isoformat() if measured_ats else None,
                "avg_intensity_vph": _avg(intensities),
                "max_intensity_vph": max(
                    (v for v in intensities if v is not None), default=None
                ),
                "min_intensity_vph": min(
                    (v for v in intensities if v is not None), default=None
                ),
                "avg_occupancy_ratio": _avg([r.get("occupancy_ratio") for r in bucket]),
                "avg_load_ratio": _avg([r.get("load_ratio") for r in bucket]),
                "avg_intensity_ratio": _avg([r.get("intensity_ratio") for r in bucket]),
                "avg_service_level": _avg([r.get("service_level") for r in bucket]),
                "location": {
                    "lat": location.get("lat"),
                    "lon": location.get("lon"),
                    "srid": "EPSG:4326",
                },
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
