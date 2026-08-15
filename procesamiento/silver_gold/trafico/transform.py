"""Transformación Bronze -> Silver del dataset `trafico` (Informo Madrid).

Lógica en **Python puro** (solo `stdlib` + este paquete): sin `pyspark` ni
`great_expectations` como dependencia de import. Es deliberado (ver
`procesamiento/README.md`, sección "Por qué Python puro para la lógica, y
PySpark solo en el job de Glue"): así se puede probar con `unittest` en
cualquier entorno, incluida esta EC2 de desarrollo (disco limitado, sin
Spark ni Great Expectations instalados), y el job real de Glue
(`glue_bronze_to_silver.py`) reutiliza estas mismas funciones envueltas en
un UDF de Spark en vez de reimplementar la lógica en PySpark.

Cada registro Bronze se procesa en dos pasos independientes:

1. `validate_record(record)`: puerta de calidad — una lista de motivos de
   rechazo (vacía si el registro es válido). Un registro con algún motivo
   NO debe llegar a Silver.
2. `to_silver_record(record, processed_at)`: solo se llama sobre registros
   que ya pasaron `validate_record`; reproyecta y normaliza.

Las mismas comprobaciones de `validate_record` están descritas como
expectations declarativas de Great Expectations en `ge_suite.py` — ver ese
módulo para la puerta de calidad "oficial" que ejecuta el job de Glue real,
y el docstring de ese módulo para por qué existen dos representaciones de
la misma regla (una en Python puro, testable aquí; otra en GX, ejecutada en
Glue) en vez de una sola.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .geo import is_within_madrid_bbox, reproject_optional

SCHEMA_VERSION = 1

# Bounds de plausibilidad para las magnitudes del feed de Informo. No son
# límites "oficiales" documentados por el Ayuntamiento (el catálogo de
# datos.madrid.es no publica el rango exacto de `nivelServicio`), son cotas
# laxas para atrapar valores claramente corruptos (negativos, porcentajes
# fuera de 0-100) sin descartar tráfico real intenso.
MAX_PLAUSIBLE_INTENSITY_VPH = 20000
MAX_PLAUSIBLE_SERVICE_LEVEL = 10


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

    if not record.get("point_id"):
        reasons.append("point_id_missing")

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

    location = record.get("location") or {}
    lat, lon = reproject_optional(location.get("x"), location.get("y"))
    if not is_within_madrid_bbox(lat, lon):
        reasons.append("location_missing_or_outside_madrid_bbox")

    intensity_vph = record.get("intensity_vph")
    if intensity_vph is not None and not (0 <= intensity_vph <= MAX_PLAUSIBLE_INTENSITY_VPH):
        reasons.append("intensity_vph_out_of_range")

    occupancy_pct = record.get("occupancy_pct")
    if occupancy_pct is not None and not (0 <= occupancy_pct <= 100):
        reasons.append("occupancy_pct_out_of_range")

    load_pct = record.get("load_pct")
    if load_pct is not None and not (0 <= load_pct <= 100):
        reasons.append("load_pct_out_of_range")

    saturation_intensity_vph = record.get("saturation_intensity_vph")
    if saturation_intensity_vph is not None and saturation_intensity_vph < 0:
        reasons.append("saturation_intensity_vph_negative")

    service_level = record.get("service_level")
    if service_level is not None and not (0 <= service_level <= MAX_PLAUSIBLE_SERVICE_LEVEL):
        reasons.append("service_level_out_of_range")

    # Un sensor que reporta error (`has_error`/`error_code != "N"`) no tiene
    # lecturas fiables: se descarta en vez de dejar pasar valores basura
    # (intensidad/ocupación de un sensor caído) a Silver.
    if record.get("has_error"):
        reasons.append("sensor_reports_error")

    return reasons


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def to_silver_record(record: dict, processed_at: datetime) -> dict:
    """Reproyecta y normaliza un registro Bronze ya validado (`validate_record` == []).

    No vuelve a validar: se asume que el llamador ya filtró los registros
    que no pasan la puerta de calidad (ver `bronze_to_silver` más abajo, o
    el job de Glue).
    """
    location = record.get("location") or {}
    lat, lon = reproject_optional(location.get("x"), location.get("y"))

    occupancy_pct = record.get("occupancy_pct")
    load_pct = record.get("load_pct")
    intensity_vph = record.get("intensity_vph")
    saturation_intensity_vph = record.get("saturation_intensity_vph")

    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "point_id": record.get("point_id"),
        "subarea": record.get("subarea"),
        "description": record.get("description"),
        "access_code": record.get("access_code"),
        "measured_at": record.get("measured_at"),
        "ingested_at": record.get("ingested_at"),
        "processed_at": processed_at.isoformat(),
        "location": {
            "x": location.get("x"),
            "y": location.get("y"),
            "srid_source": location.get("srid"),
            "lat": lat,
            "lon": lon,
            "srid_target": "EPSG:4326",
        },
        # Magnitudes "en bruto" (mismas unidades que Bronze), conservadas
        # para trazabilidad y para consumidores que las prefieran así.
        "intensity_vph": intensity_vph,
        "occupancy_pct": occupancy_pct,
        "load_pct": load_pct,
        "service_level": record.get("service_level"),
        "saturation_intensity_vph": saturation_intensity_vph,
        # Magnitudes normalizadas a una escala 0-1 consistente entre sí,
        # pensadas para comparar puntos de medida con capacidades distintas
        # (p.ej. una avenida de 6 carriles vs. una calle de 1 solo carril):
        # un 100% de ocupación significa lo mismo en cualquier punto, pero
        # el mismo intensity_vph no es comparable sin relativizarlo a la
        # intensidad de saturación propia de ese punto.
        "occupancy_ratio": _ratio(occupancy_pct, 100),
        "load_ratio": _ratio(load_pct, 100),
        "intensity_ratio": _ratio(intensity_vph, saturation_intensity_vph),
    }


def bronze_to_silver(records: "list[dict]", processed_at: datetime) -> "tuple[list[dict], list[dict]]":
    """Aplica la puerta de calidad y transforma los registros que la pasan.

    Devuelve `(silver_records, rejected)`: `rejected` es una lista de
    `{"record": <original>, "reasons": [...]}`, útil para observabilidad
    (contar cuántos registros caen y por qué) — el job de Glue solo escribe
    `silver_records` en el bucket Silver; `rejected` se queda en los logs
    del job (ver `procesamiento/README.md`, "Registros rechazados: solo
    logging, sin zona de cuarentena en este piloto").
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
