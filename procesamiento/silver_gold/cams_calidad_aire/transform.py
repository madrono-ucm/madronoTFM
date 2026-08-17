"""Transformación Bronze -> Silver del dataset `cams_calidad_aire` (previsión
de calidad del aire de Copernicus CAMS para Madrid, ver
`ingesta/capturas/cams_calidad_aire_madrid.py`, `doc/019-...md` y
`doc/045-arreglo-parseo-fecha-cams.md`).

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

## Sin `geo.py`: `latitude`/`longitude` ya vienen en WGS84

`ingesta/capturas/cams_calidad_aire_madrid.py` (`normalize_forecast_file`)
ya entrega el punto de rejilla más cercano a Madrid en WGS84 (tras corregir
la convención `[0, 360)` de longitud del NetCDF real a `[-180, 180)`, ver su
docstring) -- no hace falta ninguna reproyección.

## Es una previsión con horizonte, no una medida del instante actual

A diferencia de `calidad_aire` (tarea 049, mediciones en tiempo real de la
red de estaciones de Madrid), cada registro de este dataset es un valor
*previsto* para un instante futuro (`valid_datetime`), calculado a partir de
una corrida de modelo concreta (`forecast_issued_at`, la hora "00:00" de la
corrida diaria) con un horizonte de antelación (`leadtime_hour`, horas desde
`forecast_issued_at` hasta `valid_datetime`). Es la misma naturaleza de dato
que `aemet_prevision_avisos` (tarea 058, previsión diaria por municipio) --
aquí con dos diferencias: horizonte en horas, no en días, y sin ningún
"ya pasado" que rechazar (el productor solo pide `leadtime_hour >= 0` desde
la propia corrida, así que `valid_datetime` nunca es anterior a
`forecast_issued_at` por construcción de la petición a la API; no hace falta
repetir aquí una regla que la fuente ya garantiza).

## Puerta de calidad: campos clave no nulos + rango plausible por contaminante

Igual que pide el enunciado: `pollutant` (y su código `pollutant_code`,
también exigido -- es la clave estable para casar con
`PLAUSIBLE_MAX_BY_POLLUTANT`, ver abajo), `valid_datetime`/`leadtime_hour`/
`forecast_issued_at` (los tres describen "qué instante predice esta fila y
con cuánta antelación se predijo" -- ninguno es opcional) y `value`, todos
timezone-aware cuando son timestamps (mismo criterio que el resto del
patrón). `leadtime_hour` se exige además no negativo -- un horizonte
negativo indicaría un error de parseo de `forecast_issued_at`/
`valid_datetime`, no una previsión real.

## Rango plausible por contaminante: mismo criterio que `calidad_aire` (tarea 049)

`PLAUSIBLE_MAX_BY_POLLUTANT` reutiliza el mismo criterio y los mismos
órdenes de magnitud que `calidad_aire.PLAUSIBLE_MAX_BY_POLLUTANT` (cota laxa
pensada solo para atrapar valores corruptos, no un límite legal de calidad
del aire) -- pero está definida aquí como su propia tabla, con las claves
reales que usa `cams_calidad_aire_madrid.POLLUTANT_LABELS`
(`NO2`/`NO`/`SO2`/`O3`/`PM2.5`/`PM10`/`polvo`), un subconjunto distinto del
de `calidad_aire` (esta fuente nunca produce `CO`/`NOx`/`TOL`/etc., y sí
produce `"polvo"`, una etiqueta que `calidad_aire` no tiene). No se importa
la tabla de `calidad_aire` para no acoplar dos subpaquetes independientes
del patrón por un detalle de implementación que podría divergir con el
tiempo (contaminantes validados por CAMS y por la red municipal no tienen
por qué evolucionar igual).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1

# Cota superior laxa de plausibilidad por contaminante (etiqueta ->
# máximo, en la unidad real de ese contaminante, µg/m3 -- ver `unit` en el
# propio registro). El mínimo es 0 para todos (una concentración no puede
# ser negativa). Ver docstring del módulo para el porqué de esta tabla en
# vez de reutilizar `calidad_aire.PLAUSIBLE_MAX_BY_POLLUTANT`.
PLAUSIBLE_MAX_BY_POLLUTANT: "dict[str, float]" = {
    "NO2": 500,  # µg/m3 -- umbral de alerta legal UE: 400
    "NO": 1000,  # µg/m3
    "SO2": 500,  # µg/m3 -- umbral de alerta legal UE: 500
    "O3": 500,  # µg/m3 -- umbral de alerta legal UE: 240
    "PM2.5": 1000,  # µg/m3
    "PM10": 1000,  # µg/m3
    "polvo": 1000,  # µg/m3 -- mismo orden de magnitud que PM10/PM2.5
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

    pollutant = record.get("pollutant")
    if not pollutant:
        reasons.append("pollutant_missing")

    if not record.get("pollutant_code"):
        reasons.append("pollutant_code_missing")

    valid_datetime = _parse_iso(record.get("valid_datetime"))
    if valid_datetime is None:
        reasons.append("valid_datetime_missing_or_unparseable")
    elif valid_datetime.tzinfo is None:
        reasons.append("valid_datetime_not_timezone_aware")

    forecast_issued_at = _parse_iso(record.get("forecast_issued_at"))
    if forecast_issued_at is None:
        reasons.append("forecast_issued_at_missing_or_unparseable")
    elif forecast_issued_at.tzinfo is None:
        reasons.append("forecast_issued_at_not_timezone_aware")

    leadtime_hour = record.get("leadtime_hour")
    if leadtime_hour is None:
        reasons.append("leadtime_hour_missing")
    elif leadtime_hour < 0:
        reasons.append("leadtime_hour_negative")

    ingested_at = _parse_iso(record.get("captured_at"))
    if ingested_at is None:
        reasons.append("ingested_at_missing_or_unparseable")
    elif ingested_at.tzinfo is None:
        reasons.append("ingested_at_not_timezone_aware")

    value = record.get("value")
    if value is None:
        reasons.append("value_missing")
    else:
        if value < 0:
            reasons.append("value_negative")
        max_plausible = PLAUSIBLE_MAX_BY_POLLUTANT.get(pollutant) if pollutant else None
        if max_plausible is not None and value > max_plausible:
            reasons.append("value_out_of_plausible_range")

    return reasons


def to_silver_record(record: dict, processed_at: datetime) -> dict:
    """Normaliza un registro Bronze ya validado (`validate_record` == []).

    No vuelve a validar: se asume que el llamador ya filtró los registros
    que no pasan la puerta de calidad (ver `bronze_to_silver` más abajo, o
    el job de Glue). Renombra `captured_at` a `ingested_at` (mismo nombre de
    campo que usa el resto del patrón) y no propaga `is_mock` (dato de
    procedencia de la captura, no una dimensión de negocio -- mismo criterio
    que `aemet_prevision_avisos`, que tampoco lo propaga a Silver).
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "pollutant": record.get("pollutant"),
        "pollutant_code": record.get("pollutant_code"),
        "value": record.get("value"),
        "unit": record.get("unit"),
        "valid_datetime": record.get("valid_datetime"),
        "forecast_issued_at": record.get("forecast_issued_at"),
        "leadtime_hour": record.get("leadtime_hour"),
        "model": record.get("model"),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "ingested_at": record.get("captured_at"),
        "processed_at": processed_at.isoformat(),
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
