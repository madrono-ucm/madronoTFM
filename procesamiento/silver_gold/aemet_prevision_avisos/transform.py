"""Transformación Bronze -> Silver del dataset `aemet_prevision_avisos`
(previsión diaria y avisos meteorológicos de AEMET OpenData, ver
`ingesta/capturas/aemet_prevision_avisos.py`).

Lógica en **Python puro** (solo `stdlib`), mismo motivo que el resto de
datasets del patrón (ver `procesamiento/README.md`, sección "Por qué Python
puro para la lógica, y PySpark solo en el job de Glue"): así se puede probar
con `unittest` en esta EC2 de desarrollo, sin Spark ni Great Expectations
instalados.

## Dos formas de dato, tratadas por separado desde el principio

A diferencia del resto del patrón (una fila Bronze == una medida u hecho de
un único tipo), `aemet_prevision_avisos.py` produce **dos** Bronze datasets
completamente distintos bajo un mismo productor:

- `aemet_prevision` (`SOURCE_PREDICCION = "aemet_prediccion_municipio"`):
  varios días de **previsión futura** por municipio (hasta 7, uno por fila),
  reemitidos en cada captura -- no es una medida del instante actual.
- `aemet_avisos` (`SOURCE_AVISOS = "aemet_avisos_cap"`): avisos oficiales
  vigentes (amarillo/naranja/rojo) para un área, cero o más por captura.

Ambos esquemas no comparten ni un solo campo de negocio (ni siquiera el
nombre de la dimensión geográfica: `municipio_code` frente a `zone`), así
que este módulo expone dos puertas de calidad y dos normalizadores
independientes (`validate_prevision_record`/`to_silver_prevision_record` y
`validate_aviso_record`/`to_silver_aviso_record`), cada uno con su propia
`bronze_to_silver_*`. No se fuerza ningún esquema Silver único: forzarlo
habría exigido o bien columnas siempre nulas para la mitad de las filas, o
bien perder campos propios de cada tipo -- ver enunciado de esta tarea,
"no fuerces un único esquema de agregación para ambas".

## Prefijos S3 reales de Bronze: `aemet_prevision`/`aemet_avisos`, no `aemet_prevision_avisos`

`ingesta/capturas/aemet_prevision_avisos.py` ya fija los nombres de dataset
Bronze (`DATASET_PREDICCION = "aemet_prevision"`, `DATASET_AVISOS =
"aemet_avisos"`, usados tal cual por `BronzeWriter`/`lambda_handler`) --
son dos prefijos S3 reales y distintos (`bronze/aemet_prevision/*`,
`bronze/aemet_avisos/*`), no uno combinado. Este subpaquete de
`procesamiento/` se llama `aemet_prevision_avisos` porque agrupa el código
de ambos (mismo productor, mismo enunciado de tarea), pero Silver/Gold
mantienen la misma separación de prefijos que Bronze ya tiene fijada en
producción (ver `infra/terraform/glue.tf` para el porqué esto es una
desviación deliberada del prefijo único que sugería el enunciado de esta
tarea).

## Previsión: rangos plausibles y "fecha de validez futura"

`validate_prevision_record` exige, tal como pide el enunciado: campos clave
no nulos (`municipio_code`, `valid_date`), fecha de validez no ya pasada
respecto a `ingested_at` (`captured_at` renombrado, ver `to_silver_*`), y
rangos plausibles de temperatura/probabilidad de precipitación:

- `temperature_max_c`/`temperature_min_c`: `[-20, 50]` -- mismo rango y
  misma justificación que `meteorologia.PLAUSIBLE_RANGE_BY_MAGNITUDE["temperature_c"]`
  (extremos históricos de Madrid-Retiro: -10.1°C / 42.7°C, con margen
  amplio en ambos extremos).
- `precipitation_probability_pct`: `[0, 100]` -- rango físico exacto de una
  probabilidad porcentual.

"Fecha de validez futura respecto a `ingested_at`" se interpreta, igual que
`cartelera_cines_estrenos` con `showtime_already_passed`, como "el día
previsto no ha quedado ya atrás en el momento de la captura": se rechaza
solo si `valid_date < ingested_at.date()`, no si son el mismo día -- la
previsión "de hoy" (`leadtime_days == 0`) es un dato legítimo y frecuente
(la propia fuente la sigue publicando durante todo el día), a diferencia de
un día que ya ha pasado por completo.

`sky_state`/`sky_state_code`/`wind_direction`/`humidity_*`/`uv_max`/
`wind_speed_kmh`/`wind_gust_max_kmh`/`thermal_sensation_*` no forman parte
de la puerta de calidad (no los pide el enunciado como campos clave ni
tienen un rango de plausibilidad definido aquí) -- un valor ausente en
cualquiera de ellos no descarta el registro, tal como ya documenta
`ingesta/README.md` para `wind_gust_max_kmh` (`None` en días sin racha
máxima para el periodo `"00-24"`, caso normal incluso con datos reales).

## Tipos numéricos: Silver normaliza a `float`, Bronze no

`ingesta/README.md` documenta a propósito que Bronze conserva los tipos tal
como los publica AEMET (`precipitation_probability_pct`/`wind_speed_kmh`/
`wind_gust_max_kmh` llegan como *string*, p.ej. `"75"`, mientras que
`temperature_max_c`/`humidity_max_pct`/`uv_max` llegan como número) --
"honestidad sobre cómo lo publica la fuente". Silver, en cambio, sigue el
mismo criterio que el resto del patrón (`meteorologia`/`calidad_aire`:
`value: float`): normaliza todos los campos numéricos a `float` vía
`_to_float` (acepta tanto `str` como `int`/`float`, `None` si no es
parseable), para que `aggregate.py` -- y cualquier consumidor de Gold --
no tenga que adivinar el tipo campo a campo ni volver a parsear un `str`
para poder promediar/comparar.

## Avisos: nivel dentro del catálogo cerrado de AEMET

`validate_aviso_record` exige campos clave no nulos (`identifier` -- clave
natural para poder deduplicar reingestas en `aggregate.py`, `zone`,
`phenomenon`, `effective_from` parseable -- necesario para poder agrupar
por día en `aggregate.py`) y `level` dentro del catálogo cerrado de AEMET
(`VALID_LEVELS = {"amarillo", "naranja", "rojo"}`, ver la página de ayuda
oficial de AEMET citada en `ingesta/capturas/aemet_prevision_avisos.py`).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Union

SCHEMA_VERSION = 1

VALID_LEVELS = {"amarillo", "naranja", "rojo"}

TEMPERATURE_MIN_C = -20.0
TEMPERATURE_MAX_C = 50.0
PRECIPITATION_PROBABILITY_MIN_PCT = 0.0
PRECIPITATION_PROBABILITY_MAX_PCT = 100.0


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Parsea una fecha `YYYY-MM-DD` (p.ej. `valid_date`), sin componente de hora."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _to_float(value: "Union[str, int, float, None]") -> Optional[float]:
    """Convierte a `float` un valor numérico que puede llegar como `str` (ver docstring del módulo).

    Devuelve `None` si `value` es `None`, cadena vacía o no representa un
    número -- nunca lanza.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Previsión diaria por municipio
