"""Carga batch puntual de límites administrativos de barrios y distritos de Madrid
(muestra, referencia).

Descarga los límites (geometría) de distritos y barrios del municipio de
Madrid y los normaliza a un esquema mínimo pensado para relacionar el resto
de fuentes de este proyecto (tráfico, calidad del aire, ruido...) con una
unidad geográfica administrativa común (ver `documents/Memoria_TFM FV.docx`,
apartado 6.1, categoría «Contexto urbano»).

## Esto es una carga puntual de referencia, NO una captura periódica

Igual que `callejero_madrid.py` (tarea 009), los límites administrativos de
Madrid son un dato de **referencia** que apenas cambia (una redelimitación de
barrios/distritos es un evento excepcional, no algo que varíe minuto a minuto
u hora a hora como el tráfico o la calidad del aire). No tiene sentido
programar su recaptura ni siquiera cuando exista infraestructura real: por
eso este módulo, a propósito, **no tiene modo `--interval-seconds` ni
bucle**. La carga completa real, el día que se aplique la infraestructura de
la tarea 001, seguirá siendo una carga batch puntual invocada a mano cuando
haga falta (p.ej. tras una redelimitación oficial), no un productor en
bucle.

## Fuente elegida y por qué

Los datasets "Distritos municipales de Madrid" (id
`300497-0-distritos-municipales-madrid`) y "Barrios municipales de Madrid"
(id `300496-0-barrios-madrid`) de
[datos.madrid.es](https://datos.madrid.es/dataset/300497-0-distritos-municipales-madrid)
publican varios formatos (KML, XLSX, CSV, ZIP/SHP), pero ninguno de ellos es
a la vez ligero y fácil de consultar de forma parcial: el CSV/XLSX no traen
geometría (solo id, nombre y área); el KML de distritos sí trae geometría
pero como `LineString` (el contorno, no un polígono relleno) y hay que
descargarlo completo (no admite pedir "solo N distritos"); el KML de barrios
no fue accesible durante esta sesión (la URL de descarga
`Barrios.kml` redirige a una página de mantenimiento genérica del
Ayuntamiento, `indexServicioNoDisponible.html` — el mismo tipo de problema
de disponibilidad puntual visto en la tarea 009 con el portal HTML clásico).

En su lugar, uno de los recursos listados del dataset de distritos apunta
(con el formato mal etiquetado como "CSV" en el catálogo, un error de
metadatos del propio Ayuntamiento) a
`https://sigma.madrid.es/hosted/rest/services/CARTOGRAFIA/LIMITES_ADMINISTRATIVOS/MapServer`:
un servicio **ArcGIS REST (MapServer)** público, con capas de polígonos reales
("DISTRITOS", "BARRIOS") ya en el sistema de referencia deseado. Se prefirió
este servicio a los ficheros KML/ZIP por dos motivos:

1. Devuelve **GeoJSON con polígonos reales** (no líneas de contorno) y ya
   reproyectados a WGS84 (`outSR=4326`) con un simple parámetro de query, sin
   necesidad de parsear coordenadas DMS (a diferencia del callejero de la
   tarea 009) ni de añadir una dependencia de geoprocesado (`pyproj`,
   `shapely`) para reproyectar desde ETRS89/UTM (el CRS nativo del servicio,
   EPSG:25830).
2. Admite **filtrar y ordenar en el servidor** (`where`, `orderByFields`,
   `resultRecordCount`): esta captura puede pedir directamente "los N
   distritos ordenados por código" o "los barrios de estos distritos", sin
   descargar nunca el conjunto completo (21 distritos / 131 barrios) a este
   entorno, ni siquiera en memoria — a diferencia de `callejero_madrid.py`
   (tarea 009) o `ruido_madrid.py` (tarea 007), que sí tuvieron que
   descargar un CSV completo porque su fuente no ofrecía este tipo de
   filtrado remoto.

Se ha verificado en vivo desde este entorno que el servicio MapServer es
accesible **sin ninguna autenticación ni API key**.

### Simplificación de la geometría

Algunos distritos tienen geometrías con miles de vértices (Fuencarral - El
Pardo, el distrito más grande, tiene 2.910 puntos en su polígono sin
simplificar) — no son un problema para una carga completa real, pero sí
inflarían innecesariamente una muestra pensada para ser pequeña y legible
como fixture de test. Este módulo aplica una simplificación
**Douglas-Peucker** (implementación propia, sin dependencias adicionales)
a cada anillo del polígono, con una tolerancia configurable
(`MADRID_BOUNDARIES_SIMPLIFY_TOLERANCE_DEG`, por defecto `0.0001` grados,
~8-11 metros en la latitud de Madrid). Con la tolerancia por defecto,
Fuencarral - El Pardo pasa de 2.910 a ~450 puntos conservando la forma
general del contorno. Cada registro guarda `simplified` y
`simplify_tolerance_deg` para que quede explícito que la geometría no es
bit a bit la de la fuente. Poner la tolerancia a `0` desactiva la
simplificación y conserva la geometría exacta de la fuente.

TODO(kafka): igual que `callejero_madrid.py`, esta fuente es de referencia y
no encaja con el patrón de un topic Kafka por evento — su destino natural es
directamente el grafo Neo4j (o una tabla de dimensión en el lakehouse), no
un stream. Se deja la nota igualmente por consistencia con el resto de
módulos, pero no se espera que esta fuente conecte nunca a un broker Kafka.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_SERVICE_BASE_URL = (
    "https://sigma.madrid.es/hosted/rest/services/CARTOGRAFIA/LIMITES_ADMINISTRATIVOS/MapServer"
)
# Capas del MapServer con la geometría más detallada disponible (grupo de
# escalas "10.000-500", la de mayor precisión que publica el servicio).
DEFAULT_DISTRICTS_LAYER_ID = 26
DEFAULT_NEIGHBOURHOODS_LAYER_ID = 25

SOURCE_DISTRICTS = "madrid_distritos"
SOURCE_NEIGHBOURHOODS = "madrid_barrios"

DEFAULT_DISTRICTS_SAMPLE_PATH = (
    Path(__file__).parent / "samples" / "barrios_distritos_madrid_distritos_sample.json"
)
DEFAULT_NEIGHBOURHOODS_SAMPLE_PATH = (
    Path(__file__).parent / "samples" / "barrios_distritos_madrid_barrios_sample.json"
)

# Nº de distritos en la muestra, y de barrios por cada uno de esos distritos.
DEFAULT_DISTRICT_SAMPLE_SIZE = 3
DEFAULT_MAX_NEIGHBOURHOODS_PER_DISTRICT = 2

# Tolerancia (en grados) de la simplificación Douglas-Peucker aplicada a cada
# polígono. 0 desactiva la simplificación.
DEFAULT_SIMPLIFY_TOLERANCE_DEG = 0.0001


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la carga, leída de variables de entorno.

    No hay campos de credenciales: el servicio ArcGIS REST usado aquí es
    público y no requiere API key.
    """

    service_base_url: str
    districts_layer_id: int
    neighbourhoods_layer_id: int
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    district_sample_size: int
    max_neighbourhoods_per_district: int
    simplify_tolerance_deg: float

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            service_base_url=os.environ.get(
                "MADRID_BOUNDARIES_SERVICE_URL", DEFAULT_SERVICE_BASE_URL
            ),
            districts_layer_id=_env_int(
                "MADRID_BOUNDARIES_DISTRICTS_LAYER_ID", DEFAULT_DISTRICTS_LAYER_ID
            ),
            neighbourhoods_layer_id=_env_int(
                "MADRID_BOUNDARIES_NEIGHBOURHOODS_LAYER_ID", DEFAULT_NEIGHBOURHOODS_LAYER_ID
            ),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 15.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            district_sample_size=_env_int(
                "MADRID_BOUNDARIES_DISTRICT_SAMPLE_SIZE", DEFAULT_DISTRICT_SAMPLE_SIZE
            ),
            max_neighbourhoods_per_district=_env_int(
                "MADRID_BOUNDARIES_MAX_NEIGHBOURHOODS_PER_DISTRICT",
                DEFAULT_MAX_NEIGHBOURHOODS_PER_DISTRICT,
            ),
            simplify_tolerance_deg=_env_float(
                "MADRID_BOUNDARIES_SIMPLIFY_TOLERANCE_DEG", DEFAULT_SIMPLIFY_TOLERANCE_DEG
            ),
        )


