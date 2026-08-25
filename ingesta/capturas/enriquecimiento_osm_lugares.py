"""Carga batch puntual de POIs de OpenStreetMap para enriquecer `:Lugar` (tarea 083).

## Qué añade esta fuente que no aportan `poi_madrid`/`aparcamientos`/`cartelera_cines`

Los `:Lugar` del grafo (ver `grafo/nodos.py`) vienen hoy de tres fuentes
municipales (`poi_madrid`, `aparcamientos`, `cartelera_cines_estrenos`),
ninguna de las cuales trae categoría estructurada tipo `amenity`, horario de
apertura ni accesibilidad. OpenStreetMap sí trae ese tipo de etiquetas para
millones de puntos en todo el mundo, de forma gratuita y sin necesidad de
API key -- por eso se añade como fuente de **enriquecimiento** (no de nodos
nuevos, ver `grafo/nodos.py::enrich_lugares_con_osm` y la "Decisión ya
tomada" del enunciado de la tarea 083: unir por proximidad geográfica a los
`:Lugar` ya existentes, no crear `:Lugar` nuevos a partir de OSM).

Se descartó explícitamente Google Places para esto: OSM cubre bien
geodatos/etiquetas de lugar, pero no tiene ningún dato de afluencia o
popularidad en vivo (eso lo cubren las tareas 084/085, sobre
`aforos_peatones_bicicletas`, no esta).

## Esto es una carga puntual de referencia, NO una captura periódica

Mismo criterio que `poi_madrid.py` (tarea 011) y
`barrios_distritos_madrid.py` (tarea 010): las etiquetas de un POI de OSM
(categoría, horario, accesibilidad) no cambian minuto a minuto -- son un
dato de referencia que solo tiene sentido recapturar de vez en cuando, no en
bucle. Este módulo, a propósito, **no tiene modo `--interval-seconds` ni
bucle**, y no escribe en la capa Bronze particionada (`BronzeWriter`): solo
escribe un fichero de muestra pequeño y fijo, pensado para commitearse como
fixture.

## Fuente elegida: Overpass API, instancia pública, sin autenticación

[Overpass API](https://overpass-api.de/api/interpreter) es el motor de
consultas estándar sobre los datos de OpenStreetMap (Overpass QL), con una
instancia pública gratuita mantenida por la comunidad OSM. No requiere API
key ni registro. Se ha verificado en vivo desde este entorno que responde
correctamente a una consulta de bounding box sobre Madrid (ver
`ingesta/README.md`).

Se respeta el uso razonable de esta instancia pública: **una sola consulta**
por bounding box de Madrid (nunca en bucle, nunca programada), con un
`User-Agent` descriptivo (`_REQUEST_HEADERS`) que identifica el proyecto y
deja un contacto, igual que el criterio ya aplicado en `poi_madrid.py` frente
a `esmadrid.com`.

### Bounding box usado

`DEFAULT_BBOX` es la caja delimitadora real del municipio de Madrid, tomada
en vivo con una consulta Overpass sobre la relación administrativa oficial
de OSM (`relation(5326784)`, `admin_level=8`, `boundary=administrative`,
`ine:municipio=28079` -- el mismo código INE que usa
`barrios_distritos_madrid`, tarea 010, confirmando que es la relación
correcta): `out bb;` sobre esa relación devolvió
`(40.3119774, -3.8889539, 40.6437293, -3.5183264)` (`sur, oeste, norte,
este`). No es un valor inventado ni redondeado a mano.

### Por qué se pide un `out body <N>` limitado, no la respuesta completa

Una consulta sin límite de salida sobre las 4 etiquetas (`amenity`, `shop`,
`tourism`, `leisure`) para todo el bounding box de Madrid devuelve **más de
75.000 nodos** (`out count;` verificado en vivo) -- razonable como consulta
puntual de Overpass en sí (una sola consulta, no en bucle), pero muy por
encima de lo que tiene sentido normalizar y commitear como "muestra pequeña"
en este repositorio. `fetch_raw_pois` pide un límite de salida
(`DEFAULT_FETCH_LIMIT`, 250 elementos) directamente en la cláusula `out` de
Overpass QL -- sigue siendo una única consulta real sobre todo el bounding
box, solo que Overpass trunca la respuesta que nos envía. `select_sample_pois`
filtra después, en local, los que tienen nombre y coordenadas conocidas, y
se queda con los primeros `sample_size`.

Una captura real y completa de POIs de OSM más allá de esta muestra (p. ej.
iterando por distrito, o pidiendo lotes con paginación por área) queda como
trabajo futuro deliberado, igual que ocurrió con `poi_madrid` (carga
completa de 935 fichas subida a Bronze de forma manual en la tarea 080, no
en la tarea 011 que solo dejó el productor y una muestra) -- ver
`grafo/README.md` y `doc/083-grafo-enriquecimiento-poi-osm.md`.

### Esquema normalizado

Cada elemento de OSM (siempre `type: "node"` en esta consulta, ya que se
pide `node[...]`, no `way`/`relation`) se normaliza a:

- `osm_id` / `osm_type`: identidad real del elemento en OSM.
- `name`: el tag `name` de OSM.
- `amenity`: el **valor** del primer tag de `amenity`/`shop`/`tourism`/
  `leisure` que tenga el elemento (en ese orden de prioridad si tuviera más
  de uno, caso raro) -- se llama `amenity` de forma genérica, no porque el
  tag de origen fuera necesariamente `amenity` de OSM, sino porque es el
  nombre que usa la propiedad `osm_amenity` del `:Lugar` enriquecido en el
  grafo (`grafo/nodos.py::enrich_lugar_con_osm`) y así no hace falta
  traducir el nombre del campo entre la captura y el grafo.
- `opening_hours` / `wheelchair`: tags de OSM tal cual (formato libre de OSM,
  p. ej. `"Mo-Fr 08:00-02:00; Sa,Su 09:30-02:00"` para horario, o
  `"yes"`/`"no"`/`"limited"` para accesibilidad) -- no se parsean ni
  normalizan más, igual que `schedule`/`price_info` en `poi_madrid.py` se
  dejan como texto libre de la fuente.
- `location.lat`/`location.lon`: coordenadas WGS84 (`EPSG:4326`, el propio
  formato nativo de OSM, sin ninguna reproyección).

No se incluyen más tags de OSM (dirección, teléfono, web...) -- fuera del
alcance mínimo pedido por la tarea 083 (categoría/horario/accesibilidad).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from .bronze import MADRID_TZ, now_madrid

logger = logging.getLogger(__name__)

SOURCE_NAME = "enriquecimiento_osm_lugares"

DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Bounding box real del municipio de Madrid (relation OSM 5326784, ver
# docstring del módulo, "Bounding box usado"): (sur, oeste, norte, este).
DEFAULT_BBOX = (40.3119774, -3.8889539, 40.6437293, -3.5183264)

# Orden de prioridad si un elemento tuviera más de uno de estos tags (caso
# raro en la práctica): se toma el primero que exista.
_POI_TAG_KEYS = ("amenity", "shop", "tourism", "leisure")

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "enriquecimiento_osm_lugares_sample.json"
DEFAULT_SAMPLE_SIZE = 6
DEFAULT_FETCH_LIMIT = 250

# User-Agent descriptivo, con contacto -- uso razonable de la instancia
# pública de Overpass (ver docstring del módulo).
_REQUEST_HEADERS = {
    "User-Agent": "madrono-tfm-ingesta/1.0 (TFM UCM, contacto: madrono.ucm@gmail.com)"
}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la carga, leída de variables de entorno.

    No hay campos de credenciales: Overpass API es pública y no requiere
    API key.
    """

    overpass_url: str
    bbox: "tuple[float, float, float, float]"
    overpass_timeout_seconds: int
    http_timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_size: int
    fetch_limit: int

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            overpass_url=os.environ.get("OSM_OVERPASS_URL", DEFAULT_OVERPASS_URL),
            bbox=DEFAULT_BBOX,
            overpass_timeout_seconds=_env_int("OSM_OVERPASS_TIMEOUT_SECONDS", 25),
            http_timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 60.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 5.0),
            sample_size=_env_int("OSM_SAMPLE_SIZE", DEFAULT_SAMPLE_SIZE),
            fetch_limit=_env_int("OSM_FETCH_LIMIT", DEFAULT_FETCH_LIMIT),
        )


