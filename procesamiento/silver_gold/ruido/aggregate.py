"""Agregación Silver -> Gold del dataset `ruido`: resumen diario por estación y
periodo, más una media móvil de 7 días de LAeq.

## Clave de agregación: `(station_id, period, measured_date)`, no `(id, fecha, hora)`

A diferencia del resto del patrón, esta fuente ya es un agregado **diario**
por estación+periodo (ver `transform.py`): no hay ninguna hora que agregar.
Agrupar por `(station_id, period, measured_date)` (en vez de forzar una
`hora` que la fuente no publica) sirve sobre todo para ser robusto ante
reingestas del mismo día (reintentos de la captura, backfills) -- en el caso
normal (una sola lectura Silver por estación+periodo+día) el `avg`/`max`/
`min` de cada bucket coincide trivialmente con esa única lectura.

## Decisión de la tarea: media móvil de 7 días sobre LAeq

El enunciado pedía decidir con criterio propio qué aporta Gold a esta
granularidad diaria, en vez de forzar una agregación horaria que la fuente
no soporta. Un simple paso a través (un resumen diario del mismo dato, sin
ningún nuevo cálculo) no añadiría valor real de negocio. Se ha optado por
calcular, por cada `(station_id, period)`, una **media móvil de los últimos
7 días naturales** (`laeq_rolling_7d_avg_db`, sobre `avg_laeq_db` de cada
día del bucket) -- una magnitud habitual en paneles de contaminación
acústica para suavizar el ruido día a día (fin de semana vs. laborable,
eventos puntuales) y detectar tendencias, sin depender de que la fuente
tenga huecos (la Red Fija del SIVCA no publica fines de semana ni festivos,
ver `ingesta/capturas/ruido_madrid.py`): la ventana es de calendario (día
actual - 6 días hasta día actual), no "últimas 7 lecturas", así que un hueco
de fin de semana simplemente reduce `laeq_rolling_7d_days` (cuántos días
reales entraron en la ventana), no desplaza la ventana.

Solo se calcula la media móvil sobre LAeq (el indicador principal de
contaminación acústica), no sobre los percentiles L1/L10/L50/L90/L99, para
no multiplicar columnas de una magnitud secundaria sin un caso de uso
concreto.

**Advertencia física, documentada aquí a propósito**: tanto la media diaria
(`avg_laeq_db`, cuando hay más de una lectura Silver el mismo día) como la
media móvil de 7 días calculan una media aritmética simple de valores en
dB. Un promedio energéticamente correcto de niveles LAeq requiere revertir a
presión sonora lineal, promediar y volver a dB (`10*log10(mean(10**(x/10)))`),
no una media aritmética de los propios dB -- igual que `calidad_aire`/
`trafico`/`meteorologia` promedian sus magnitudes con una media aritmética
simple sin esa corrección. Se mantiene el mismo criterio que el resto del
patrón (simplicidad, consistencia) a sabiendas de esta imprecisión: en el
caso normal (una sola lectura Silver por estación+periodo+día) `avg_laeq_db`
coincide exactamente con el valor publicado por la fuente, así que el error
solo aparece en la media móvil de 7 días (que combina varios días
distintos) -- si una tarea futura necesita un promedio acústicamente
correcto, debe sustituir esta media aritmética por la fórmula logarítmica
anterior, tanto aquí como en el job de Glue equivalente.
"""

from __future__ import annotations

from datetime import date, datetime
from statistics import mean
from typing import Optional

SCHEMA_VERSION = 1

ROLLING_WINDOW_DAYS = 7


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _avg(values: "list[Optional[float]]") -> Optional[float]:
    present = [v for v in values if v is not None]
    return mean(present) if present else None


def _daily_buckets(records: "list[dict]") -> "list[dict]":
    """Agrupa Silver por `(station_id, period, measured_date)` en un resumen diario."""
    buckets: "dict[tuple[str, str, str], list[dict]]" = {}

    for record in records:
        station_id = record.get("station_id")
        period = record.get("period")
        measured_date = record.get("measured_date")
        if not station_id or not period or _parse_date(measured_date) is None:
            continue
        key = (station_id, period, measured_date)
        buckets.setdefault(key, []).append(record)

    daily = []
    for (station_id, period, measured_date), bucket in buckets.items():
        location = bucket[0].get("location") or {}
        daily.append(
            {
                "station_id": station_id,
                "period": period,
                "period_name": bucket[0].get("period_name"),
                "measured_date": measured_date,
                "station_name": bucket[0].get("station_name"),
                "district": bucket[0].get("district"),
                "neighbourhood": bucket[0].get("neighbourhood"),
                "samples_count": len(bucket),
                "avg_laeq_db": _avg([r.get("laeq_db") for r in bucket]),
                "max_laeq_db": max((r.get("laeq_db") for r in bucket if r.get("laeq_db") is not None), default=None),
                "min_laeq_db": min((r.get("laeq_db") for r in bucket if r.get("laeq_db") is not None), default=None),
                "avg_l1_db": _avg([r.get("l1_db") for r in bucket]),
                "avg_l10_db": _avg([r.get("l10_db") for r in bucket]),
                "avg_l50_db": _avg([r.get("l50_db") for r in bucket]),
                "avg_l90_db": _avg([r.get("l90_db") for r in bucket]),
                "avg_l99_db": _avg([r.get("l99_db") for r in bucket]),
                "location": {
                    "lat": location.get("lat"),
                    "lon": location.get("lon"),
                    "srid": "EPSG:4326",
                    "altitude_m": location.get("altitude_m"),
                },
            }
        )
    return daily


def aggregate_silver_to_gold(records: "list[dict]", processed_at: datetime) -> "list[dict]":
    """Agrega registros Silver de `ruido` por estación, periodo y día (ver docstring del módulo)."""
    daily = _daily_buckets(records)

    by_group: "dict[tuple[str, str], list[dict]]" = {}
    for entry in daily:
        by_group.setdefault((entry["station_id"], entry["period"]), []).append(entry)

    gold_records = []
    for (station_id, period), group in by_group.items():
        group_sorted = sorted(group, key=lambda e: e["measured_date"])
        dates = [_parse_date(e["measured_date"]) for e in group_sorted]

        for i, entry in enumerate(group_sorted):
            current_date = dates[i]
            window = [
                group_sorted[j]["avg_laeq_db"]
                for j in range(len(group_sorted))
                if group_sorted[j]["avg_laeq_db"] is not None
                and 0 <= (current_date - dates[j]).days < ROLLING_WINDOW_DAYS
            ]

            gold_records.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "station_id": station_id,
                    "station_name": entry["station_name"],
                    "district": entry["district"],
                    "neighbourhood": entry["neighbourhood"],
                    "period": period,
                    "period_name": entry["period_name"],
                    "date": entry["measured_date"],
                    "samples_count": entry["samples_count"],
                    "avg_laeq_db": entry["avg_laeq_db"],
                    "max_laeq_db": entry["max_laeq_db"],
                    "min_laeq_db": entry["min_laeq_db"],
                    "avg_l1_db": entry["avg_l1_db"],
                    "avg_l10_db": entry["avg_l10_db"],
                    "avg_l50_db": entry["avg_l50_db"],
                    "avg_l90_db": entry["avg_l90_db"],
                    "avg_l99_db": entry["avg_l99_db"],
                    "laeq_rolling_7d_avg_db": _avg(window),
                    "laeq_rolling_7d_days": len(window),
                    "location": entry["location"],
                    "processed_at": processed_at.isoformat(),
                }
            )

    return sorted(gold_records, key=lambda r: (r["station_id"], r["period"], r["date"]))