def _fetch_json_with_retries(config: CaptureConfig, url: str, params: dict) -> dict:
    """Consulta una URL con reintentos simples y backoff lineal."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.get(url, params=params, timeout=config.timeout_seconds)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Fallo al consultar %s (intento %d/%d): %s", url, attempt, config.max_retries, exc
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * attempt)
    raise RuntimeError(f"No se pudo consultar {url} tras {config.max_retries} intentos") from last_exc


def fetch_features(
    config: CaptureConfig,
    layer_id: int,
    where: str,
    order_by_fields: str,
    result_record_count: Optional[int] = None,
) -> list[dict]:
    """Consulta una capa del MapServer y devuelve sus features GeoJSON.

    El filtrado (`where`), orden (`orderByFields`) y límite de resultados
    (`resultRecordCount`) los aplica el propio servicio: esta función nunca
    descarga la capa completa.
    """
    url = f"{config.service_base_url}/{layer_id}/query"
    params = {
        "where": where,
        "outFields": "*",
        "outSR": "4326",
        "orderByFields": order_by_fields,
        "f": "geojson",
    }
    if result_record_count is not None:
        params["resultRecordCount"] = result_record_count
    data = _fetch_json_with_retries(config, url, params)
    if "error" in data:
        raise RuntimeError(f"El servicio devolvió un error para {url}: {data['error']}")
    return data.get("features", [])


def _perpendicular_distance(point: list, start: list, end: list) -> float:
    x, y = point[0], point[1]
    x1, y1 = start[0], start[1]
    x2, y2 = end[0], end[1]
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)
    proj_x, proj_y = x1 + t * dx, y1 + t * dy
    return math.hypot(x - proj_x, y - proj_y)


def _douglas_peucker(points: list, tolerance: float) -> list:
    """Simplifica una polilínea con el algoritmo Douglas-Peucker (sin dependencias)."""
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    max_dist, max_idx = 0.0, 0
    for i in range(1, len(points) - 1):
        dist = _perpendicular_distance(points[i], start, end)
        if dist > max_dist:
            max_dist, max_idx = dist, i
    if max_dist > tolerance:
        left = _douglas_peucker(points[: max_idx + 1], tolerance)
        right = _douglas_peucker(points[max_idx:], tolerance)
        return left[:-1] + right
    return [start, end]


def simplify_geometry(geometry: dict, tolerance: float) -> tuple[dict, bool]:
    """Simplifica los anillos de un Polygon/MultiPolygon GeoJSON.

    Devuelve la geometría (simplificada o tal cual si `tolerance <= 0`) y si
    se aplicó simplificación.
    """
    if tolerance <= 0:
        return geometry, False

    geom_type = geometry["type"]
    if geom_type == "Polygon":
        rings = [_douglas_peucker(ring, tolerance) for ring in geometry["coordinates"]]
        return {"type": "Polygon", "coordinates": rings}, True
    if geom_type == "MultiPolygon":
        polygons = [
            [_douglas_peucker(ring, tolerance) for ring in polygon]
            for polygon in geometry["coordinates"]
        ]
        return {"type": "MultiPolygon", "coordinates": polygons}, True
    # Tipo de geometría no esperado en esta fuente (ni distritos ni barrios
    # han traído nunca un Point/LineString en la investigación de esta
    # tarea): se conserva tal cual, sin intentar simplificar.
    return geometry, False


def normalize_district_record(feature: dict, ingested_at: datetime, tolerance: float) -> dict:
    """Normaliza una feature GeoJSON de distrito al esquema mínimo."""
    props = feature["properties"]
    geometry, simplified = simplify_geometry(feature["geometry"], tolerance)
    return {
        "schema_version": 1,
        "source": SOURCE_DISTRICTS,
        "district_id": props.get("COD_DIS_TX"),
        "name": props.get("NOMBRE"),
        "area_m2": props.get("Shape.STArea()"),
        "ingested_at": ingested_at.astimezone(timezone.utc).isoformat(),
        "simplified": simplified,
        "simplify_tolerance_deg": tolerance if simplified else None,
        "geometry": {**geometry, "srid": "EPSG:4326"},
    }


def normalize_neighbourhood_record(feature: dict, ingested_at: datetime, tolerance: float) -> dict:
    """Normaliza una feature GeoJSON de barrio al esquema mínimo."""
    props = feature["properties"]
    geometry, simplified = simplify_geometry(feature["geometry"], tolerance)
    return {
        "schema_version": 1,
        "source": SOURCE_NEIGHBOURHOODS,
        "neighbourhood_id": props.get("COD_BAR"),
        "name": props.get("NOMBRE"),
        "district_id": props.get("COD_DIS_TX"),
        "district_name": props.get("NOMDIS"),
        "area_m2": props.get("Shape.STArea()"),
        "ingested_at": ingested_at.astimezone(timezone.utc).isoformat(),
        "simplified": simplified,
        "simplify_tolerance_deg": tolerance if simplified else None,
        "geometry": {**geometry, "srid": "EPSG:4326"},
    }


def select_sample_districts(config: CaptureConfig) -> list[dict]:
    """Pide al servicio los primeros `district_sample_size` distritos, ordenados por código."""
    return fetch_features(
        config,
        config.districts_layer_id,
        where="1=1",
        order_by_fields="COD_DIS_TX",
        result_record_count=config.district_sample_size,
    )


def _cap_features_per_district(features: list[dict], max_per_district: int) -> list[dict]:
    """Se queda con como mucho `max_per_district` features por cada `COD_DIS_TX`.

    Extraída de `select_sample_neighbourhoods` para poder probarla sin red,
    igual que `select_crossings_for_vias` acota cruces por vial en
    `callejero_madrid.py` (tarea 009).
    """
    counts: dict[str, int] = {}
    selected: list[dict] = []
    for feature in features:
        district_id = feature["properties"].get("COD_DIS_TX")
        if counts.get(district_id, 0) >= max_per_district:
            continue
        counts[district_id] = counts.get(district_id, 0) + 1
        selected.append(feature)
    return selected


def select_sample_neighbourhoods(config: CaptureConfig, district_ids: list) -> list[dict]:
    """Pide al servicio los barrios de `district_ids`, acotados a `max_neighbourhoods_per_district` cada uno.

    El filtrado por distrito y el orden los aplica el servicio (una única
    consulta para todos los distritos de la muestra); el tope por distrito se
    aplica en Python tras la respuesta (`_cap_features_per_district`).
    """
    if not district_ids:
        return []
    codes = ",".join(f"'{code}'" for code in district_ids)
    features = fetch_features(
        config,
        config.neighbourhoods_layer_id,
        where=f"COD_DIS_TX IN ({codes})",
        order_by_fields="COD_DIS_TX,COD_BAR",
    )
    return _cap_features_per_district(features, config.max_neighbourhoods_per_district)


def _write_json(records: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(
    config: CaptureConfig, districts_out_path: Path, neighbourhoods_out_path: Path
) -> tuple[Path, Path]:
    """Descarga, normaliza y guarda una muestra pequeña de distritos y sus barrios.

    Igual que `callejero_madrid.py` (tarea 009), esto NO escribe en la capa
    Bronze particionada ni deja nada programado: escribe dos ficheros de
    muestra pequeños y fijos, pensados para commitearse como fixtures, no
    para acumularse en disco. El servicio de origen nunca se consulta por
    más distritos/barrios de los que entran en la muestra.
    """
    ingested_at = datetime.now(timezone.utc)

    district_features = select_sample_districts(config)
    district_records = [
        normalize_district_record(f, ingested_at, config.simplify_tolerance_deg)
        for f in district_features
    ]
    district_ids = [r["district_id"] for r in district_records if r["district_id"]]
    logger.info("Distritos de muestra seleccionados: %d", len(district_records))

    neighbourhood_features = select_sample_neighbourhoods(config, district_ids)
    neighbourhood_records = [
        normalize_neighbourhood_record(f, ingested_at, config.simplify_tolerance_deg)
        for f in neighbourhood_features
    ]
    logger.info("Barrios de muestra seleccionados: %d", len(neighbourhood_records))

    _write_json(district_records, districts_out_path)
    _write_json(neighbourhood_records, neighbourhoods_out_path)

    logger.info("Muestra de distritos escrita en %s", districts_out_path)
    logger.info("Muestra de barrios escrita en %s", neighbourhoods_out_path)
    return districts_out_path, neighbourhoods_out_path


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Carga batch puntual de referencia de los límites administrativos de "
            "distritos y barrios de Madrid, y la guarda como fixtures pequeños. No "
            "admite ejecución en bucle ni programada: es una carga puntual invocada "
            "a mano, pensada para no repetirse salvo que los límites administrativos "
            "cambien de forma relevante."
        )
    )
    parser.add_argument(
        "--out-distritos",
        type=Path,
        default=DEFAULT_DISTRICTS_SAMPLE_PATH,
        help="Ruta del fichero de muestra de distritos a escribir",
    )
    parser.add_argument(
        "--out-barrios",
        type=Path,
        default=DEFAULT_NEIGHBOURHOODS_SAMPLE_PATH,
        help="Ruta del fichero de muestra de barrios a escribir",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Nivel de logging (DEBUG, INFO, WARNING, ...)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = CaptureConfig.from_env()
    capture_sample(config, args.out_distritos, args.out_barrios)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
