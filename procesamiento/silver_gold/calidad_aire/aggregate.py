"""Agregación Silver -> Gold del dataset `calidad_aire`: valor medio/máx/mín por
estación, contaminante y hora.

Se agrupa por **`(station_id, pollutant, fecha, hora)`** -- a diferencia del
resto de datasets del patrón (que agrupan solo por punto de medida/estación/
aparcamiento), aquí una misma estación reporta varios contaminantes
simultáneamente (cada uno con su propia unidad y escala), así que mezclarlos
en un solo agregado por estación+hora no tendría sentido (la media de un
NO2 y un CO en la misma fila sería una magnitud sin significado). El
contaminante es, junto con la estación y la hora, parte de la clave natural
de agregación.

La hora de agregación se deriva de `measured_at` (ya en hora de Madrid,
mismo criterio que `trafico/aggregate.py`). Un registro sin `measured_at`
parseable se ignora -- no debería ocurrir: Silver ya exige `measured_at`
válido en su puerta de calidad (ver `transform.py`).
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
    """Agrega registros Silver de `calidad_aire` por estación, contaminante y hora (Madrid)."""
    buckets: "dict[tuple[str, str, str, int], list[dict]]" = {}

    for record in records:
        measured_at = _parse_iso(record.get("measured_at"))
        station_id = record.get("station_id")
        pollutant = record.get("pollutant")
        if measured_at is None or not station_id or not pollutant:
            continue
        key = (station_id, pollutant, measured_at.date().isoformat(), measured_at.hour)
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (station_id, pollutant, date_str, hour), bucket in sorted(buckets.items()):
        measured_ats = sorted(
            m for m in (_parse_iso(r.get("measured_at")) for r in bucket) if m is not None
        )
        location = bucket[0].get("location") or {}
        values = [r.get("value") for r in bucket]

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "station_id": station_id,
                "station_name": bucket[0].get("station_name"),
                "magnitude_code": bucket[0].get("magnitude_code"),
                "pollutant": pollutant,
                "pollutant_name": bucket[0].get("pollutant_name"),
                "unit": bucket[0].get("unit"),
                "date": date_str,
                "hour": hour,
                "samples_count": len(bucket),
                "first_measured_at": measured_ats[0].isoformat() if measured_ats else None,
                "last_measured_at": measured_ats[-1].isoformat() if measured_ats else None,
                "avg_value": _avg(values),
                "max_value": max((v for v in values if v is not None), default=None),
                "min_value": min((v for v in values if v is not None), default=None),
                "location": {
                    "lat": location.get("lat"),
                    "lon": location.get("lon"),
                    "srid": "EPSG:4326",
                },
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
