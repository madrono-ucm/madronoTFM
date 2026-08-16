"""Agregación Silver -> Gold del dataset `transporte_publico_emt`: espera por parada, línea y hora.

Se agrupa por **`(stop_id, line, fecha, hora)`** -- una parada suele dar
servicio a varias líneas, y el tiempo de espera de cada una es una magnitud
distinta (frecuencias distintas), así que agregar solo por `stop_id`
mezclaría líneas con características muy diferentes en una única media sin
sentido. La hora de agregación se deriva de `ingested_at` (el instante en que
se observó cada estimación -- ver `transform.py` para por qué hace de
equivalente de `measured_at` en este dataset).

A diferencia de `trafico/aggregate.py`, esta agregación **no incluye
`location`**: aquí `location` es la posición GPS del autobús en el instante
de la estimación, no la de la parada -- cambia en cada muestra y no tiene un
valor "representativo" único por `(stop_id, line)` con el que agregar de
forma significativa (a diferencia de tráfico, donde el sensor tiene una
posición fija). Si una tarea futura necesita la ubicación de la parada en
Gold, la fuente correcta es el catálogo de paradas de la EMT (fuera del
alcance de esta tarea), no la posición del autobús en la última muestra.
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
    """Agrega registros Silver de `transporte_publico_emt` por parada, línea y hora (Madrid).

    La hora de agregación se deriva de `ingested_at` (ya en hora de Madrid),
    truncado a la hora en punto. Un registro sin `ingested_at` parseable se
    ignora (no debería ocurrir: Silver ya exige `ingested_at` válido en su
    puerta de calidad, ver `transform.py`).
    """
    buckets: "dict[tuple[str, str, str, int], list[dict]]" = {}

    for record in records:
        ingested_at = _parse_iso(record.get("ingested_at"))
        stop_id = record.get("stop_id")
        line = record.get("line")
        if ingested_at is None or not stop_id or not line:
            continue
        key = (stop_id, line, ingested_at.date().isoformat(), ingested_at.hour)
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (stop_id, line, date_str, hour), bucket in sorted(buckets.items()):
        ingested_ats = sorted(
            i for i in (_parse_iso(r.get("ingested_at")) for r in bucket) if i is not None
        )
        waits = [r.get("estimate_arrive_sec") for r in bucket]

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "stop_id": stop_id,
                "line": line,
                "date": date_str,
                "hour": hour,
                "samples_count": len(bucket),
                "first_ingested_at": ingested_ats[0].isoformat() if ingested_ats else None,
                "last_ingested_at": ingested_ats[-1].isoformat() if ingested_ats else None,
                "avg_estimate_arrive_sec": _avg(waits),
                "min_estimate_arrive_sec": min(
                    (v for v in waits if v is not None), default=None
                ),
                "max_estimate_arrive_sec": max(
                    (v for v in waits if v is not None), default=None
                ),
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
