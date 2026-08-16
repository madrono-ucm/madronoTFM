"""Transformación Bronze -> Silver del dataset `aparcamientos` (ocupación rotacional).

Lógica en **Python puro** (solo `stdlib`), mismo motivo que
`trafico/transform.py`/`transporte_publico_emt/transform.py`/
`bicimad/transform.py` (ver `procesamiento/README.md`, sección "Por qué
Python puro para la lógica, y PySpark solo en el job de Glue"): así se puede
probar con `unittest` en esta EC2 de desarrollo, sin Spark ni Great
Expectations instalados.

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

Igual que `transporte_publico_emt`/`bicimad`:
`ingesta/capturas/aparcamientos_madrid.py` (`normalize_record`) entrega
directamente `location.lat`/`location.lon` (coordenadas ya en WGS84, tal
como las devuelve el servicio SOAP `GetListParking`), no hace falta ninguna
reproyección.

## Decisión explícita: ocupación no disponible NO se descarta

`ingesta/capturas/aparcamientos_madrid.py` documenta que compartir la
ocupación en tiempo real es **voluntario**: no todos los aparcamientos del
listado (`GetListParking`) incluyen el nodo `lstOccupation` con la plaza
libres/instante de medida, y las plazas totales (`GetDetailParking`, una
llamada SOAP aparte por aparcamiento) pueden no obtenerse si esa segunda
llamada falla. En la práctica esto puede dejar `measured_at`,
`free_spaces` y/o `total_spaces` a `None` de forma independiente entre sí en
un mismo registro Bronze.

**Decisión: estos registros SÍ pasan a Silver, con los campos numéricos a
`null`** -- no se descartan. Razones:

- Un aparcamiento que no comparte su ocupación en un instante dado sigue
  siendo un aparcamiento real que existe y tiene nombre/dirección/ubicación
  -- descartarlo perdería esa información sin necesidad (a diferencia de un
  sensor de tráfico con `has_error=true`, donde el registro entero es
  basura, aquí solo falta un subconjunto de campos). `aggregate.py` calcula
  la ratio de ocupación "cuando ambos estén disponibles" (ver ese módulo)
  precisamente para que estos registros parciales sigan siendo útiles en
  Gold sin inventar un valor.
- Es la única forma de que Silver/Gold reflejen honestamente que la
  cobertura de datos en tiempo real de este dataset es parcial (no todos
  los aparcamientos rotacionales de Madrid comparten su ocupación) --
  descartarlos silenciosamente ocultaría esa cobertura real en vez de
  representarla.

Lo que la puerta de calidad SÍ rechaza es la combinación imposible/corrupta:
`free_spaces`/`total_spaces` negativos, o `free_spaces > total_spaces`
cuando ambos están presentes (dato claramente inconsistente, no ausencia de
dato).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1


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

    Nota: `measured_at`/`free_spaces`/`total_spaces` ausentes (`None`) NO
    son, por sí solos, motivo de rechazo -- ver el docstring del módulo
    ("Decisión explícita: ocupación no disponible NO se descarta").
    """
    reasons: "list[str]" = []

    if not record.get("parking_id"):
        reasons.append("parking_id_missing")

    ingested_at = _parse_iso(record.get("ingested_at"))
    if ingested_at is None:
        reasons.append("ingested_at_missing_or_unparseable")
    elif ingested_at.tzinfo is None:
        reasons.append("ingested_at_not_timezone_aware")

    measured_at_raw = record.get("measured_at")
    if measured_at_raw is not None:
        measured_at = _parse_iso(measured_at_raw)
        if measured_at is None:
            reasons.append("measured_at_unparseable")
        elif measured_at.tzinfo is None:
            reasons.append("measured_at_not_timezone_aware")

    free_spaces = record.get("free_spaces")
    if free_spaces is not None and free_spaces < 0:
        reasons.append("free_spaces_negative")

    total_spaces = record.get("total_spaces")
    if total_spaces is not None and total_spaces < 0:
        reasons.append("total_spaces_negative")

    if free_spaces is not None and total_spaces is not None and free_spaces > total_spaces:
        reasons.append("free_spaces_exceeds_total_spaces")

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
    free_spaces = record.get("free_spaces")
    total_spaces = record.get("total_spaces")

    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "parking_id": record.get("parking_id"),
        "name": record.get("name"),
        "address": record.get("address"),
        "measured_at": record.get("measured_at"),
        "ingested_at": record.get("ingested_at"),
        "processed_at": processed_at.isoformat(),
        "free_spaces": free_spaces,
        "total_spaces": total_spaces,
        # Ratio 0-1 comparable entre aparcamientos de capacidades distintas
        # (mismo criterio que `occupancy_ratio` en `trafico/transform.py`/
        # `bicimad/transform.py`); `None` cuando falta cualquiera de los dos
        # operandos (ver docstring del módulo).
        "occupancy_ratio": _ratio(free_spaces, total_spaces),
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
