"""Agregación Silver -> Gold del dataset `bicimad`: disponibilidad media por estación y hora.

Se agrupa por **`(station_id, fecha, hora)`**, mismo criterio de grano que
`trafico/aggregate.py` (una estación, a diferencia de una parada de EMT, sí
tiene una única ubicación fija -- ver `location` más abajo). La hora de
agregación se deriva de `measured_at` (hora de Madrid, ver
`ingesta/capturas/bicimad.py`/`bronze.py`).

Cada fila de Gold agrega, para las estaciones instaladas dentro de una hora
natural: `samples_count`, `avg_bikes_available`/`avg_bikes_disabled`/
`avg_docks_available`/`avg_docks_disabled` y `avg_occupancy_ratio` (media de
`bikes_available / docks_total` por muestra, ver `transform.py`) --
consistente con el patrón ya usado por `trafico/aggregate.py`
(`avg_occupancy_ratio` allí es la media de un ratio calculado en Silver, no
un ratio de las medias de Gold; mismo criterio aquí). `docks_total` se
conserva como el primer valor observado en el bucket (constante en la
práctica: la capacidad de una estación no cambia hora a hora), igual que
`location`/`name` (`trafico/aggregate.py` hace lo mismo con `lat`/`lon`).
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
    """Agrega registros Silver de `bicimad` por estación y hora (Madrid).

    La hora de agregación se deriva de `measured_at` (ya en hora de Madrid),
    truncado a la hora en punto. Un registro sin `measured_at` parseable se
    ignora (no debería ocurrir: Silver ya exige `measured_at` válido en su
    puerta de calidad, ver `transform.py`).
    """
    buckets: "dict[tuple[str, str, int], list[dict]]" = {}

    for record in records:
        measured_at = _parse_iso(record.get("measured_at"))
        station_id = record.get("station_id")
        if measured_at is None or not station_id:
            continue
        key = (station_id, measured_at.date().isoformat(), measured_at.hour)
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (station_id, date_str, hour), bucket in sorted(buckets.items()):
        measured_ats = sorted(
            m for m in (_parse_iso(r.get("measured_at")) for r in bucket) if m is not None
        )
        location = bucket[0].get("location") or {}

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "station_id": station_id,
                "name": bucket[0].get("name"),
                "date": date_str,
                "hour": hour,
                "samples_count": len(bucket),
                "first_measured_at": measured_ats[0].isoformat() if measured_ats else None,
                "last_measured_at": measured_ats[-1].isoformat() if measured_ats else None,
                "avg_bikes_available": _avg([r.get("bikes_available") for r in bucket]),
                "avg_bikes_disabled": _avg([r.get("bikes_disabled") for r in bucket]),
                "avg_docks_available": _avg([r.get("docks_available") for r in bucket]),
                "avg_docks_disabled": _avg([r.get("docks_disabled") for r in bucket]),
                "avg_occupancy_ratio": _avg([r.get("occupancy_ratio") for r in bucket]),
                "docks_total": bucket[0].get("docks_total"),
                "location": {
                    "lat": location.get("lat"),
                    "lon": location.get("lon"),
                    "srid": "EPSG:4326",
                },
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
