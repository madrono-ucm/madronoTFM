"""Transformación Bronze -> Silver del dataset `bicimad` (estado de estaciones GBFS).

Lógica en **Python puro** (solo `stdlib`), mismo motivo que
`trafico/transform.py`/`transporte_publico_emt/transform.py` (ver
`procesamiento/README.md`, sección "Por qué Python puro para la lógica, y
PySpark solo en el job de Glue"): así se puede probar con `unittest` en esta
EC2 de desarrollo, sin Spark ni Great Expectations instalados.

Cada registro Bronze se procesa en dos pasos independientes:

1. `validate_record(record)`: puerta de calidad -- una lista de motivos de
   rechazo (vacía si el registro es válido). Un registro con algún motivo NO
   debe llegar a Silver.
2. `to_silver_record(record, processed_at)`: solo se llama sobre registros
   que ya pasaron `validate_record`.

Las mismas comprobaciones están descritas como expectations declarativas de
Great Expectations en `ge_suite.py` -- ver ese módulo para la puerta de
calidad "oficial" que ejecuta el job de Glue real.

## Sin `geo.py`: `location` ya viene en WGS84

Igual que `transporte_publico_emt` (tarea 046): el feed GBFS de
`ingesta/capturas/bicimad.py` (`normalize_record`) entrega directamente
`location.lat`/`location.lon` (coordenadas del propio estándar GBFS, WGS84),
no hace falta ninguna reproyección.

## Diferencia frente a `trafico`/`transporte_publico_emt`: consistencia entre contadores

`ingesta/capturas/bicimad.py` une dos feeds GBFS (`station_information`,
metadatos fijos incluida `capacity`; `station_status`, contadores en tiempo
real) por `station_id`. Sus contadores (`bikes_available`, `bikes_disabled`,
`docks_available`, `docks_disabled`) no tienen por qué sumar exactamente
`docks_total` (`capacity`): una bici alquilada en ese instante (fuera de
cualquier estación) no aparece en ningún contador de ninguna estación, así
que la suma real observada en el feed es sistemáticamente **menor o igual**
que la capacidad, nunca mayor -- verificado contra las 5 estaciones reales
de `ingesta/capturas/samples/bicimad_sample.json` (p.ej. estación `1406`:
`1 + 5 = 6 <= 47`, con 41 "huecos" de discrepancia normales por bicis fuera
de la red). Por eso la puerta de calidad usa `<=`, no `==` (el criterio que
sugería el enunciado de la tarea como alternativa a una igualdad exacta que
la fuente real no cumple).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1

# Campos de contador que, cuando están presentes, no pueden ser negativos
# (valores claramente corruptos, no un límite documentado por GBFS).
_COUNTER_FIELDS = (
    "bikes_available",
    "bikes_disabled",
    "docks_available",
    "docks_disabled",
    "docks_total",
)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
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

    measured_at = _parse_iso(record.get("measured_at"))
    if measured_at is None:
        reasons.append("measured_at_missing_or_unparseable")
    elif measured_at.tzinfo is None:
        reasons.append("measured_at_not_timezone_aware")

    ingested_at = _parse_iso(record.get("ingested_at"))
    if ingested_at is None:
        reasons.append("ingested_at_missing_or_unparseable")
    elif ingested_at.tzinfo is None:
        reasons.append("ingested_at_not_timezone_aware")

    # Una estación desinstalada (retirada de la red, en mantenimiento) no
    # tiene contadores fiables -- se descarta en vez de dejar pasar valores
    # sin sentido operativo a Silver.
    if record.get("is_installed") is False:
        reasons.append("station_not_installed")

    for field_name in _COUNTER_FIELDS:
        value = record.get(field_name)
        if value is not None and value < 0:
            reasons.append(f"{field_name}_negative")

    docks_total = record.get("docks_total")
    bikes_available = record.get("bikes_available")
    bikes_disabled = record.get("bikes_disabled")
    docks_available = record.get("docks_available")
    docks_disabled = record.get("docks_disabled")

    # Consistencia laxa (<=, no ==, ver docstring del módulo): la suma real
    # de bicis/anclajes contados en la estación nunca puede superar su
    # capacidad total, aunque sí puede ser menor (bicis fuera de la red).
    if docks_total is not None and bikes_available is not None and bikes_disabled is not None:
        if bikes_available + bikes_disabled > docks_total:
            reasons.append("bikes_exceed_docks_total")

    if docks_total is not None and docks_available is not None and docks_disabled is not None:
        if docks_available + docks_disabled > docks_total:
            reasons.append("docks_exceed_docks_total")

    return reasons


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def to_silver_record(record: dict, processed_at: datetime) -> dict:
    """Normaliza un registro Bronze ya validado (`validate_record` == []).

    No vuelve a validar: se asume que el llamador ya filtró los registros
    que no pasan la puerta de calidad (ver `bronze_to_silver` más abajo, o
    el job de Glue).
    """
    location = record.get("location") or {}
    bikes_available = record.get("bikes_available")
    docks_total = record.get("docks_total")

    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "station_id": record.get("station_id"),
        "name": record.get("name"),
        "address": record.get("address"),
        "measured_at": record.get("measured_at"),
        "ingested_at": record.get("ingested_at"),
        "processed_at": processed_at.isoformat(),
        "bikes_available": bikes_available,
        "bikes_disabled": record.get("bikes_disabled"),
        "docks_available": record.get("docks_available"),
        "docks_disabled": record.get("docks_disabled"),
        "docks_total": docks_total,
        "status": record.get("status"),
        "is_renting": record.get("is_renting"),
        "is_returning": record.get("is_returning"),
        # Ratio 0-1 comparable entre estaciones de capacidades distintas
        # (mismo criterio que `occupancy_ratio` en `trafico/transform.py`):
        # cuántas de las plazas totales de la estación tienen una bici
        # disponible para alquilar ahora mismo.
        "occupancy_ratio": _ratio(bikes_available, docks_total),
        "location": {
            "lat": location.get("lat"),
            "lon": location.get("lon"),
            "srid": location.get("srid"),
        },
    }


def bronze_to_silver(records: "list[dict]", processed_at: datetime) -> "tuple[list[dict], list[dict]]":
    """Aplica la puerta de calidad y transforma los registros que la pasan.

    Devuelve `(silver_records, rejected)`: `rejected` es una lista de
    `{"record": <original>, "reasons": [...]}`, útil para observabilidad --
    el job de Glue solo escribe `silver_records` en el bucket Silver;
    `rejected` se queda en los logs del job, mismo criterio que
    `trafico/transform.py`/`transporte_publico_emt/transform.py`.
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
