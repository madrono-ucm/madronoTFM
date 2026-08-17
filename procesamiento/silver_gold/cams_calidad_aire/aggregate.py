"""Agregación Silver -> Gold del dataset `cams_calidad_aire`: valor medio/
máximo previsto por contaminante y **día que predicen** (`fecha_validez`,
derivada de `valid_datetime`), no por horizonte de antelación
(`leadtime_hour`).

Decisión de agregación fijada por el enunciado de esta tarea (previsión
horaria, "valor medio/máximo previsto ese día para ese contaminante"), no
evaluada aquí. `fecha_validez` responde "¿qué previó el modelo para tal día,
en conjunto, para tal contaminante?" combinando en el mismo bucket todas las
horas de ese día y todos los `leadtime_hour`/corridas (`forecast_issued_at`)
que la hayan predicho -- a diferencia de `aemet_prevision_avisos.aggregate_prevision_silver_to_gold`
(tarea 058), que agrupa por `leadtime_days` (el horizonte) precisamente para
poder comparar "qué tan certera es la previsión a N días vista" entre días de
calendario distintos. Ambas preguntas son legítimas y comparten la misma
naturaleza de dato (previsión con horizonte); esta tarea pide la primera, no
la segunda -- `leadtime_hours` (lista de horizontes distintos presentes en el
bucket) se conserva en cada fila de Gold para no perder esa información,
sin que sea la clave de agrupación.

`fecha_validez` se deriva de `valid_datetime` (no se guarda como columna
aparte en Silver), mismo criterio que el resto del patrón deriva `fecha`/
`hora` de un timestamp en vez de duplicarlo.
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
    """Agrega registros Silver de `cams_calidad_aire` por contaminante y día previsto."""
    buckets: "dict[tuple[str, str], list[dict]]" = {}

    for record in records:
        pollutant = record.get("pollutant")
        valid_datetime = _parse_iso(record.get("valid_datetime"))
        if not pollutant or valid_datetime is None:
            continue
        key = (pollutant, valid_datetime.date().isoformat())
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (pollutant, fecha_validez), bucket in sorted(buckets.items()):
        values = [r.get("value") for r in bucket if r.get("value") is not None]
        leadtime_hours = sorted({r["leadtime_hour"] for r in bucket if r.get("leadtime_hour") is not None})
        forecast_issued_ats = sorted(
            t for t in (_parse_iso(r.get("forecast_issued_at")) for r in bucket) if t is not None
        )

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "pollutant": pollutant,
                "pollutant_code": bucket[0].get("pollutant_code"),
                "unit": bucket[0].get("unit"),
                "fecha_validez": fecha_validez,
                "samples_count": len(bucket),
                "avg_value": _avg(values),
                "max_value": max(values) if values else None,
                "leadtime_hours": leadtime_hours,
                "first_forecast_issued_at": forecast_issued_ats[0].isoformat() if forecast_issued_ats else None,
                "last_forecast_issued_at": forecast_issued_ats[-1].isoformat() if forecast_issued_ats else None,
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
