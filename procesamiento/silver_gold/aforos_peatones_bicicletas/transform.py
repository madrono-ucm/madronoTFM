"""Transformación Bronze -> Silver del dataset `aforos_peatones_bicicletas`
(estaciones permanentes de aforo de Madrid, tecnología Data From Sky).

Lógica en **Python puro** (solo `stdlib`), mismo motivo que el resto de
datasets del patrón (ver `procesamiento/README.md`, sección "Por qué Python
puro para la lógica, y PySpark solo en el job de Glue"): así se puede probar
con `unittest` en esta EC2 de desarrollo, sin Spark ni Great Expectations
instalados.

Cada registro Bronze se procesa en dos pasos independientes:

1. `validate_record(record)`: puerta de calidad -- una lista de motivos de
   rechazo (vacía si el registro es válido). Un registro con algún motivo NO
   debe llegar a Silver.
2. `to_silver_record(record, processed_at)`: solo se llama sobre registros
   que ya pasaron `validate_record`.

Las mismas comprobaciones están descritas como expectations declarativas de
Great Expectations en `ge_suite.py` -- ver `trafico/ge_suite.py` para el
razonamiento completo de por qué existen dos representaciones de la misma
regla.

## Sin `geo.py`: `location` ya viene en WGS84

Igual que `transporte_publico_emt`/`bicimad`/`aparcamientos`/`calidad_aire`/
`meteorologia`/`ruido`: `ingesta/capturas/aforos_peatones_bicicletas_madrid.py`
(`normalize_record`) entrega directamente `location.lat`/`location.lon`,
convertidas a partir del formato "agrupado por puntos" propio del CSV de
origen (p.ej. `"40.417.386"` -> `40.417386`), ya en WGS84 -- no hace falta
ninguna reproyección.

## Dos redes de estaciones, un único campo `count` en Silver

Bronze trae **dos campos de conteo separados** (`pedestrian_count`/
`bicycle_count`), pero cada registro solo rellena uno de los dos según su
`mode` (`"peatones"`/`"bicicletas"`, ver docstring del módulo de ingesta,
"Dos redes de estaciones distintas, no una sola con dos columnas"): peatones
y bicicletas se miden en estaciones físicamente distintas, no son el mismo
punto midiendo dos magnitudes a la vez. Silver colapsa ambos campos en un
único `count` (el que corresponde al `mode` del registro), siguiendo el
mismo criterio que `calidad_aire`/`meteorologia` (un único campo `value`/
`count` cuya interpretación depende de una etiqueta del propio registro --
`pollutant`/`magnitude` allí, `mode` aquí) en vez de conservar dos columnas
donde una siempre es `null`. `mode` es, junto con la estación y la hora,
parte de la clave natural de agregación en `aggregate.py`.

## Puerta de calidad: sin dato = se descarta (a diferencia de `aparcamientos`)

El objetivo de la tarea pide explícitamente "descarta estaciones/horas sin
dato": un registro cuyo campo de conteo correspondiente a su `mode` venga a
`null` (o negativo) se rechaza entero, a diferencia de `aparcamientos`
(donde compartir la ocupación en tiempo real es voluntaria y un `null` es un
estado válido y esperado). Aquí no hay ninguna señal en la fuente de que un
conteo ausente sea un estado legítimo de la estación -- ambos CSV de origen
siempre traen la columna de conteo rellena para las filas reales del último
día publicado (verificado en la muestra de
`ingesta/capturas/samples/aforos_peatones_bicicletas_madrid_sample.json`), así
que un `null`/negativo se trata como dato corrupto o incompleto, no como
cobertura parcial por diseño.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1

MODE_PEDESTRIAN = "peatones"
MODE_BICYCLE = "bicicletas"

# Campo de Bronze que contiene el conteo real para cada `mode` -- el otro
# campo de conteo siempre viene a `null` en ese mismo registro (ver
# docstring del módulo).
COUNT_FIELD_BY_MODE: "dict[str, str]" = {
    MODE_PEDESTRIAN: "pedestrian_count",
    MODE_BICYCLE: "bicycle_count",
}


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

    mode = record.get("mode")
    count_field = COUNT_FIELD_BY_MODE.get(mode)
    if count_field is None:
        reasons.append("mode_missing_or_invalid")

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

    if count_field is not None:
        count = record.get(count_field)
        if count is None:
            reasons.append("count_missing")
        elif count < 0:
            reasons.append("count_negative")

    return reasons


def to_silver_record(record: dict, processed_at: datetime) -> dict:
    """Normaliza un registro Bronze ya validado (`validate_record` == []).

    No vuelve a validar: se asume que el llamador ya filtró los registros
    que no pasan la puerta de calidad (ver `bronze_to_silver` más abajo, o
    el job de Glue).
    """
    location = record.get("location") or {}
    mode = record.get("mode")
    count_field = COUNT_FIELD_BY_MODE.get(mode)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "station_id": record.get("station_id"),
        "mode": mode,
        "count": record.get(count_field) if count_field else None,
        "measured_at": record.get("measured_at"),
        "ingested_at": record.get("ingested_at"),
        "processed_at": processed_at.isoformat(),
        "district_code": record.get("district_code"),
        "district": record.get("district"),
        "address": record.get("address"),
        "address_notes": record.get("address_notes"),
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
