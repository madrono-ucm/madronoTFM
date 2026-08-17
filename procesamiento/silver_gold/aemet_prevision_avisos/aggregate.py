"""Agregación Silver -> Gold del dataset `aemet_prevision_avisos`: dos
agregaciones independientes, una por cada forma de dato (ver
`transform.py` para el porqué de la separación).

## Previsión: `(municipio_code, leadtime_days)`

`leadtime_days` es el horizonte de la previsión: cuántos días de antelación
tenía, en el momento de la captura, el día que describe (`valid_date -
ingested_at.date()`). Un mismo `leadtime_days` (p.ej. "mañana", `1`) agrupa
previsiones de días de calendario distintos capturadas en momentos
distintos -- exactamente lo que pide el enunciado: "valores medios/máximos
previstos para ese horizonte", es decir, "en general, ¿qué tan certera/qué
pinta tiene la previsión a 1 día vista?", no "qué pasó un día concreto"
(eso ya lo responde Silver fila a fila, con `valid_date` sin agregar).
`leadtime_days` no se guarda como columna aparte en Silver (se deriva aquí,
mismo criterio que `bluesky_menciones`/`cartelera_cines_estrenos` derivan
`hour`/`fecha` de un timestamp en vez de duplicarlo en Silver).

Se agrega `avg`/`max` de `temperature_max_c` y `avg`/`min` de
`temperature_min_c` (el máximo del máximo y el mínimo del mínimo son los
extremos que de verdad importan de cada magnitud, no su opuesto), y
`avg`/`max` de `precipitation_probability_pct` -- exactamente "valores
medios/máximos" tal como pide el enunciado, sobre las mismas dos magnitudes
que ya acota la puerta de calidad de `transform.py`.

## Avisos: `(zone, fecha, level)`

`fecha` es el día de `effective_from` (cuándo empieza a estar vigente el
aviso), no el de `ingested_at` (cuándo se capturó) -- mismo criterio que
`cartelera_cines_estrenos`/`agenda_eventos`/`bluesky_menciones`: la pregunta
que responde esta agregación es "qué avisos estuvieron activos tal día en
tal zona", no "cuándo corrió el barrido". `alerts_count` (número de
`identifier` **distintos** en el bucket) es la magnitud principal --
"conteo de avisos activos" tal como pide el enunciado -- separada de
`samples_count` (filas Silver, incluye reingestas del mismo aviso vigente
capturado varias veces mientras sigue activo) por el mismo motivo que el
resto del patrón separa ambos contadores.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

SCHEMA_VERSION = 1


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Previsión diaria por municipio
# ---------------------------------------------------------------------------


def aggregate_prevision_silver_to_gold(records: "list[dict]", processed_at: datetime) -> "list[dict]":
    """Agrega registros Silver de previsión por municipio y horizonte (`leadtime_days`)."""
    buckets: "dict[tuple[str, int], list[dict]]" = {}

    for record in records:
        municipio_code = record.get("municipio_code")
        valid_date = _parse_date(record.get("valid_date"))
        ingested_at = _parse_iso(record.get("ingested_at"))
        if not municipio_code or valid_date is None or ingested_at is None:
            continue
        leadtime_days = (valid_date - ingested_at.date()).days
        key = (municipio_code, leadtime_days)
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (municipio_code, leadtime_days), bucket in sorted(buckets.items()):
        municipio_name = next((r.get("municipio_name") for r in bucket if r.get("municipio_name")), None)
        temperature_max_values = [r["temperature_max_c"] for r in bucket if r.get("temperature_max_c") is not None]
        temperature_min_values = [r["temperature_min_c"] for r in bucket if r.get("temperature_min_c") is not None]
        precipitation_prob_values = [
            r["precipitation_probability_pct"] for r in bucket if r.get("precipitation_probability_pct") is not None
        ]
        valid_dates = sorted(d for d in (_parse_date(r.get("valid_date")) for r in bucket) if d is not None)

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "municipio_code": municipio_code,
                "municipio_name": municipio_name,
                "leadtime_days": leadtime_days,
                "samples_count": len(bucket),
                "avg_temperature_max_c": (
                    sum(temperature_max_values) / len(temperature_max_values) if temperature_max_values else None
                ),
                "max_temperature_max_c": max(temperature_max_values) if temperature_max_values else None,
                "avg_temperature_min_c": (
                    sum(temperature_min_values) / len(temperature_min_values) if temperature_min_values else None
                ),
                "min_temperature_min_c": min(temperature_min_values) if temperature_min_values else None,
                "avg_precipitation_probability_pct": (
                    sum(precipitation_prob_values) / len(precipitation_prob_values)
                    if precipitation_prob_values
                    else None
                ),
                "max_precipitation_probability_pct": (
                    max(precipitation_prob_values) if precipitation_prob_values else None
                ),
                "first_valid_date": valid_dates[0].isoformat() if valid_dates else None,
                "last_valid_date": valid_dates[-1].isoformat() if valid_dates else None,
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records


# ---------------------------------------------------------------------------
# Avisos de fenómenos meteorológicos adversos (CAP)
# ---------------------------------------------------------------------------


def aggregate_avisos_silver_to_gold(records: "list[dict]", processed_at: datetime) -> "list[dict]":
    """Agrega registros Silver de avisos por zona, día de inicio de vigencia y nivel."""
    buckets: "dict[tuple[str, str, str], list[dict]]" = {}

    for record in records:
        zone = record.get("zone")
        level = record.get("level")
        effective_from = _parse_iso(record.get("effective_from"))
        if not zone or not level or effective_from is None:
            continue
        key = (zone, effective_from.date().isoformat(), level)
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (zone, fecha, level), bucket in sorted(buckets.items()):
        distinct_identifiers = {r.get("identifier") for r in bucket if r.get("identifier")}
        phenomena = sorted({r.get("phenomenon") for r in bucket if r.get("phenomenon")})
        effective_froms = sorted(
            t for t in (_parse_iso(r.get("effective_from")) for r in bucket) if t is not None
        )
        effective_untils = sorted(
            t for t in (_parse_iso(r.get("effective_until")) for r in bucket) if t is not None
        )

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "zone": zone,
                "fecha": fecha,
                "level": level,
                "samples_count": len(bucket),
                "alerts_count": len(distinct_identifiers),
                "phenomena": phenomena,
                "first_effective_from": effective_froms[0].isoformat() if effective_froms else None,
                "last_effective_until": effective_untils[-1].isoformat() if effective_untils else None,
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
