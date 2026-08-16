"""Transformación Bronze -> Silver del dataset `meteorologia` (red de estaciones de Madrid).

Lógica en **Python puro** (solo `stdlib`), mismo motivo que el resto de
datasets del patrón (ver `procesamiento/README.md`, sección "Por qué Python
puro para la lógica, y PySpark solo en el job de Glue"): así se puede probar
con `unittest` en esta EC2 de desarrollo, sin Spark ni Great Expectations
instalados.

## Diferencia real frente a `calidad_aire`: Bronze es ANCHO, no largo

`calidad_aire_madrid.py` entrega un registro Bronze por combinación
estación+contaminante (esquema "largo": una fila, un `value`). Aunque el
enunciado de esta tarea apunta a "mismo backend/formato que calidad_aire",
`ingesta/capturas/meteorologia_madrid.py` (`normalize_station_record`)
agrega deliberadamente **todas** las magnitudes de una estación (hasta 8:
`temperature_c`, `humidity_pct`, `wind_speed_ms`, `wind_direction_deg`,
`pressure_mb`, `solar_radiation_wm2`, `uv_radiation_mwm2`,
`precipitation_lm2`) en un único registro Bronze "ancho" -- ver el docstring
de ese módulo: el objetivo original de la tarea 008 pedía explícitamente un
esquema con "temperatura, humedad, viento, precipitación" como campos de un
mismo registro. No todas las estaciones miden todas las magnitudes (el
catálogo de estaciones marca con `X` cuáles, y el JSON de tiempo real
simplemente omite las que no aplican): un campo de magnitud ausente en
Bronze es `null`, no un error.

Por eso este módulo hace, en el mismo paso Bronze->Silver, lo que
`calidad_aire_madrid.py` ya hace en la propia ingesta: **pivota** de ancho a
largo. `bronze_to_silver` produce **hasta 8 registros Silver por cada
registro Bronze** (uno por magnitud presente y válida), cada uno con su
propio campo `magnitude` (el nombre de campo de `ingesta.MAGNITUDES`, p.ej.
`"temperature_c"`) y `value`. Esto mantiene Silver/Gold en el mismo formato
"largo por magnitud" que el resto del patrón (`calidad_aire` incluido) y
hace que `aggregate.py` pueda agrupar por `(station_id, magnitude, fecha,
hora)` sin tener que repivotar en la agregación.

Cada registro Bronze se procesa en dos niveles de puerta de calidad:

1. `validate_record(record)`: comprobaciones a nivel de estación+instante
   (`station_id`, `measured_at`, `ingested_at`) -- si fallan, **ninguna**
   magnitud de ese registro llega a Silver (no hay instante ni estación a la
   que atribuirlas).
2. `validate_magnitude_value(magnitude, value)`: rango de plausibilidad por
   magnitud -- si una magnitud concreta falla, solo se descarta ESA
   magnitud; el resto de magnitudes válidas del mismo registro (mismo
   station_id+measured_at) sí llegan a Silver. Un sensor de temperatura
   estropeado no debería tirar también la humedad o el viento de la misma
   estación.

Las mismas comprobaciones están descritas como expectations declarativas de
Great Expectations en `ge_suite.py`.

## Sin `geo.py`: `location` ya viene en WGS84

Igual que `transporte_publico_emt`/`bicimad`/`aparcamientos`/`calidad_aire`:
`ingesta/capturas/meteorologia_madrid.py` (`normalize_station_record`)
entrega directamente `location.lat`/`location.lon`, tomadas del CSV de
metadatos "Estaciones de control" de datos.madrid.es, ya en WGS84 -- no hace
falta ninguna reproyección.

## Rango plausible por magnitud

A diferencia de tráfico (magnitudes homogéneas), y de forma parecida a
`calidad_aire` (rango por contaminante), cada magnitud meteorológica tiene
su propia escala y unidad -- un único rango para todas no distinguiría una
temperatura corrupta de una presión válida. `PLAUSIBLE_RANGE_BY_MAGNITUDE`
da un rango `(mínimo, máximo)` laxo por magnitud, pensado solo para atrapar
valores claramente corruptos (fuera de cualquier registro histórico
plausible en Madrid) sin descartar eventos meteorológicos extremos reales:

- `temperature_c`: [-20, 50] -- Madrid nunca ha registrado ni tanto frío
  (mínimo histórico AEMET en Madrid-Retiro: -10.1°C) ni tanto calor (máximo
  histórico: 42.7°C), cota con margen amplio en ambos extremos.
- `humidity_pct`: [0, 100] -- rango físico exacto, no hay margen posible.
- `wind_speed_ms`: [0, 100] -- muy por encima de cualquier ráfaga registrada
  en la Comunidad de Madrid (récords de rachas huracanadas mundiales rondan
  los 100 m/s en tornados; en Madrid ráfagas fuertes rara vez superan 30
  m/s).
- `wind_direction_deg`: [0, 360] -- rango físico exacto (rumbo compás).
- `pressure_mb`: [850, 1050] -- Madrid está a ~600-700m de altitud, así que
  su presión barométrica típica (~930-950 mb) ya es más baja que a nivel del
  mar; el rango cubre con margen tanto esa altitud como los extremos
  sinópticos globales de presión a nivel del mar (870-1085 mb).
- `solar_radiation_wm2`: [0, 1500] -- por encima de la constante solar en
  superficie (~1000-1200 W/m2 en condiciones despejadas de mediodía).
- `uv_radiation_mwm2`: [0, 5000] -- sin una referencia oficial de la propia
  fuente (el PDF de la fuente no publica un máximo), cota deliberadamente
  generosa para no descartar picos reales sin poder contrastarlos.
- `precipitation_lm2`: [0, 300] -- muy por encima de cualquier acumulado
  horario real observado en Madrid (récords mundiales de precipitación en 1h
  rondan los 300 l/m2 en eventos extremos tropicales, un techo con margen
  incluso para una intensidad excepcional en Madrid).

Estos rangos son deliberadamente laxos y no proceden de ningún límite legal
u oficial (a diferencia de, p.ej., un umbral de alerta de AEMET) -- mismo
criterio que `calidad_aire.PLAUSIBLE_MAX_BY_POLLUTANT`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1

# Mismo conjunto de campos que `MAGNITUDES.values()` en
# `ingesta/capturas/meteorologia_madrid.py` -- el nombre de campo Bronze
# (p.ej. "temperature_c") se usa tal cual como valor de `magnitude` en
# Silver/Gold, ya que codifica también la unidad (sufijo `_c`, `_pct`,
# `_ms`...), sin necesidad de una tabla de unidades aparte.
MAGNITUDE_FIELDS: "tuple[str, ...]" = (
    "temperature_c",
    "humidity_pct",
    "wind_speed_ms",
    "wind_direction_deg",
    "pressure_mb",
    "solar_radiation_wm2",
    "uv_radiation_mwm2",
    "precipitation_lm2",
)

# Rango de plausibilidad (mínimo, máximo) por magnitud -- ver docstring del
# módulo para el razonamiento de cada cota. Una magnitud ausente de esta
# tabla (no debería ocurrir: `MAGNITUDE_FIELDS` ya cubre todo
# `ingesta.MAGNITUDES`) no se rechaza por rango, mismo criterio que
# `calidad_aire.PLAUSIBLE_MAX_BY_POLLUTANT`.
PLAUSIBLE_RANGE_BY_MAGNITUDE: "dict[str, tuple[float, float]]" = {
    "temperature_c": (-20.0, 50.0),
    "humidity_pct": (0.0, 100.0),
    "wind_speed_ms": (0.0, 100.0),
    "wind_direction_deg": (0.0, 360.0),
    "pressure_mb": (850.0, 1050.0),
    "solar_radiation_wm2": (0.0, 1500.0),
    "uv_radiation_mwm2": (0.0, 5000.0),
    "precipitation_lm2": (0.0, 300.0),
}


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def validate_record(record: dict) -> "list[str]":
    """Devuelve los motivos por los que NINGUNA magnitud de `record` debe llegar a Silver.

    Lista vacía == el registro tiene estación e instante válidos (aunque
    magnitudes individuales puedan seguir rechazándose, ver
    `validate_magnitude_value`). Cada motivo es una cadena corta y estable,
    útil como métrica.
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

    return reasons


