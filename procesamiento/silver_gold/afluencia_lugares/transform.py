"""Transformación Bronze -> Silver del dataset `afluencia_lugares`
(afluencia estimada de lugares conocidos de Madrid vía la librería
`populartimes`, ver `ingesta/capturas/afluencia_lugares_madrid.py` y
doc/012).

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

`ingesta/capturas/afluencia_lugares_madrid.py` (`normalize_record`) ya
entrega `location.lat`/`location.lon` en WGS84 (`"srid": "EPSG:4326"`,
resuelto por la propia API "Find Place" de Google) -- no hace falta ninguna
reproyección. Mismo criterio que `agenda_eventos` (tarea 056): `lat`/`lon`
se aplanan a columnas de primer nivel en Silver, sin un sub-struct
`location`.

## Este dataset sigue bloqueado: no hay `GOOGLE_MAPS_API_KEY` real todavía

Ver doc/012: no existe ninguna forma autónoma de dar de alta una cuenta de
Google Cloud en este pipeline, así que tanto la muestra local
(`ingesta/capturas/samples/afluencia_lugares_madrid_sample.json`) como
cualquier dato en Bronze seguirán siendo `"is_mock": true` hasta que se
obtenga esa clave. Esto no impide escribir ni verificar este subpaquete:
igual que hizo la propia tarea 012, la lógica se verifica contra el fixture
mock existente, y el código queda listo para funcionar tal cual el día que
haya clave real. `is_mock` no se propaga a Silver -- dato de procedencia de
la captura, no una dimensión de negocio, mismo criterio que
`aemet_prevision_avisos`/`cams_calidad_aire`.

## `live_pct`/`typical_by_hour`: dos formas de dato, ambas de presencia opcional

A diferencia del resto del patrón, cada registro puede traer dos magnitudes
independientes, cualquiera de las dos (o ambas) legítimamente ausente:

- `live_pct` (afluencia en vivo, 0-100): `None` cuando Google no tiene datos
  suficientes para el lugar en el instante de la captura (ver el registro
  real de muestra "Parque del Retiro") o cuando el registro procede del
  handler Lambda de patrón típico (`capture_typical_patterns`, que fuerza
  `live_pct=None` a propósito, ver docstring de `afluencia_lugares_madrid.py`,
  sección "Handler Lambda"). No es un error: `validate_record` NO descarta
  un registro solo por tener `live_pct` a `null`, tal como pide el
  enunciado.
- `typical_by_hour` (patrón habitual, `dict[día_es, list[24 valores]]`):
  `None` cuando Google no tiene datos suficientes de ningún día para ese
  lugar (mismo caso real de muestra, "Plaza Mayor", con `live_pct` Y
  `typical_by_hour` ambos a `null` -- un lugar real sin datos suficientes en
  Google produciría exactamente este mismo registro).

Cuando cualquiera de las dos está presente, sus valores deben estar en el
rango `0-100` (son porcentajes de afluencia relativa, mismo tipo de
magnitud que `occupancy_pct`/`load_pct` en `trafico`) -- un valor fuera de
ese rango indica un registro corrupto, no un lugar sin datos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1

# Mismas claves de día que `ingesta/capturas/afluencia_lugares_madrid.py`
# (`_DAY_KEY_ES`): lunes primero, en español. `aggregate.py` reutiliza esta
# misma lista para indexar `typical_by_hour` por día de la semana.
WEEKDAY_KEYS_ES = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _out_of_range(value, minimum: float = 0, maximum: float = 100) -> bool:
    return value is not None and not (minimum <= value <= maximum)


def validate_record(record: dict) -> "list[str]":
    """Devuelve los motivos por los que `record` NO debe llegar a Silver.

    Lista vacía == registro válido. Cada motivo es una cadena corta y
    estable (útil como métrica: cuántos registros caen por cada regla).
    """
    reasons: "list[str]" = []

    if not record.get("place_id"):
        reasons.append("place_id_missing")

    if not record.get("name"):
        reasons.append("name_missing")

    captured_at = _parse_iso(record.get("captured_at"))
    if captured_at is None:
        reasons.append("captured_at_missing_or_unparseable")
    elif captured_at.tzinfo is None:
        reasons.append("captured_at_not_timezone_aware")

    # `live_pct=None` es un dato válido (ver docstring del módulo) -- solo
    # se rechaza si está presente pero fuera de rango.
    if _out_of_range(record.get("live_pct")):
        reasons.append("live_pct_out_of_range")

    # `typical_by_hour=None` también es válido; si está presente, cada uno
    # de los 24 valores de cada día debe estar en 0-100.
    typical_by_hour = record.get("typical_by_hour")
    if typical_by_hour:
        all_values = [v for day_values in typical_by_hour.values() for v in (day_values or [])]
        if any(_out_of_range(v) for v in all_values):
            reasons.append("typical_by_hour_value_out_of_range")

    return reasons


def to_silver_record(record: dict, processed_at: datetime) -> dict:
    """Normaliza un registro Bronze ya validado (`validate_record` == []).

    No vuelve a validar: se asume que el llamador ya filtró los registros
    que no pasan la puerta de calidad (ver `bronze_to_silver` más abajo, o
    el job de Glue). Aplana `location.*` a columnas de primer nivel (mismo
    criterio que `agenda_eventos`) y renombra `captured_at` a `ingested_at`,
    mismo nombre de campo que usa el resto del patrón para el instante de
    captura.
    """
    location = record.get("location") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "place_id": record.get("place_id"),
        "name": record.get("name"),
        "query": record.get("query"),
        "address": record.get("address"),
        "lat": location.get("lat"),
        "lon": location.get("lon"),
        "live_pct": record.get("live_pct"),
        "typical_by_hour": record.get("typical_by_hour"),
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