# ---------------------------------------------------------------------------


def validate_prevision_record(record: dict) -> "list[str]":
    """Devuelve los motivos por los que un registro de previsión NO debe llegar a Silver.

    Lista vacía == registro válido. Ver docstring del módulo para el
    razonamiento de cada regla.
    """
    reasons: "list[str]" = []

    if not record.get("municipio_code"):
        reasons.append("municipio_code_missing")

    valid_date = _parse_date(record.get("valid_date"))
    if valid_date is None:
        reasons.append("valid_date_missing_or_unparseable")

    ingested_at = _parse_iso(record.get("captured_at"))
    if ingested_at is None:
        reasons.append("ingested_at_missing_or_unparseable")
    elif ingested_at.tzinfo is None:
        reasons.append("ingested_at_not_timezone_aware")

    if valid_date is not None and ingested_at is not None and ingested_at.tzinfo is not None:
        if valid_date < ingested_at.date():
            reasons.append("valid_date_already_passed")

    temperature_max_c = _to_float(record.get("temperature_max_c"))
    if temperature_max_c is None or not (TEMPERATURE_MIN_C <= temperature_max_c <= TEMPERATURE_MAX_C):
        reasons.append("temperature_max_c_missing_or_out_of_range")

    temperature_min_c = _to_float(record.get("temperature_min_c"))
    if temperature_min_c is None or not (TEMPERATURE_MIN_C <= temperature_min_c <= TEMPERATURE_MAX_C):
        reasons.append("temperature_min_c_missing_or_out_of_range")

    precipitation_probability_pct = _to_float(record.get("precipitation_probability_pct"))
    if precipitation_probability_pct is None or not (
        PRECIPITATION_PROBABILITY_MIN_PCT <= precipitation_probability_pct <= PRECIPITATION_PROBABILITY_MAX_PCT
    ):
        reasons.append("precipitation_probability_pct_missing_or_out_of_range")

    return reasons