def validate_magnitude_value(magnitude: str, value: float) -> Optional[str]:
    """Devuelve el motivo de rechazo de `value` para `magnitude`, o `None` si es plausible."""
    min_value, max_value = PLAUSIBLE_RANGE_BY_MAGNITUDE.get(magnitude, (float("-inf"), float("inf")))
    if value < min_value or value > max_value:
        return "value_out_of_plausible_range"
    return None


def to_silver_record(record: dict, magnitude: str, value: float, processed_at: datetime) -> dict:
    """Normaliza una magnitud ya validada de un registro Bronze ya validado.

    No vuelve a validar: se asume que el llamador ya filtró vía
    `validate_record`/`validate_magnitude_value` (ver `bronze_to_silver`).
    """
    location = record.get("location") or {}

    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "station_id": record.get("station_id"),
        "station_name": record.get("station_name"),
        "station_address": record.get("station_address"),
        "magnitude": magnitude,
        "value": value,
        "measured_at": record.get("measured_at"),
        "ingested_at": record.get("ingested_at"),
        "processed_at": processed_at.isoformat(),
        "location": {
            "lat": location.get("lat"),
            "lon": location.get("lon"),
            "srid": location.get("srid"),
            "altitude_m": location.get("altitude_m"),
        },
    }


def bronze_to_silver(records: "list[dict]", processed_at: datetime) -> "tuple[list[dict], list[dict]]":
    """Aplica la puerta de calidad y transforma los registros que la pasan.

    Un registro Bronze (una estación, un instante, hasta 8 magnitudes) puede
    producir varios registros Silver (uno por magnitud presente y válida) --
    ver docstring del módulo. Devuelve `(silver_records, rejected)`:
    `rejected` mezcla rechazos a nivel de registro (estación/instante
    inválidos, con la magnitud ausente del item) y a nivel de magnitud
    (estación/instante válidos, una magnitud concreta fuera de rango, con
    `magnitude` presente en el item) -- útil para observabilidad; el job de
    Glue solo escribe `silver_records` en el bucket Silver.
    """
    silver_records = []
    rejected = []
    for record in records:
        reasons = validate_record(record)
        if reasons:
            rejected.append({"record": record, "reasons": reasons})
            continue

        for magnitude in MAGNITUDE_FIELDS:
            value = record.get(magnitude)
            if value is None:
                # Esta estación no mide esta magnitud, o no tuvo ninguna
                # lectura válida ese día (ver `ingesta.MAGNITUDES` /
                # `_latest_valid_hour`) -- no es un error, se omite en
                # silencio.
                continue
            reason = validate_magnitude_value(magnitude, value)
            if reason:
                rejected.append({"record": record, "reasons": [reason], "magnitude": magnitude})
                continue
            silver_records.append(to_silver_record(record, magnitude, value, processed_at))

    return silver_records, rejected
