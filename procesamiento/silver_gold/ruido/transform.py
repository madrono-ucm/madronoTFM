"""Transformación Bronze -> Silver del dataset `ruido` (contaminación acústica diaria).

Lógica en **Python puro** (solo `stdlib`), mismo motivo que el resto de
datasets del patrón (ver `procesamiento/README.md`, sección "Por qué Python
puro para la lógica, y PySpark solo en el job de Glue"): así se puede probar
con `unittest` en esta EC2 de desarrollo, sin Spark ni Great Expectations
instalados.

## Diferencia real frente al resto de datasets del patrón: granularidad diaria, no horaria

`ingesta/capturas/ruido_madrid.py` (ver doc/008 y el docstring de ese
módulo) publica valores **diarios** (no horarios/en tiempo real) de la Red
Fija del SIVCA: un registro por estación, periodo horario (`D`iurno,
`E`vespertino, `N`octurno, `T`otal) y día -- LAeq y los percentiles
L1/L10/L50/L90/L99. No existe ningún campo de hora: `measured_date` es una
fecha, no un instante. La puerta de calidad y la agregación de este dataset
reflejan esa granularidad real (estación+periodo+día), no el patrón
`(id, fecha, hora)` que usan `trafico`/`transporte_publico_emt`/`bicimad`/
`aparcamientos`/`calidad_aire`/`meteorologia` -- forzar una agregación
horaria inventaría una hora que la fuente no tiene.

## Sin `geo.py`: `location` ya viene en WGS84

Igual que `transporte_publico_emt`/`bicimad`/`aparcamientos`/`calidad_aire`/
`meteorologia`: `ingesta/capturas/ruido_madrid.py` (`normalize_record`)
entrega directamente `location.lat`/`location.lon`, ya reprojectadas a WGS84
por la propia ingesta (`_parse_grouped_decimal` sobre el catálogo de
estaciones acústicas de datos.madrid.es) -- no hace falta ninguna
reproyección aquí. `location.altitude_m` (mismo campo que `meteorologia`)
también viene ya resuelto.

## Rango plausible de decibelios: un único rango, no una tabla por etiqueta

A diferencia de `calidad_aire`/`meteorologia` (un mismo campo `value`
representa magnitudes de escala distinta según otro campo del registro --
contaminante o magnitud meteorológica), aquí los seis campos numéricos
(`laeq_db`, `l1_db`, `l10_db`, `l50_db`, `l90_db`, `l99_db`) son todos
niveles sonoros en la misma unidad (dB), así que un único rango de
plausibilidad basta: no hace falta ninguna tabla `dict[etiqueta, rango]`.
`PLAUSIBLE_DB_RANGE = (20.0, 120.0)` es una cota laxa (no un límite legal de
ruido, que se define en mapas estratégicos de ruido con umbrales Lden/Ln por
zona, no como un rango instantáneo) pensada solo para atrapar valores
claramente corruptos (silencio absoluto o un nivel de daño auditivo
instantáneo), sin descartar ninguna medición urbana real por ruidosa o
tranquila que sea.

## "Descarta periodos sin dato": `laeq_db` ausente rechaza el registro

El enunciado pide "descarta periodos sin dato". La fuente puede publicar una
fila estación+periodo+día sin lectura (columna `LAeq` vacía en el CSV de
origen, que `ruido_madrid._to_float` ya normaliza a `None`) -- ese registro
no aporta ninguna medición y se rechaza igual que un `value` nulo en
`calidad_aire`/`trafico`. Los percentiles (`l1_db`..`l99_db`) SÍ pueden ser
`None` de forma independiente sin rechazar el registro completo (algunas
estaciones/periodos no publican todos los percentiles) -- solo se valida su
rango cuando están presentes.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

SCHEMA_VERSION = 1

# Cota laxa de plausibilidad para cualquier nivel sonoro en dB de este
# dataset (LAeq y los percentiles L1/L10/L50/L90/L99) -- ver docstring del
# módulo para el razonamiento completo.
PLAUSIBLE_DB_RANGE: "tuple[float, float]" = (20.0, 120.0)

# Campo Bronze/Silver -> motivo de rechazo si está fuera de `PLAUSIBLE_DB_RANGE`.
_DB_FIELDS: "tuple[str, ...]" = ("laeq_db", "l1_db", "l10_db", "l50_db", "l90_db", "l99_db")


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


def validate_record(record: dict) -> "list[str]":
    """Devuelve los motivos por los que `record` NO debe llegar a Silver.

    Lista vacía == registro válido. Cada motivo es una cadena corta y
    estable (útil como métrica: cuántos registros caen por cada regla).
    """
    reasons: "list[str]" = []

    if not record.get("station_id"):
        reasons.append("station_id_missing")

    if not record.get("period"):
        reasons.append("period_missing")

    if _parse_date(record.get("measured_date")) is None:
        reasons.append("measured_date_missing_or_unparseable")

    ingested_at = _parse_iso(record.get("ingested_at"))
    if ingested_at is None:
        reasons.append("ingested_at_missing_or_unparseable")
    elif ingested_at.tzinfo is None:
        reasons.append("ingested_at_not_timezone_aware")

    if record.get("laeq_db") is None:
        reasons.append("laeq_missing")

    min_db, max_db = PLAUSIBLE_DB_RANGE
    for field in _DB_FIELDS:
        value = record.get(field)
        if value is None:
            continue
        if value < min_db or value > max_db:
            reasons.append(f"{field}_out_of_plausible_range")

    return reasons


def to_silver_record(record: dict, processed_at: datetime) -> dict:
    """Normaliza un registro Bronze ya validado (`validate_record` == []).

    No vuelve a validar: se asume que el llamador ya filtró los registros
    que no pasan la puerta de calidad (ver `bronze_to_silver` más abajo, o
    el job de Glue).
    """
    location = record.get("location") or {}

    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "station_id": record.get("station_id"),
        "station_name": record.get("station_name"),
        "station_address": record.get("station_address"),
        "district": record.get("district"),
        "neighbourhood": record.get("neighbourhood"),
        "period": record.get("period"),
        "period_name": record.get("period_name"),
        "measured_date": record.get("measured_date"),
        "ingested_at": record.get("ingested_at"),
        "processed_at": processed_at.isoformat(),
        "laeq_db": record.get("laeq_db"),
        "l1_db": record.get("l1_db"),
        "l10_db": record.get("l10_db"),
        "l50_db": record.get("l50_db"),
        "l90_db": record.get("l90_db"),
        "l99_db": record.get("l99_db"),
        "location": {
            "lat": location.get("lat"),
            "lon": location.get("lon"),
            "srid": location.get("srid"),
            "altitude_m": location.get("altitude_m"),
        },
    }


def bronze_to_silver(records: "list[dict]", processed_at: datetime) -> "tuple[list[dict], list[dict]]":
    """Aplica la puerta de calidad y transforma los registros que la pasan.

    Devuelve `(silver_records, rejected)`: `rejected` es una lista de
    `{"record": <original>, "reasons": [...]}`, útil para observabilidad --
    el job de Glue solo escribe `silver_records` en el bucket Silver;
    `rejected` se queda en los logs del job, mismo criterio que el resto de
    datasets del patrón.
    """
    silver_records = []
    rejected = []
    for record in records:
        reasons = validate_record(record)
        if reasons:
            rejected.append({"record": record, "reasons": reasons})
        else:
            silver_records.append(to_silver_record(record, processed_at))
    return silver_records, rejected
