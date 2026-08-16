"""Transformación Bronze -> Silver del dataset `cartelera_cines_estrenos`
(cartelera y horarios de cines de Madrid, vía SensaCine, ver
`ingesta/capturas/cartelera_cines_madrid.py`).

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

## Sin `geo.py`: no hay ninguna coordenada en este dataset

A diferencia de todos los datasets anteriores del patrón, el esquema de
`cartelera_cines_madrid.py` no incluye ninguna posición geográfica (ni de
cine ni de sesión) -- no hace falta ningún `geo.py` ni columna `location`.

## Bronze mezcla dos tipos de registro; este dataset solo procesa sesiones

`ingesta/capturas/cartelera_cines_madrid.py` normaliza dos formas de
registro distintas bajo el mismo `DATASET_NAME`
(`"cartelera_cines_estrenos"`, ver ese módulo): **sesiones** de cine
concretas (`normalize_showtime`: película + cine + horario + identificador
de sesión, sin campo `record_type`) y **estrenos semanales**
(`normalize_premiere`: `record_type == "estreno_semana"`, película + fecha
de estreno + duración + géneros, sin cine ni horario -- una lista nacional
de estrenos, no desglosada por cine ni por sesión, ver el docstring de ese
módulo).

El enunciado de esta tarea pide explícitamente que la puerta de calidad
exija como campos clave "título de la película, cine, horario de sesión" --
eso solo tiene sentido para el primer tipo de registro. `validate_record`
rechaza cualquier registro de estreno semanal con el motivo
`"not_a_screening_session"` en vez de intentar encajarlo en el mismo
esquema (no tiene cine ni horario que perder, y agregarlo como si fuera una
sesión produciría una fila de Gold sin sentido). Los estrenos semanales
quedan fuera del alcance de este subpaquete -- si una tarea futura quiere
tratarlos como su propia entidad (p.ej. "estrenos de la semana", sin cine ni
horario), el criterio a seguir es un dataset/tabla Silver/Gold aparte, no
forzarlos en este esquema de sesiones.

**Aviso importante para tareas futuras, descubierto en esta sesión**: el
único escritor programado de Bronze de este dataset hoy es `lambda_handler`
(`ingesta/capturas/cartelera_cines_madrid.py`), y envuelve **únicamente
`sweep_premieres`** -- no hay ningún schedule que escriba sesiones
(`fetch_cinema_showtimes` es solo bajo demanda, pensado para un futuro
servicio conversacional, sin ningún handler Lambda propio, ver el docstring
de ese módulo, apartado "Handler Lambda"). Confirmado en
`doc/033-conectar-lambda-layer-verificar.md`: la única invocación real
registrada de este dataset escribió 6 registros, los 6 de tipo
`estreno_semana`. Esto significa que, con el estado actual de `ingesta/`,
esta puerta de calidad rechazaría el 100% de los lotes reales de Bronze
capturados hasta ahora -- no hay todavía ningún escritor programado que
produzca sesiones. No se ha corregido aquí (fuera de alcance: esta tarea es
solo `procesamiento/`); queda documentado como bloqueante real para poder
ejecutar este pipeline contra datos de producción: haría falta una tarea
futura que añada un escritor programado de sesiones (p.ej. un
`lambda_handler` adicional que recorra `CINEMAS`, o ampliar el existente).

## Puerta de calidad: horario de sesión ya pasado respecto a la captura

El enunciado pide "descarta ... con fechas de sesión ya pasadas respecto a
`ingested_at`, si el dato lo permitiera" -- el dato sí lo permite: cada
sesión trae `showtime_datetime` (hora de la proyección) y `captured_at`
(instante en que SensaCine se consultó, ver `normalize_showtime`). Un
registro cuya sesión ya ha empezado en el momento de la captura
(`showtime_datetime < captured_at`) se rechaza con el motivo
`"showtime_already_passed"`: una cartelera es, por construcción, una lista
de sesiones *futuras* respecto al momento en que se consulta -- una sesión
ya iniciada no es información útil para nadie que consulte la cartelera
para decidir qué ver.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1

PREMIERE_RECORD_TYPE = "estreno_semana"


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

    if record.get("record_type") == PREMIERE_RECORD_TYPE:
        reasons.append("not_a_screening_session")

    if not record.get("movie_title"):
        reasons.append("movie_title_missing")

    if not record.get("cinema_id"):
        reasons.append("cinema_id_missing")

    if not record.get("showtime_id"):
        reasons.append("showtime_id_missing")

    showtime_datetime = _parse_iso(record.get("showtime_datetime"))
    if showtime_datetime is None:
        reasons.append("showtime_datetime_missing_or_unparseable")
    elif showtime_datetime.tzinfo is None:
        reasons.append("showtime_datetime_not_timezone_aware")

    captured_at = _parse_iso(record.get("captured_at"))
    if captured_at is None:
        reasons.append("captured_at_missing_or_unparseable")
    elif captured_at.tzinfo is None:
        reasons.append("captured_at_not_timezone_aware")

    if (
        showtime_datetime is not None
        and showtime_datetime.tzinfo is not None
        and captured_at is not None
        and captured_at.tzinfo is not None
        and showtime_datetime < captured_at
    ):
        reasons.append("showtime_already_passed")

    return reasons


def to_silver_record(record: dict, processed_at: datetime) -> dict:
    """Normaliza un registro Bronze ya validado (`validate_record` == []).

    No vuelve a validar: se asume que el llamador ya filtró los registros
    que no pasan la puerta de calidad (ver `bronze_to_silver` más abajo, o
    el job de Glue). Renombra `captured_at` (nombre propio de este
    productor, ver docstring del módulo) a `ingested_at`, mismo nombre de
    campo que usa el resto del patrón para el instante de captura.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "cinema_id": record.get("cinema_id"),
        "chain": record.get("chain"),
        "cinema_name": record.get("cinema_name"),
        "address": record.get("address"),
        "postal_code": record.get("postal_code"),
        "locality": record.get("locality"),
        "screen_count": record.get("screen_count"),
        "movie_title": record.get("movie_title"),
        "movie_url": record.get("movie_url"),
        "language_version": record.get("language_version"),
        "experiences": record.get("experiences") or [],
        "showtime_datetime": record.get("showtime_datetime"),
        "showtime_id": record.get("showtime_id"),
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
