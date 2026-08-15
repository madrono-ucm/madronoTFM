"""Carga batch puntual de la red estructural de transporte de Madrid (GTFS, CRTM).

Descarga los feeds GTFS estáticos que publica el Consorcio Regional de
Transportes de Madrid (CRTM) en su portal de datos abiertos y los normaliza
a un esquema mínimo de **líneas con sus paradas principales** (no el grafo
completo de horarios): para cada línea de muestra, la secuencia ordenada de
paradas de un viaje representativo. Es el contexto estructural de la red
(qué líneas existen, por dónde pasan) que hoy le falta al proyecto — la
tarea 003 (llegadas en vivo de la EMT) sigue bloqueada por un registro con
email sin verificar, pero esta captura no depende de ninguna cuenta.

## Esto es una carga puntual de referencia, NO una captura periódica

Igual que `callejero_madrid.py` (tarea 009), `barrios_distritos_madrid.py`
(tarea 010), `poi_madrid.py` (tarea 011) y `calendario_laboral_madrid.py`
(tarea 020), la red de líneas y paradas de transporte de Madrid es un dato
de **referencia**: CRTM publica "cambios de servicio" unas pocas veces al
año (nuevas líneas, cambios de recorrido, nuevas estaciones), no minuto a
minuto. No tiene sentido programar su recaptura ni siquiera cuando exista
infraestructura real: por eso este módulo, a propósito, **no tiene modo
`--interval-seconds` ni bucle**.

## Fuente elegida y por qué

Portal de datos abiertos del CRTM (`datos.crtm.es`, un sitio ArcGIS Hub).
La búsqueda documentada por el propio portal (`/search`) es una SPA que no
devuelve resultados por HTTP directo; el catálogo completo sí es accesible
sin autenticación a través del feed DCAT-US 1.1 que expone todo portal
ArcGIS Hub (`https://datos.crtm.es/api/feed/dcat-us/1.1.json`, ~700 KB,
estándar [project-open-data.cio.gov](https://project-open-data.cio.gov/v1.1/schema/)).
Filtrando ese catálogo por "gtfs" aparecen **6 feeds GTFS estáticos**, uno
por red/operador:

| `mode` (este módulo) | Red                                            | Tamaño del ZIP |
|-----------------------|------------------------------------------------|----------------|
| `metro`               | Metro de Madrid                                | 1.5 MB         |
| `emt`                 | Autobuses urbanos EMT Madrid                   | 18 MB          |
| `metro_ligero`        | Metro Ligero / Tranvía                         | 0.4 MB         |
| `cercanias`           | Cercanías Renfe (ámbito CRTM)                  | 6 KB           |
| `urbano_cm`           | Autobuses urbanos de la Comunidad de Madrid    | 8 MB           |
| `interurbano_cm`      | Autobuses interurbanos de la Comunidad de Madrid | 72 MB        |

Cada item del catálogo (tipo "CSV Collection" en ArcGIS) se descarga sin
autenticación desde el endpoint estándar de contenido de ArcGIS Online
`https://www.arcgis.com/sharing/rest/content/items/{item_id}/data`
(verificado en vivo para los 6 feeds; es el mismo endpoint que usa el botón
"Download" de la página de cada dataset en `datos.crtm.es`, no una URL
inventada). `MODE_FEEDS` mapea cada `mode` a su `item_id`.

### Solo 4 de los 6 modos en la muestra por defecto

`DEFAULT_MODES` incluye `metro`, `emt`, `metro_ligero` y `cercanias` — los
tres que el enunciado de esta tarea pedía investigar explícitamente más
Cercanías (por el hallazgo de calidad de datos que se documenta abajo).
Se excluyen de la muestra por defecto (aunque quedan soportados vía
`CRTM_GTFS_MODES` para quien los necesite) `urbano_cm` e `interurbano_cm`:
ambos cubren la red de autobuses de la **Comunidad de Madrid** (municipios
fuera de la capital), no la red estructural de la ciudad de Madrid que es
el objeto de esta tarea, y el segundo (72 MB) es, con diferencia, el feed
más pesado del catálogo — no aporta valor añadido de esquema sobre `emt`
para una primera muestra.

### Hallazgo: no existe GTFS-RT abierto de CRTM (relevante para la tarea 003)

Se ha buscado explícitamente, en vivo, un feed GTFS-RT (alertas de
servicio, posición de vehículos, retrasos) del CRTM, sin encontrar
ninguno accesible sin cuenta:

- El catálogo DCAT completo del portal (`/api/feed/dcat-us/1.1.json`) solo
  contiene los 6 GTFS estáticos de la tabla anterior; una búsqueda por
  `gtfs-rt`, `tiempo real`, `realtime`, `alertas`, `incidencias`,
  `protobuf`, `vehicle`, `trip update` en el buscador del propio portal
  (`/api/search/v1/collections/dataset/items?q=...`) no devuelve ningún
  resultado adicional. El mismo resultado se obtiene en el portal hermano
  `datos-movilidad.crtm.es` ("Portal de movilidad multimodal" del propio
  CRTM).
- [Transitland](https://www.transit.land/feeds/f-ezjm-consorcioregionaldetransportesdemadrid),
  el catálogo independiente de feeds GTFS/GTFS-RT más usado a nivel
  mundial, solo tiene registrado el feed GTFS estático de CRTM (con 23
  versiones históricas archivadas desde 2017); no hay feed GTFS-RT asociado.
- No existe un host `api.crtm.es` ni `opendata.crtm.es` accesible (fallo de
  conexión TLS en ambos, verificado en vivo).

**Conclusión**: CRTM no publica alertas/incidencias/retrasos en tiempo real
de forma abierta a nivel de toda la red multimodal. Esto no desbloquea la
tarea 003: la única fuente de llegadas en vivo verificada hasta ahora
sigue siendo la API MobilityLabs de la EMT (`openapi.emtmadrid.es`,
`transporte_publico_madrid.py`), bloqueada por su registro con email sin
verificar. Es un hallazgo negativo, pero documentado para no repetir esta
misma búsqueda en una futura tarea.

### Formato real encontrado

Los 6 feeds son GTFS estándar (`agency.txt`, `routes.txt`, `stops.txt`,
`trips.txt`, `stop_times.txt`, `calendar(_dates).txt`, `shapes.txt`,
`frequencies.txt`, `fare_attributes.txt`, `fare_rules.txt`, `feed_info.txt`),
con `route_type` según la especificación GTFS (`0`=tranvía, `1`=metro,
`2`=cercanías/tren, `3`=autobús — los cuatro valores presentes en los
modos de la muestra). `stops.txt` incluye, junto a las paradas reales
(`location_type` vacío o `"0"`), elementos de accesibilidad con prefijo
`acc_` en el `stop_id` (ascensores, accesos de superficie...,
`location_type="2"`) que este módulo filtra al construir las paradas de
cada línea (`_index_boarding_stops`): no son puntos de embarque.

**Hallazgo de calidad de datos, documentado y no corregido**: el feed de
`cercanias` publica `routes.txt` y `stops.txt` completos (las 10 líneas de
Cercanías con sus estaciones), pero `trips.txt` y `stop_times.txt` están
**vacíos** (solo la cabecera, verificado en vivo) — CRTM no modela el
servicio programado de Cercanías en su GTFS (es Renfe quien opera esa red;
probablemente CRTM solo enlaza la línea con la red multimodal). Por eso
las líneas de `cercanias` en la muestra tienen `"stops": []`: no es un
fallo de este módulo, es lo que la fuente publica. El resto de modos
(`metro`, `emt`, `metro_ligero`) sí tienen horarios completos, con una
excepción puntual: dentro de `metro`, la línea 3 (`route_id="4__3___"`,
incluida en la muestra por ser una de las primeras del fichero) tampoco
tiene ningún `trip_id` en `trips.txt` (verificado en vivo, a diferencia de
las líneas 1, 2, 4-12 y R del mismo feed, que sí los tienen), así que
también aparece con `"stops": []` en la muestra committeada — otro hueco
real de la fuente, no de este módulo.

### Esquema mínimo elegido: líneas con su secuencia de paradas de un viaje representativo

El enunciado de la tarea explícita no hace falta modelar el grafo completo
de horarios. Para cada línea de muestra se elige un único viaje (`trip_id`)
representativo (el primero con `direction_id="0"`, o el primero disponible
si no hay ninguno con ese sentido) y se usa su `stop_times.txt` para
obtener la secuencia ordenada real de paradas de esa línea en ese sentido —
más informativo que solo `routes.txt` (que no dice por dónde pasa la
línea) sin necesitar modelar calendarios, frecuencias ni el resto de
viajes. `stop_times.txt` es, con diferencia, el fichero más grande de un
GTFS (84 MB sin comprimir en el feed de `emt`): `_read_stop_times_for_trips`
lo recorre en streaming directamente desde el ZIP y descarta cada fila que
no pertenezca a uno de los pocos `trip_id` de la muestra, sin cargarlo
entero en memory ni escribirlo a disco.

### Un único dataset con campo `mode`, no un fichero por red

Sigue el mismo patrón ya establecido en las tareas 013, 016 y 017: la
muestra combina los modos de `DEFAULT_MODES` en
`crtm_red_transporte_madrid_sample.json` con un campo `mode` que distingue
la red de origen de cada línea; quien necesite solo un modo filtra por ese
campo.

TODO(kafka): igual que `callejero_madrid.py`/`barrios_distritos_madrid.py`/
`poi_madrid.py`/`calendario_laboral_madrid.py`, esta fuente es de
referencia y no encaja con el patrón de un topic Kafka por evento — su
destino natural es el grafo Neo4j (líneas y paradas como nodos, tramos
como aristas) o una tabla de dimensión en el lakehouse, no un stream. Se
deja la nota igualmente por consistencia con el resto de módulos, pero no
se espera que esta fuente conecte nunca a un broker Kafka.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from .bronze import MADRID_TZ, now_madrid

logger = logging.getLogger(__name__)

SOURCE = "crtm_red_transporte"

# Endpoint estándar de descarga de contenido de ArcGIS Online: el mismo que
# usa el botón "Download" de cada dataset en datos.crtm.es (ver docstring).
ARCGIS_ITEM_DOWNLOAD_URL = "https://www.arcgis.com/sharing/rest/content/items/{item_id}/data"


@dataclass(frozen=True)
class GtfsFeed:
    label: str
    item_id: str


# item_id de cada feed GTFS en el catálogo ArcGIS Hub de datos.crtm.es,
# obtenidos del feed DCAT-US público del portal (ver docstring del módulo).
MODE_FEEDS: dict[str, GtfsFeed] = {
    "metro": GtfsFeed("Metro de Madrid", "5c7f2951962540d69ffe8f640d94c246"),
    "emt": GtfsFeed("Autobuses urbanos EMT Madrid", "868df0e58fca47e79b942902dffd7da0"),
    "metro_ligero": GtfsFeed("Metro Ligero / Tranvía", "aaed26cc0ff64b0c947ac0bc3e033196"),
    "cercanias": GtfsFeed("Cercanías Renfe (ámbito CRTM)", "1a25440bf66f499bae2657ec7fb40144"),
    "urbano_cm": GtfsFeed("Autobuses urbanos de la Comunidad de Madrid", "357e63c2904f43aeb5d8a267a64346d8"),
    "interurbano_cm": GtfsFeed("Autobuses interurbanos de la Comunidad de Madrid", "885399f83408473c8d815e40c5e702b7"),
}

# Los 4 modos investigados explícitamente por el enunciado (metro, EMT,
# metro ligero) más cercanías (por el hallazgo de calidad de datos, ver
# docstring). urbano_cm/interurbano_cm quedan soportados pero fuera de la
# muestra por defecto: cubren la Comunidad de Madrid, no la red estructural
# de la ciudad, y el segundo es el feed más pesado del catálogo (72 MB).
DEFAULT_MODES = ("metro", "emt", "metro_ligero", "cercanias")

# GTFS route_type -> etiqueta legible (valores realmente presentes en los
# feeds de CRTM: 0, 1, 2, 3; se completa el resto de la especificación por
# si algún modo futuro lo usara).
ROUTE_TYPE_LABELS = {
    "0": "tranvia",
    "1": "metro",
    "2": "cercanias",
    "3": "autobus",
    "4": "ferry",
    "5": "funicular_cable",
    "6": "telecabina",
    "7": "funicular",
}

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "crtm_red_transporte_madrid_sample.json"
DEFAULT_ROUTES_PER_MODE = 3


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la carga, leída de variables de entorno.

    No hay campos de credenciales: los feeds GTFS de CRTM usados aquí son
    públicos y no requieren API key ni cuenta.
    """

    modes: tuple[str, ...]
    routes_per_mode: int
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        modes_raw = os.environ.get("CRTM_GTFS_MODES")
        modes = (
            tuple(m.strip() for m in modes_raw.split(",") if m.strip())
            if modes_raw
            else DEFAULT_MODES
        )
        return cls(
            modes=modes,
            routes_per_mode=_env_int("CRTM_GTFS_ROUTES_PER_MODE", DEFAULT_ROUTES_PER_MODE),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 60.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
        )