def build_overpass_query(
    bbox: "tuple[float, float, float, float]", overpass_timeout_seconds: int, limit: int
) -> str:
    """Construye la consulta Overpass QL: unión de `node[tag](bbox)` para
    cada uno de `_POI_TAG_KEYS`, con la salida truncada a `limit` elementos
    (ver docstring del módulo, "Por qué se pide un `out body <N>` limitado")."""
    south, west, north, east = bbox
    bbox_clause = f"{south},{west},{north},{east}"
    node_clauses = "".join(f'node["{tag}"]({bbox_clause});' for tag in _POI_TAG_KEYS)
    return f"[out:json][timeout:{overpass_timeout_seconds}];({node_clauses});out body {limit};"


def _fetch_with_retries(config: CaptureConfig, query: str) -> dict:
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.post(
                config.overpass_url,
                data={"data": query},
                headers=_REQUEST_HEADERS,
                timeout=config.http_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if "elements" not in payload:
                raise RuntimeError(f"Respuesta de Overpass sin 'elements': {payload}")
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_exc = exc
            logger.warning(
                "Fallo al consultar Overpass (intento %d/%d): %s", attempt, config.max_retries, exc
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * attempt)
    raise RuntimeError(f"No se pudo consultar Overpass tras {config.max_retries} intentos") from last_exc


def fetch_raw_pois(config: CaptureConfig) -> "list[dict]":
    """Ejecuta la consulta Overpass QL (una sola petición HTTP, ver docstring
    del módulo) y devuelve los `elements` crudos de la respuesta JSON, sin
    normalizar."""
    query = build_overpass_query(config.bbox, config.overpass_timeout_seconds, config.fetch_limit)
    payload = _fetch_with_retries(config, query)
    return payload["elements"]


def _matched_tag_value(tags: dict) -> Optional[str]:
    for key in _POI_TAG_KEYS:
        if key in tags:
            return tags[key]
    return None


def normalize_record(element: dict, ingested_at: datetime) -> Optional[dict]:
    """Normaliza un elemento crudo de Overpass (`type: "node"`, `tags: {...}`)
    al esquema mínimo del módulo (ver docstring, "Esquema normalizado").
    Devuelve `None` si el elemento no trae ninguno de los 4 tags de interés
    (no debería ocurrir con los resultados de `fetch_raw_pois`, que ya filtra
    por esos tags en la propia consulta Overpass, pero se comprueba por
    robustez frente a cualquier otra fuente de `elements`)."""
    tags = element.get("tags") or {}
    amenity = _matched_tag_value(tags)
    if amenity is None:
        return None

    lat, lon = element.get("lat"), element.get("lon")
    location = {"lat": lat, "lon": lon, "srid": "EPSG:4326"} if lat is not None and lon is not None else None

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "osm_id": element.get("id"),
        "osm_type": element.get("type"),
        "name": tags.get("name"),
        "amenity": amenity,
        "opening_hours": tags.get("opening_hours"),
        "wheelchair": tags.get("wheelchair"),
        "ingested_at": ingested_at.astimezone(MADRID_TZ).isoformat(),
        "location": location,
    }


