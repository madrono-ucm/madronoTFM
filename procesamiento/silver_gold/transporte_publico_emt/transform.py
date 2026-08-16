"""Transformación Bronze -> Silver del dataset `transporte_publico_emt` (llegadas EMT Madrid).

Lógica en **Python puro** (solo `stdlib`), mismo motivo que
`procesamiento/silver_gold/trafico/transform.py` (ver
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

## Diferencia relevante frente a `trafico`: no existe `measured_at`

El esquema de este productor (`ingesta/capturas/transporte_publico_madrid.py`,
`normalize_record`) no tiene ningún campo `measured_at`: la API MobilityLabs
de la EMT es un servicio de tiempo real que, en cada llamada, devuelve la
estimación *vigente en ese instante* de cuánto falta para que un autobús
llegue a la parada (`estimate_arrive_sec`, segundos). No hay una "hora de
medida" distinta de la hora de captura -- `ingested_at` **es** el instante de
medida (el momento en que se observó esa estimación), así que aquí hace de
equivalente exacto del `measured_at` de tráfico. No se ha renombrado el campo
(sigue llamándose `ingested_at`, igual que en Bronze) para no introducir un
alias que no aporta nada y que divergería del nombre real del esquema fuente.

## Diferencia relevante: `location` es la posición del autobús, no de la parada

A diferencia de tráfico (`location` = coordenadas fijas del sensor), aquí
`location` es la posición GPS del autobús en el instante de la estimación --
cambia en cada llegada y en cada captura. Se conserva en Silver por
trazabilidad, pero no se usa como "ubicación representativa" en la puerta de
calidad (una parada no tiene una única ubicación de autobús) ni se agrega en
Gold (ver `aggregate.py`): agregarla no tendría el mismo significado que en
tráfico, donde location es constante por punto de medida.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1

# Rango de plausibilidad del tiempo de espera estimado, en segundos. No es un
# límite oficial documentado por la EMT (la API no publica ningún máximo), es
# una cota laxa para atrapar valores claramente corruptos (negativos,
# estimaciones absurdamente largas) sin descartar esperas reales largas en
# líneas de baja frecuencia. 120 minutos = 7200 segundos.
MIN_PLAUSIBLE_WAIT_SEC = 0
MAX_PLAUSIBLE_WAIT_SEC = 120 * 60

# Claves que solo aparecen en la respuesta de login/error de la API
# MobilityLabs (`accessToken`, `code`/`description` del cuerpo de la
# respuesta, ver `ingesta/capturas/transporte_publico_madrid.py`,
# `fetch_access_token`/`fetch_raw_arrivals`). Un registro Bronze normalizado
# nunca debería tener ninguna de estas claves -- si aparece, es señal de que
# un payload de autenticación/error se coló en Bronze en vez de una llegada
# real normalizada (p.ej. un bug futuro en `normalize_record`/`parse_records`
# que dejara pasar el cuerpo crudo de la API sin parsear), y se descarta en
# vez de tratarlo como una llegada válida.
_AUTH_OR_ERROR_PAYLOAD_KEYS = ("accessToken", "code", "description")


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

    if any(key in record for key in _AUTH_OR_ERROR_PAYLOAD_KEYS):
        reasons.append("unexpected_auth_error_payload")

    if not record.get("stop_id"):
        reasons.append("stop_id_missing")

    if not record.get("line"):
        reasons.append("line_missing")

    ingested_at = _parse_iso(record.get("ingested_at"))
    if ingested_at is None:
        reasons.append("ingested_at_missing_or_unparseable")
    elif ingested_at.tzinfo is None:
        reasons.append("ingested_at_not_timezone_aware")

    estimate_arrive_sec = record.get("estimate_arrive_sec")
    if estimate_arrive_sec is not None and not (
        MIN_PLAUSIBLE_WAIT_SEC <= estimate_arrive_sec <= MAX_PLAUSIBLE_WAIT_SEC
    ):
        reasons.append("estimate_arrive_sec_out_of_range")

    distance_bus_m = record.get("distance_bus_m")
    if distance_bus_m is not None and distance_bus_m < 0:
        reasons.append("distance_bus_m_negative")

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
        "stop_id": record.get("stop_id"),
        "line": record.get("line"),
        "bus_id": record.get("bus_id"),
        "destination": record.get("destination"),
        "ingested_at": record.get("ingested_at"),
        "processed_at": processed_at.isoformat(),
        "estimate_arrive_sec": record.get("estimate_arrive_sec"),
        "distance_bus_m": record.get("distance_bus_m"),
        "is_head": record.get("is_head"),
        "deviation_sec": record.get("deviation_sec"),
        "position_type_bus": record.get("position_type_bus"),
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
    `trafico/transform.py`.
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