def _fetch_with_retries(config: CaptureConfig, url: str) -> bytes:
    """Descarga una URL, con reintentos simples y backoff lineal."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.get(url, timeout=config.timeout_seconds)
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Fallo al descargar %s (intento %d/%d): %s", url, attempt, config.max_retries, exc
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * attempt)
    raise RuntimeError(f"No se pudo descargar {url} tras {config.max_retries} intentos") from last_exc


def fetch_gtfs_zip(config: CaptureConfig, mode: str) -> bytes:
    """Descarga el ZIP GTFS completo de `mode` (ver `MODE_FEEDS`)."""
    feed = MODE_FEEDS[mode]
    url = ARCGIS_ITEM_DOWNLOAD_URL.format(item_id=feed.item_id)
    return _fetch_with_retries(config, url)


def _read_csv_member(zf: zipfile.ZipFile, name: str) -> list[dict]:
    """Lee un fichero CSV de un GTFS entero en memoria.

    Válido para todos los ficheros de un GTFS salvo `stop_times.txt`, que
    puede pesar decenas de MB sin comprimir (ver `_read_stop_times_for_trips`).
    """
    with zf.open(name) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        return list(csv.DictReader(text))


def _read_stop_times_for_trips(zf: zipfile.ZipFile, trip_ids: set[str]) -> dict[str, list[dict]]:
    """Recorre `stop_times.txt` en streaming y se queda solo con `trip_ids`.

    `stop_times.txt` es, con diferencia, el fichero más grande de un GTFS
    (84 MB sin comprimir en el feed de EMT usado en esta captura): se lee
    fila a fila directamente desde el ZIP y se descarta cada una que no
    pertenezca a uno de los pocos viajes de muestra pedidos, sin cargar el
    fichero completo en memoria ni escribirlo a disco.
    """
    wanted: dict[str, list[dict]] = {trip_id: [] for trip_id in trip_ids}
    if not wanted:
        return wanted
    with zf.open("stop_times.txt") as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        for row in csv.DictReader(text):
            rows = wanted.get(row["trip_id"])
            if rows is not None:
                rows.append(row)
    for rows in wanted.values():
        rows.sort(key=lambda r: int(r["stop_sequence"]))
    return wanted


def _clean(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _index_boarding_stops(stops: list[dict]) -> dict[str, dict]:
    """Indexa `stops.txt` por `stop_id`, descartando elementos de accesibilidad.

    La fuente incluye, junto a las paradas reales (`location_type` vacío o
    `"0"`), elementos de accesibilidad con prefijo `acc_` en el `stop_id`
    (ascensores, accesos de superficie..., `location_type="2"`): no son
    puntos de embarque y se excluyen aquí.
    """
    return {s["stop_id"]: s for s in stops if _clean(s.get("location_type")) in (None, "0")}


def _select_representative_trip(trips: list[dict], route_id: str) -> Optional[str]:
    """Elige un `trip_id` representativo de `route_id`: el primero en sentido `0`.

    Si no hay ningún viaje en sentido `0` (o la línea no tiene viajes en
    absoluto, ver el hallazgo sobre `cercanias` en el docstring del
    módulo), se toma el primero disponible, o se devuelve `None`.
    """
    candidates = [t for t in trips if t["route_id"] == route_id]
    if not candidates:
        return None
    for trip in candidates:
        if trip.get("direction_id") == "0":
            return trip["trip_id"]
    return candidates[0]["trip_id"]


def select_sample_routes(
    routes: list[dict], trips: list[dict], sample_size: int
) -> list[tuple[dict, Optional[str]]]:
    """Toma las primeras `sample_size` líneas de `routes.txt`, con su viaje representativo."""
    selected = []
    for route in routes[:sample_size]:
        trip_id = _select_representative_trip(trips, route["route_id"])
        selected.append((route, trip_id))
    return selected


def _normalize_stop_ref(row: dict, stops_by_id: dict) -> Optional[dict]:
    stop = stops_by_id.get(row["stop_id"])
    if stop is None:
        return None
    lat = _clean(stop.get("stop_lat"))
    lon = _clean(stop.get("stop_lon"))
    return {
        "stop_id": stop["stop_id"],
        "name": _clean(stop.get("stop_name")),
        "sequence": int(row["stop_sequence"]),
        "location": {
            "lat": float(lat) if lat else None,
            "lon": float(lon) if lon else None,
            "srid": "EPSG:4326",
        },
    }


def normalize_route(
    route: dict,
    trip_id: Optional[str],
    stop_times_by_trip: dict[str, list[dict]],
    stops_by_id: dict[str, dict],
    mode: str,
    ingested_at: datetime,
) -> dict:
    """Normaliza una línea (`routes.txt`) con la secuencia de paradas de su viaje representativo.

    `stops` queda vacío si la línea no tiene ningún viaje en la fuente
    (ver el hallazgo de calidad de datos sobre `cercanias` en el docstring
    del módulo) o si su viaje representativo no aparece en `stop_times.txt`.
    """
    rows = stop_times_by_trip.get(trip_id, []) if trip_id else []
    stops = [s for s in (_normalize_stop_ref(row, stops_by_id) for row in rows) if s is not None]

    return {
        "schema_version": 1,
        "source": SOURCE,
        "mode": mode,
        "route_id": route["route_id"],
        "short_name": _clean(route.get("route_short_name")),
        "long_name": _clean(route.get("route_long_name")),
        "route_type": ROUTE_TYPE_LABELS.get(route.get("route_type"), route.get("route_type")),
        "color": _clean(route.get("route_color")),
        "url": _clean(route.get("route_url")),
        "ingested_at": ingested_at.astimezone(MADRID_TZ).isoformat(),
        "stops": stops,
    }


def fetch_and_normalize_mode(config: CaptureConfig, mode: str, ingested_at: datetime) -> list[dict]:
    """Descarga el feed GTFS de `mode` y normaliza una muestra de sus líneas."""
    zip_bytes = fetch_gtfs_zip(config, mode)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        routes = _read_csv_member(zf, "routes.txt")
        trips = _read_csv_member(zf, "trips.txt")
        stops = _read_csv_member(zf, "stops.txt")

        selected = select_sample_routes(routes, trips, config.routes_per_mode)
        wanted_trip_ids = {trip_id for _, trip_id in selected if trip_id}
        stop_times_by_trip = _read_stop_times_for_trips(zf, wanted_trip_ids)

    stops_by_id = _index_boarding_stops(stops)
    return [
        normalize_route(route, trip_id, stop_times_by_trip, stops_by_id, mode, ingested_at)
        for route, trip_id in selected
    ]


def _write_json(records: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de la red de transporte.

    Igual que otras cargas de referencia de este proyecto, esto NO escribe
    en la capa Bronze particionada ni deja nada programado: escribe un
    único fichero de muestra pequeño y fijo (como mucho
    `config.routes_per_mode` líneas por cada modo de `config.modes`),
    pensado para commitearse como fixture. Cada ZIP GTFS se descarga
    completo en memoria (ninguno de los modos por defecto supera 18 MB),
    pero nunca se escribe a disco ni se lee entero en el contexto de la
    sesión que genera este módulo.
    """
    ingested_at = now_madrid()
    records: list[dict] = []
    for mode in config.modes:
        mode_records = fetch_and_normalize_mode(config, mode, ingested_at)
        logger.info("Modo %s: %d líneas de muestra normalizadas", mode, len(mode_records))
        records.extend(mode_records)

    _write_json(records, out_path)
    logger.info("Muestra escrita en %s (%d líneas en total)", out_path, len(records))
    return out_path


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Carga batch puntual de referencia de la red estructural de transporte "
            "de Madrid (GTFS, CRTM): líneas de metro/EMT/metro ligero/cercanías con "
            "las paradas de un viaje representativo. No admite ejecución en bucle "
            "ni programada: es una carga puntual invocada a mano, pensada para no "
            "repetirse salvo que CRTM publique un cambio de servicio relevante."
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
