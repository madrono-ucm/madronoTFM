"""Agregación Silver -> Gold del dataset `aforos_peatones_bicicletas`: conteo
total/medio por estación, modo y hora.

Se agrupa por **`(station_id, mode, fecha, hora)`** -- igual que
`calidad_aire`/`meteorologia` (estación + etiqueta + hora), aquí la etiqueta
es `mode` (`"peatones"`/`"bicicletas"`): dos estaciones con el mismo
`station_id` no existen (las redes de peatones `PERM_PEA##` y de bicicletas
`PERM_BICI##` usan identificadores propios, ver `ingesta/capturas/
aforos_peatones_bicicletas_madrid.py`), pero incluir `mode` en la clave deja
la agregación correcta aunque eso cambiara, y documenta explícitamente que
`count` solo tiene sentido dentro de un mismo modo (sumar peatones y
bicicletas en un único total no sería una magnitud útil).

La hora de agregación se deriva de `measured_at` (ya en hora de Madrid,
mismo criterio que `trafico/aggregate.py`). Un registro sin `measured_at`
parseable se ignora -- no debería ocurrir: Silver ya exige `measured_at`
válido en su puerta de calidad (ver `transform.py`).

`total_count` (suma) es la magnitud principal de este dataset -- a
diferencia de `calidad_aire`/`trafico` (donde promediar tiene más sentido
que sumar lecturas de una magnitud continua), un conteo de peatones/
bicicletas en una hora es, por construcción, un total: la fuente ya publica
como mucho una fila por estación+hora, así que `samples_count` normalmente
vale 1 y `total_count`/`avg_count` coinciden; si algún lote reingesta la
misma estación+hora más de una vez, `total_count` sumaría conteos que en
realidad son la misma medición repetida -- se conserva de todos modos junto
con `avg_count`/`samples_count` para que un consumidor pueda detectar esa
situación (samples_count > 1) en vez de ocultarla.
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


def _sum(values: "list[Optional[float]]") -> Optional[float]:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def aggregate_silver_to_gold(records: "list[dict]", processed_at: datetime) -> "list[dict]":
    """Agrega registros Silver de `aforos_peatones_bicicletas` por estación, modo y hora (Madrid)."""
    buckets: "dict[tuple[str, str, str, int], list[dict]]" = {}

    for record in records:
        measured_at = _parse_iso(record.get("measured_at"))
        station_id = record.get("station_id")
        mode = record.get("mode")
        if measured_at is None or not station_id or not mode:
            continue
        key = (station_id, mode, measured_at.date().isoformat(), measured_at.hour)
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (station_id, mode, date_str, hour), bucket in sorted(buckets.items()):
        measured_ats = sorted(
            m for m in (_parse_iso(r.get("measured_at")) for r in bucket) if m is not None
        )
        location = bucket[0].get("location") or {}
        counts = [r.get("count") for r in bucket]

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "station_id": station_id,
                "mode": mode,
                "district_code": bucket[0].get("district_code"),
                "district": bucket[0].get("district"),
                "address": bucket[0].get("address"),
                "address_notes": bucket[0].get("address_notes"),
                "date": date_str,
                "hour": hour,
                "samples_count": len(bucket),
                "first_measured_at": measured_ats[0].isoformat() if measured_ats else None,
                "last_measured_at": measured_ats[-1].isoformat() if measured_ats else None,
                "total_count": _sum(counts),
                "avg_count": _avg(counts),
                "max_count": max((c for c in counts if c is not None), default=None),
                "min_count": min((c for c in counts if c is not None), default=None),
                "location": {
                    "lat": location.get("lat"),
                    "lon": location.get("lon"),
                    "srid": "EPSG:4326",
                },
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
