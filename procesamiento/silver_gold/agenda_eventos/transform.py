"""Transformación Bronze -> Silver del dataset `agenda_eventos` (agenda de
eventos culturales y de ocio de Madrid, dos fuentes combinadas -- ver
`ingesta/capturas/agenda_eventos_madrid.py`).

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

## Sin `geo.py`: ambas fuentes ya entregan WGS84

`ingesta/capturas/agenda_eventos_madrid.py` (`normalize_municipal_event` y
`normalize_esmadrid_event`) ya entrega `location.lat`/`location.lon` en
WGS84 (`"srid": "EPSG:4326"` cuando hay coordenadas) para ambas fuentes --
no hace falta ninguna reproyección. A diferencia del resto de datasets del
patrón, aquí `lat`/`lon` pueden venir a `null` de forma legítima (ninguna
fuente garantiza georreferenciar el 100% de sus eventos): no forma parte de
la puerta de calidad, igual que `district`/`neighborhood` (ver más abajo).

## Dos fuentes, un mismo esquema -- pero con huecos distintos cada una

`source` distingue `"agenda_eventos_madrid_municipal"` (centros
municipales, siempre con `district`/`neighborhood` resueltos desde el propio
catálogo de datos.madrid.es) de `"agenda_turismo_esmadrid"` (Madrid
Destino/esmadrid.com, que **nunca** trae `district`/`neighborhood`: el XML
de origen no publica esa columna, ver `normalize_esmadrid_event`). Ninguna
de las dos es la fuente "correcta"; `validate_record` no exige `district`
para no descartar sistemáticamente el 100% de una de las dos fuentes.

## Diferencia real frente al resto del patrón: no es una serie temporal, es un catálogo de eventos

Igual que `cartelera_cines_estrenos` (tarea 055), cada fila de Silver es un
hecho discreto -- un evento concreto, identificado por `event_id` -- no una
medida numérica repetida en el tiempo. La puerta de calidad no comprueba
ningún rango de plausibilidad de una magnitud: exige que los campos clave
que pide el enunciado de la tarea (título, fecha/hora del evento, `source`)
estén presentes, más `event_id` (clave natural imprescindible para poder
deduplicar reingestas en `aggregate.py`, igual que `showtime_id` en
`cartelera_cines_estrenos`).

## `start_datetime`: formato distinto según la fuente, ninguno con zona horaria

El dato municipal trae un `datetime` completo sin zona horaria explícita
(p.ej. `"2026-08-21T22:00:00"`, ya en hora de Madrid, ver
`_parse_municipal_datetime`); esMadrid solo trae la **fecha** del primer
rango de fechas del evento, sin hora (p.ej. `"2026-11-15"`, ver
`_parse_esmadrid_date` y la "Simplificación deliberada" documentada en el
docstring de ese módulo -- la hora real, cuando existe, queda en
`schedule_text` como texto libre). `validate_record` solo exige que
`start_datetime` sea **parseable** como fecha u hora ISO-8601
(`datetime.fromisoformat`, que acepta ambos formatos: date-only y
date+time), tal como pide el enunciado ("descarta eventos sin fecha de
celebración parseable") -- no exige que tenga hora ni que sea
timezone-aware, a diferencia de `captured_at`/`ingested_at` (ver abajo), que
sí siempre trae offset explícito en ambas fuentes (`now_madrid()` en
`ingesta/capturas/bronze.py`).

## A diferencia de `cartelera_cines_estrenos`: NO se descartan eventos "ya pasados"

Una sesión de cine es un instante puntual futuro por construcción de la
fuente (una cartelera solo lista próximas proyecciones); un evento de esta
agenda, en cambio, puede ser una exposición o actividad de **varios meses**
cuyo `start_datetime` ya quedó atrás en el momento de la captura pero cuyo
`end_datetime` sigue vigente (ver el registro real de muestra "25 años del
Museo de San Isidro...", `start_datetime` 2026-07-21, capturado el
2026-08-15 -- sigue siendo un evento activo y relevante). Comparar
`start_datetime < captured_at` aquí descartaría eventos genuinamente en
curso, así que esta puerta de calidad, a propósito, no reproduce esa regla
de `cartelera_cines_estrenos`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1

SOURCE_MUNICIPAL = "agenda_eventos_madrid_municipal"
SOURCE_ESMADRID = "agenda_turismo_esmadrid"
KNOWN_SOURCES = {SOURCE_MUNICIPAL, SOURCE_ESMADRID}


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

    if record.get("source") not in KNOWN_SOURCES:
        reasons.append("source_missing_or_unknown")

    if not record.get("event_id"):
        reasons.append("event_id_missing")

    if not record.get("title"):
        reasons.append("title_missing")

    if _parse_iso(record.get("start_datetime")) is None:
        reasons.append("start_datetime_missing_or_unparseable")

    captured_at = _parse_iso(record.get("captured_at"))
    if captured_at is None:
        reasons.append("captured_at_missing_or_unparseable")
    elif captured_at.tzinfo is None:
        reasons.append("captured_at_not_timezone_aware")

    return reasons


def to_silver_record(record: dict, processed_at: datetime) -> dict:
    """Normaliza un registro Bronze ya validado (`validate_record` == []).

    No vuelve a validar: se asume que el llamador ya filtró los registros
    que no pasan la puerta de calidad (ver `bronze_to_silver` más abajo, o
    el job de Glue). Aplana `location.*` a columnas de primer nivel (mismo
    criterio que `aforos_peatones_bicicletas`/`ruido`, para que el esquema
    Silver quede plano y sea compatible con Parquet/Athena sin structs
    anidados) y renombra `captured_at` a `ingested_at`, mismo nombre de
    campo que usa el resto del patrón para el instante de captura.
    """
    location = record.get("location") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "event_id": record.get("event_id"),
        "title": record.get("title"),
        "description": record.get("description"),
        "category": record.get("category"),
        "start_datetime": record.get("start_datetime"),
        "end_datetime": record.get("end_datetime"),
        "schedule_text": record.get("schedule_text"),
        "free": record.get("free"),
        "price_info": record.get("price_info"),
        "venue_name": location.get("venue_name"),
        "address": location.get("address"),
        "district": location.get("district"),
        "neighborhood": location.get("neighborhood"),
        "postal_code": location.get("postal_code"),
        "lat": location.get("lat"),
        "lon": location.get("lon"),
        "url": record.get("url"),
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