def select_sample_pois(elements: "list[dict]", sample_size: int) -> "list[dict]":
    """Normaliza `elements` (en orden) y se queda con los primeros
    `sample_size` que tengan `name` y coordenadas conocidas -- Overpass no
    permite filtrar barato por "solo con nombre" en la propia consulta,
    mismo criterio que `select_sample_pois` de `poi_madrid.py` descartando
    registros sin coordenadas."""
    ingested_at = now_madrid()
    selected: "list[dict]" = []
    for element in elements:
        record = normalize_record(element, ingested_at)
        if record is None or not record.get("name") or record.get("location") is None:
            continue
        selected.append(record)
        if len(selected) >= sample_size:
            break
    return selected


def _write_json(records: "list[dict]", out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Consulta Overpass, normaliza y guarda una muestra pequeña de POIs de
    OSM.

    Igual que `poi_madrid.py`, esto NO escribe en la capa Bronze particionada
    ni deja nada programado: escribe un único fichero de muestra pequeño y
    fijo (como mucho `config.sample_size` POIs), pensado para commitearse
    como fixture, no para acumularse en disco.
    """
    elements = fetch_raw_pois(config)
    logger.info("Elementos OSM crudos recibidos de Overpass: %d", len(elements))

    records = select_sample_pois(elements, config.sample_size)
    logger.info("POIs OSM de muestra seleccionados: %d", len(records))

    _write_json(records, out_path)
    logger.info("Muestra escrita en %s", out_path)
    return out_path


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Carga batch puntual de referencia de POIs de OpenStreetMap "
            "(Overpass API) dentro del municipio de Madrid, y la guarda como "
            "fixture pequeño. No admite ejecución en bucle ni programada: es "
            "una carga puntual invocada a mano."
        )
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_SAMPLE_PATH,
        help="Ruta del fichero de muestra a escribir",
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
    capture_sample(config, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
