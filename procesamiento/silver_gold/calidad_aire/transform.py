"""Transformación Bronze -> Silver del dataset `calidad_aire` (red de estaciones de Madrid).

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

Igual que `transporte_publico_emt`/`bicimad`/`aparcamientos`:
`ingesta/capturas/calidad_aire_madrid.py` (`normalize_record`) entrega
directamente `location.lat`/`location.lon`, tomadas del CSV de metadatos de
estaciones (`212629-0-estaciones-control-aire`), ya en WGS84 -- no hace
falta ninguna reproyección.

## Lecturas no válidas (`V01`..`V24` == `"N"`): ya filtradas en `ingesta/`

El enunciado de esta tarea pedía confirmar si la fuente ya excluye las
lecturas horarias marcadas como no válidas (código `"N"` en las columnas
`V01`..`V24` del JSON crudo de tiempo real) antes de llegar a Bronze.
Se confirma que sí: `calidad_aire_madrid.normalize_record` usa
`_latest_valid_hour`, que solo considera horas con `V{hour:02d} == "V"` y
devuelve `None` (registro completamente descartado, ni siquiera llega a
Bronze) si el registro estación+magnitud+día no tiene ninguna lectura válida
ese día. Por eso el esquema Bronze de este dataset no contiene ningún campo
`V01`..`V24` -- solo el `value` de la última lectura válida -- y
`validate_record` (abajo) no necesita, ni podría, repetir ese filtro: ya
está resuelto aguas arriba.

## Rango plausible por contaminante

A diferencia de tráfico (magnitudes homogéneas: intensidad, ocupación...),
cada lectura de este dataset está etiquetada con un contaminante
(`magnitude_abbr`, p.ej. `"NO2"`, `"PM10"`, `"O3"`) con su propia unidad y
escala típica -- un rango de plausibilidad único para todos no distinguiría
un NO2 corrupto de un CO válido. `PLAUSIBLE_RANGES` da un rango laxo
(no un límite legal/oficial de calidad del aire, que son medias en ventanas
de tiempo largas -- 1h/8h/24h/anual, no un tope instantáneo) por cada
contaminante del Anexo II del PDF "Intérprete de ficheros de calidad del
aire" que puede devolver el feed en tiempo real (mismo conjunto que
`MAGNITUDES` en `ingesta/capturas/calidad_aire_madrid.py`), pensado solo
para atrapar valores claramente corruptos (negativos, o varios órdenes de
magnitud por encima de cualquier episodio de contaminación real observado
en Madrid) sin descartar picos de contaminación real. Un `magnitude_abbr`
que no aparezca en la tabla (no debería ocurrir, ver `MAGNITUDES` en
`ingesta/`) no se rechaza por rango -- solo se exige que no sea negativo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1

# Cota superior laxa de plausibilidad por contaminante (abreviatura ->
# máximo, en la unidad real de ese contaminante -- ver `unit` en el propio
# registro / `MAGNITUDES` en `ingesta/capturas/calidad_aire_madrid.py`). El
# mínimo es 0 para todos (una concentración no puede ser negativa).
PLAUSIBLE_MAX_BY_POLLUTANT: "dict[str, float]" = {
    "SO2": 500,  # µg/m3 -- umbral de alerta legal UE: 500
    "CO": 50,  # mg/m3 -- límite legal UE (8h): 10; cota laxa x5
    "NO": 1000,  # µg/m3
    "NO2": 500,  # µg/m3 -- umbral de alerta legal UE: 400
    "PM2.5": 1000,  # µg/m3
    "PM10": 1000,  # µg/m3
    "NOx": 1000,  # µg/m3
    "O3": 500,  # µg/m3 -- umbral de alerta legal UE: 240
    "TOL": 1000,  # µg/m3
    "BEN": 100,  # µg/m3
    "EBE": 1000,  # µg/m3
    "MXY": 1000,  # µg/m3
    "PXY": 1000,  # µg/m3
    "OXY": 1000,  # µg/m3
    "TCH": 50,  # mg/m3
    "CH4": 50,  # mg/m3
    "NMHC": 50,  # mg/m3
    "MPX": 50,  # mg/m3 (dato real es "mg/m3" en `MAGNITUDES`, código "431")
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

    pollutant = record.get("magnitude_abbr")
    if not pollutant:
        reasons.append("pollutant_missing")

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
    el job de Glue).
    """
    location = record.get("location") or {}

    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "station_id": record.get("station_id"),
        "station_name": record.get("station_name"),
        "station_address": record.get("station_address"),
        "magnitude_code": record.get("magnitude_code"),
        "pollutant": record.get("magnitude_abbr"),
        "pollutant_name": record.get("magnitude_name"),
        "unit": record.get("unit"),
        "value": record.get("value"),
        "measured_at": record.get("measured_at"),
        "ingested_at": record.get("ingested_at"),
        "processed_at": processed_at.isoformat(),
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
