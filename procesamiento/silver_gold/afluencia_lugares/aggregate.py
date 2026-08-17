"""Agregación Silver -> Gold del dataset `afluencia_lugares`: por
`(place_id, fecha, hora)`.

Criterio de agregación (decidido por el enunciado de la tarea, implementado
tal cual, sin evaluar alternativas): `live_pct` medio del bucket cuando esté
disponible, junto con el valor de `typical_by_hour` correspondiente a ese
día de la semana/hora, tomado del propio registro. El día de la semana y la
hora se derivan de `ingested_at` (el único timestamp de este dataset, ver
`transform.py`) -- como todos los registros de un mismo bucket comparten,
por construcción de la clave, el mismo día de la semana y la misma hora, el
valor típico correspondiente es el mismo para todos ellos salvo que alguno
no tenga `typical_by_hour` (lugar sin datos suficientes en Google, ver
`transform.py`); por eso se promedia igual que `live_pct` en vez de tomar
solo el primero -- mismo criterio de "ignora ausentes, promedia presentes"
en toda métrica de este dataset.
"""

from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Optional

from .transform import WEEKDAY_KEYS_ES

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


def _typical_value_for(typical_by_hour: Optional[dict], weekday_index: int, hour: int) -> Optional[float]:
    """Devuelve el valor típico de `typical_by_hour` para un día de la semana y hora concretos.

    `weekday_index` sigue la convención de `datetime.weekday()` (lunes=0);
    `WEEKDAY_KEYS_ES` (mismo orden que `ingesta/capturas/afluencia_lugares_madrid.py`)
    lo traduce a la clave de día en español.
    """
    if not typical_by_hour:
        return None
    day_values = typical_by_hour.get(WEEKDAY_KEYS_ES[weekday_index])
    if not day_values or hour >= len(day_values):
        return None
    return day_values[hour]


def aggregate_silver_to_gold(records: "list[dict]", processed_at: datetime) -> "list[dict]":
    """Agrega registros Silver de `afluencia_lugares` por lugar, fecha y hora.

    Un registro sin `ingested_at` parseable o sin `place_id` se ignora (no
    debería ocurrir: Silver ya exige ambos en su puerta de calidad, ver
    `transform.py`).
    """
    buckets: "dict[tuple[str, str, int], list[dict]]" = {}

    for record in records:
        ingested_at = _parse_iso(record.get("ingested_at"))
        place_id = record.get("place_id")
        if ingested_at is None or not place_id:
            continue
        key = (place_id, ingested_at.date().isoformat(), ingested_at.hour)
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (place_id, date_str, hour), bucket in sorted(buckets.items()):
        ingested_ats = sorted(
            m for m in (_parse_iso(r.get("ingested_at")) for r in bucket) if m is not None
        )
        weekday_index = datetime.fromisoformat(date_str).weekday()
        day_of_week = WEEKDAY_KEYS_ES[weekday_index]

        live_pcts = [r.get("live_pct") for r in bucket]
        typical_values = [
            _typical_value_for(r.get("typical_by_hour"), weekday_index, hour) for r in bucket
        ]

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "place_id": place_id,
                "name": bucket[0].get("name"),
                "date": date_str,
                "hour": hour,
                "day_of_week": day_of_week,
                "samples_count": len(bucket),
                "avg_live_pct": _avg(live_pcts),
                "typical_pct": _avg(typical_values),
                "lat": bucket[0].get("lat"),
                "lon": bucket[0].get("lon"),
                "first_ingested_at": ingested_ats[0].isoformat() if ingested_ats else None,
                "last_ingested_at": ingested_ats[-1].isoformat() if ingested_ats else None,
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