def to_silver_prevision_record(record: dict, processed_at: datetime) -> dict:
    """Normaliza un registro Bronze de previsión ya validado (`validate_prevision_record` == []).

    No vuelve a validar. Renombra `captured_at` a `ingested_at` (mismo
    nombre de campo que usa el resto del patrón) y normaliza a `float` los
    campos numéricos que Bronze conserva tal como los publica AEMET (ver
    docstring del módulo).
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "municipio_code": record.get("municipio_code"),
        "municipio_name": record.get("municipio_name"),
        "province": record.get("province"),
        "elaborated_at": record.get("elaborated_at"),
        "valid_date": record.get("valid_date"),
        "sky_state": record.get("sky_state"),
        "sky_state_code": record.get("sky_state_code"),
        "precipitation_probability_pct": _to_float(record.get("precipitation_probability_pct")),
        "temperature_max_c": _to_float(record.get("temperature_max_c")),
        "temperature_min_c": _to_float(record.get("temperature_min_c")),
        "thermal_sensation_max_c": _to_float(record.get("thermal_sensation_max_c")),
        "thermal_sensation_min_c": _to_float(record.get("thermal_sensation_min_c")),
        "humidity_max_pct": _to_float(record.get("humidity_max_pct")),
        "humidity_min_pct": _to_float(record.get("humidity_min_pct")),
        "wind_direction": record.get("wind_direction"),
        "wind_speed_kmh": _to_float(record.get("wind_speed_kmh")),
        "wind_gust_max_kmh": _to_float(record.get("wind_gust_max_kmh")),
        "uv_max": _to_float(record.get("uv_max")),
        "ingested_at": record.get("captured_at"),
        "processed_at": processed_at.isoformat(),
    }


def bronze_to_silver_prevision(records: "list[dict]", processed_at: datetime) -> "tuple[list[dict], list[dict]]":
    """Aplica la puerta de calidad de previsión y transforma los registros que la pasan.

    Devuelve `(silver_records, rejected)`: `rejected` es una lista de
    `{"record": <original>, "reasons": [...]}`, mismo criterio que el resto
    del patrón.
    """
    silver_records = []
    rejected = []

    for record in records:
        reasons = validate_prevision_record(record)
        if reasons:
            rejected.append({"record": record, "reasons": reasons})
        else:
            silver_records.append(to_silver_prevision_record(record, processed_at))

    return silver_records, rejected


# ---------------------------------------------------------------------------
# Avisos de fenómenos meteorológicos adversos (CAP)
# ---------------------------------------------------------------------------


def validate_aviso_record(record: dict) -> "list[str]":
    """Devuelve los motivos por los que un registro de aviso NO debe llegar a Silver.

    Lista vacía == registro válido. Ver docstring del módulo para el
    razonamiento de cada regla.
    """
    reasons: "list[str]" = []

    if not record.get("identifier"):
        reasons.append("identifier_missing")

    if not record.get("zone"):
        reasons.append("zone_missing")

    if record.get("level") not in VALID_LEVELS:
        reasons.append("level_missing_or_invalid")

    if not record.get("phenomenon"):
        reasons.append("phenomenon_missing")

    if _parse_iso(record.get("effective_from")) is None:
        reasons.append("effective_from_missing_or_unparseable")

    ingested_at = _parse_iso(record.get("captured_at"))
    if ingested_at is None:
        reasons.append("ingested_at_missing_or_unparseable")
    elif ingested_at.tzinfo is None:
        reasons.append("ingested_at_not_timezone_aware")

    return reasons


def to_silver_aviso_record(record: dict, processed_at: datetime) -> dict:
    """Normaliza un registro Bronze de aviso ya validado (`validate_aviso_record` == []).

    No vuelve a validar. Renombra `captured_at` a `ingested_at`, mismo
    criterio que el resto del patrón.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "identifier": record.get("identifier"),
        "sent_at": record.get("sent_at"),
        "zone": record.get("zone"),
        "level": record.get("level"),
        "phenomenon": record.get("phenomenon"),
        "probability": record.get("probability"),
        "severity": record.get("severity"),
        "urgency": record.get("urgency"),
        "certainty": record.get("certainty"),
        "effective_from": record.get("effective_from"),
        "effective_until": record.get("effective_until"),
        "headline": record.get("headline"),
        "description": record.get("description"),
        "ingested_at": record.get("captured_at"),
        "processed_at": processed_at.isoformat(),
    }


def bronze_to_silver_avisos(records: "list[dict]", processed_at: datetime) -> "tuple[list[dict], list[dict]]":
    """Aplica la puerta de calidad de avisos y transforma los registros que la pasan.

    Mismo formato de retorno que `bronze_to_silver_prevision`.
    """
    silver_records = []
    rejected = []

    for record in records:
        reasons = validate_aviso_record(record)
        if reasons:
            rejected.append({"record": record, "reasons": reasons})
        else:
            silver_records.append(to_silver_aviso_record(record, processed_at))

    return silver_records, rejected
