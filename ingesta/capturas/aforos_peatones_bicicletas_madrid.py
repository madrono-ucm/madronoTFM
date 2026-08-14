"""Productor de datos abiertos de aforos de peatones y bicicletas de Madrid
(muestra puntual).

Descarga los conteos horarios de peatones y bicicletas de la red de
estaciones permanentes de aforo del Ayuntamiento de Madrid (tecnología de
visión artificial Data From Sky, ver `documents/Memoria_TFM FV.docx`,
apartado 6.1 «Contexto urbano») y los normaliza a un esquema mínimo y
consistente. Igual que `transporte_publico_madrid.py` (tarea 003),
`bicimad.py` (tarea 004), `aparcamientos_madrid.py` (tarea 005),
`calidad_aire_madrid.py` (tarea 006), `ruido_madrid.py` (tarea 007) y
`meteorologia_madrid.py` (tarea 008), esto es a propósito **solo una captura
puntual de muestra** — ver "Alcance reducido" en `ingesta/README.md`.

## Complementa a la tarea 012, sin su zona gris

A diferencia de `afluencia_lugares_madrid.py` (tarea 012, que estima
popularidad tipo Google para un lugar concreto vía una librería en zona
gris académica), esta fuente es un **dato oficial del Ayuntamiento, sin
ningún problema de condiciones de uso**: conteos reales de peatones y
bicicletas en puntos y calles fijas de la ciudad, publicados como datos
abiertos con licencia CC BY 4.0.

## Fuente elegida y por qué

Dataset "Aforos de peatones y bicicletas" (id
`300321-0-aforos-peatones-bicicletas`) de
[datos.madrid.es](https://datos.madrid.es/dataset/300321-0-aforos-peatones-bicicletas),
publicado por la Dirección General de Planificación e Infraestructuras de
Movilidad. Es el único dataset del portal con esta granularidad concreta
(conteo horario por punto fijo, desde el 1 de septiembre de 2019), tal como
sugería el objetivo de la tarea; el propio dataset enlaza otros dos
("Aforos de tráfico... no permanentes/permanentes") que miden intensidad de
**vehículos**, no de peatones/bicicletas, y quedan fuera del alcance de esta
captura.

### Formato real encontrado

El dataset publica, entre otros formatos (XLSX, PDF de estructura), **un CSV
independiente por año y por modo** (peatones / bicicletas): 6 CSV de
peatones (2019-2024) y 6 de bicicletas (2019-2024), verificado en vivo vía
la API CKAN del portal (`package_show`). Las notas internas del propio
dataset ("Los interlocutores envían la información trimestralmente... el
archivo a subir tiene que traer todo el acumulado anual") explican por qué
solo hay un recurso por año en vez de uno por trimestre: se recopila
trimestralmente pero se publica como un único CSV anual acumulado, que se
sustituye trimestre a trimestre.

A fecha de esta captura (2026-08-13), pese a que los metadatos del dataset
están marcados como modificados el 2026-07-24, **el recurso más reciente
sigue siendo el de 2024** (verificado en vivo: no existe ningún recurso 2025
ni 2026 en `package_show`), y ese propio CSV de 2024 solo cubre enero-junio
(datos hasta el 30/06/2024 inclusive) — el CSV es de por sí un histórico
acumulado ordenado cronológicamente ascendente que crece con cada trimestre
publicado, no un fichero cerrado de "el año completo". Se usa tal cual como
fuente por defecto (los dos recursos más recientes, uno por modo); si en una
ejecución futura ya hubiera un recurso más reciente, basta con apuntar
`MADRID_COUNTERS_PEDESTRIAN_URL`/`MADRID_COUNTERS_BICYCLE_URL` a la nueva
URL (mismo criterio que la nota equivalente en `callejero_madrid.py`,
tarea 009).

Cada CSV (~17 MB el de peatones, ~34 MB el de bicicletas para 2024) trae una
fila por estación y hora, con separador `;`, codificado en UTF-8 con BOM
(a diferencia del ISO-8859-1 de `ruido_madrid.py`/`callejero_madrid.py`), y
columnas: `fecha` (fecha+hora local, `DD/MM/YYYY H:MM`), `hora` (redundante:
repite el tramo horario de `fecha`, se descarta), `identificador`
(id de la estación, siempre idéntico a `device_id`, verificado en vivo
sobre el fichero completo — se conserva solo `identificador`), la columna de
conteo (`peatones` o `bicicletas` según el fichero), `Número_distrito` y
`distrito` (vacíos en algunas filas, p.ej. estaciones de pedanías como
Barajas), `direccion`, `observaciones_direccion`, y `latitude`/`longitude`
en el mismo formato "agrupado por puntos" que `ruido_madrid.py`
(p.ej. `"40.417.386"` -> `40.417386`), no un decimal simple.

Ninguno de los dos CSV ofrece un recurso más pequeño ni filtrado remoto
(mismo caso que `ruido_madrid.py`/`callejero_madrid.py`), así que hace falta
traer cada CSV completo a memoria para poder elegir la muestra; en ningún
momento se escribe el dataset completo en el disco de esta EC2, solo la
muestra final pequeña.

Se ha verificado en vivo desde este entorno que ambos recursos son
accesibles **sin ninguna autenticación ni API key**.

## Dos redes de estaciones distintas, no una sola con dos columnas

Peatones y bicicletas se miden en **redes de estaciones físicamente
distintas** (30 puntos permanentes de peatones, identificador `PERM_PEA##`;
53 de bicicletas, `PERM_BICI##`), en su mayoría ubicadas en calles
diferentes — no son el mismo punto midiendo dos magnitudes a la vez. Por
eso cada registro normalizado trae ambos campos `pedestrian_count` y
`bicycle_count` (tal como pedía el objetivo de la tarea: "peatones
contados, bicicletas contadas"), pero **solo uno de los dos está relleno
por registro** (`mode` indica cuál); forzar un cruce por ubicación/hora
para rellenar ambos a la vez habría inventado una relación que la fuente no
da. Ambos modos comparten el mismo esquema (mismo `schema_version`,
`source`, forma de `location`...), así que un consumidor puede tratarlos
como un único dataset y filtrar por `mode` si necesita solo uno.

TODO(kafka): cuando exista un broker Kafka desplegado (tarea 001), sustituir
o complementar la escritura del fixture en `capture_sample` por la
publicación de cada registro normalizado en un topic Kafka (p.ej.
`aforos-peatones-bicicletas-madrid`), manteniendo `normalize_record` como la
única fuente de verdad del esquema.

## Handler Lambda (tarea 027, lote 2/3): comprobación de recurso + captura si aplica

`lambda_handler` primero llama a `check_for_newer_resources`, que consulta
el catálogo CKAN del dataset y solo **avisa en los logs** (sin bloquear ni
cambiar nada) si ya existe un recurso CSV más reciente que el configurado
por defecto — este dataset se actualiza solo trimestralmente (ver "Formato
real encontrado" arriba), así que un handler programado puede pasar mucho
tiempo re-descargando el mismo último día ya capturado antes de que valga
la pena revisar si conviene actualizar `MADRID_COUNTERS_PEDESTRIAN_URL`/
`MADRID_COUNTERS_BICYCLE_URL`. La captura en sí ("si aplica") siempre
procede con la fuente configurada, vía `capture_all` (todas las estaciones
de ambos modos del último día disponible, sin el recorte
`sample_stations`/`sample_hours_per_station` de `capture_sample`).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from .bronze import BronzeWriter

logger = logging.getLogger(__name__)

# Dataset CKAN de origen (ver docstring del módulo, "Formato real
# encontrado"): se usa para comprobar en vivo si ha aparecido un recurso
# CSV más reciente que el configurado por defecto, ya que este dataset se
# actualiza solo trimestralmente (a diferencia del resto de productores del
# proyecto, cuyos recursos son fijos o de tiempo real).
CKAN_PACKAGE_SHOW_URL = "https://datos.madrid.es/api/action/package_show"
CKAN_DATASET_ID = "300321-0-aforos-peatones-bicicletas"

DEFAULT_PEDESTRIAN_URL = (
    "https://datos.madrid.es/dataset/300321-0-aforos-peatones-bicicletas/resource/"
    "300321-0-aforos-peatones-bicicletas-csv/download/300321-0-aforos-peatones-bicicletas-csv.csv"
)
DEFAULT_BICYCLE_URL = (
    "https://datos.madrid.es/dataset/300321-0-aforos-peatones-bicicletas/resource/"
    "300321-10-aforos-peatones-bicicletas-csv/download/300321-10-aforos-peatones-bicicletas-csv.csv"
)

SOURCE_NAME = "madrid_aforos_peatones_bicicletas"
DATASET_NAME = "aforos_peatones_bicicletas"
MODE_PEDESTRIAN = "peatones"
MODE_BICYCLE = "bicicletas"

DEFAULT_SAMPLE_PATH = (
    Path(__file__).parent / "samples" / "aforos_peatones_bicicletas_madrid_sample.json"
)
# Nº de estaciones distintas por modo (peatones/bicicletas) en la muestra, y
# nº máximo de horas del último día disponible que se toman de cada una:
# unas pocas estaciones x unas pocas horas (ver objetivo de la tarea), no el
# histórico completo desde 2019.
DEFAULT_SAMPLE_STATIONS = 3
DEFAULT_SAMPLE_HOURS_PER_STATION = 6

# Ambos CSV de este dataset se publican en UTF-8 con BOM, a diferencia del
# ISO-8859-1 de ruido_madrid.py/callejero_madrid.py (tareas 007/009).
SOURCE_ENCODING = "utf-8-sig"
# El feed publica `fecha` en hora local de Madrid, sin offset.
MADRID_TZ = ZoneInfo("Europe/Madrid")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la captura, leída de variables de entorno.

    No hay campos de credenciales: ambos recursos de datos.madrid.es usados
    aquí son públicos y no requieren API key.
    """

    pedestrian_url: str
    bicycle_url: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_stations: int
    sample_hours_per_station: int

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            pedestrian_url=os.environ.get("MADRID_COUNTERS_PEDESTRIAN_URL", DEFAULT_PEDESTRIAN_URL),
            bicycle_url=os.environ.get("MADRID_COUNTERS_BICYCLE_URL", DEFAULT_BICYCLE_URL),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 30.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_stations=_env_int("MADRID_COUNTERS_SAMPLE_STATIONS", DEFAULT_SAMPLE_STATIONS),
            sample_hours_per_station=_env_int(
                "MADRID_COUNTERS_SAMPLE_HOURS_PER_STATION", DEFAULT_SAMPLE_HOURS_PER_STATION
            ),
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


def fetch_raw_pedestrians(config: CaptureConfig) -> str:
    """Descarga el CSV completo de conteos horarios de peatones."""
    return _fetch_with_retries(config, config.pedestrian_url).decode(SOURCE_ENCODING)


def fetch_raw_bicycles(config: CaptureConfig) -> str:
    """Descarga el CSV completo de conteos horarios de bicicletas."""
    return _fetch_with_retries(config, config.bicycle_url).decode(SOURCE_ENCODING)


def _latest_csv_resource_url(resources: "list[dict]", keyword: str) -> Optional[str]:
    """Del catálogo CKAN, la URL del recurso CSV más reciente cuyo nombre contiene `keyword`."""
    candidates = [
        r
        for r in resources
        if (r.get("format") or "").upper() == "CSV" and keyword in (r.get("name") or "").lower()
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda r: r.get("last_modified") or r.get("created") or "", reverse=True)
    return candidates[0].get("url")


def check_for_newer_resources(config: CaptureConfig) -> None:
    """Avisa (log, sin fallar ni cambiar nada) si el catálogo CKAN ya tiene un recurso
    CSV más reciente que el configurado por defecto, para cada modo.

    Este dataset se actualiza solo trimestralmente (ver docstring del
    módulo), así que un handler Lambda programado (p.ej. semanal) puede
    pasar mucho tiempo re-descargando el mismo último día ya capturado
    antes. Esta comprobación no bloquea la captura real (que siempre usa
    `config.pedestrian_url`/`config.bicycle_url`, tal como los resolvió
    `CaptureConfig.from_env`): solo deja constancia en los logs de cuándo
    conviene actualizar esas variables de entorno a una URL más reciente,
    ya que este código no cambia la fuente configurada por su cuenta.
    """
    try:
        response = requests.get(
            CKAN_PACKAGE_SHOW_URL,
            params={"id": CKAN_DATASET_ID},
            timeout=config.timeout_seconds,
        )
        response.raise_for_status()
        resources = (response.json().get("result") or {}).get("resources") or []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("No se pudo comprobar el catálogo CKAN de aforos: %s", exc)
        return

    latest_pedestrian = _latest_csv_resource_url(resources, "peatones")
    if latest_pedestrian and latest_pedestrian != config.pedestrian_url:
        logger.warning(
            "Hay un recurso de peatones más reciente que el configurado: %s (actual: %s)",
            latest_pedestrian,
            config.pedestrian_url,
        )
    latest_bicycle = _latest_csv_resource_url(resources, "bicicletas")
    if latest_bicycle and latest_bicycle != config.bicycle_url:
        logger.warning(
            "Hay un recurso de bicicletas más reciente que el configurado: %s (actual: %s)",
            latest_bicycle,
            config.bicycle_url,
        )


def _clean(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _to_int(raw: Optional[str]) -> Optional[int]:
    value = _clean(raw)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_grouped_decimal(raw: Optional[str]) -> Optional[float]:
    """Convierte latitud/longitud tal como las publica esta fuente.

    El CSV las exporta con puntos de más como separador de agrupación (p.ej.
    `"40.417.386"` en vez de `40.417386`, o `"-3.707.141"` en vez de
    `-3.707141`, mismo formato que el catálogo de estaciones de
    `ruido_madrid.py`): el primer fragmento tras un signo opcional es la
    parte entera, y el resto de fragmentos separados por `.` son la parte
    decimal concatenada.
    """
    value = _clean(raw)
    if value is None:
        return None
    parts = value.split(".")
    if len(parts) <= 1:
        try:
            return float(value)
        except ValueError:
            return None
    integer_part, fraction_parts = parts[0], parts[1:]
    try:
        return float(f"{integer_part}.{''.join(fraction_parts)}")
    except ValueError:
        return None


def _parse_measured_at(raw: Optional[str]) -> Optional[datetime]:
    """Parsea `fecha` ('DD/MM/YYYY H:MM', hora local de Madrid, sin offset)."""
    value = _clean(raw)
    if value is None:
        return None
    try:
        naive = datetime.strptime(value, "%d/%m/%Y %H:%M")
        return naive.replace(tzinfo=MADRID_TZ)
    except ValueError:
        logger.warning("No se pudo parsear fecha=%r", raw)
        return None


def _date_sort_key(raw_fecha: str) -> Optional[tuple]:
    """De 'DD/MM/YYYY H:MM' extrae (YYYY, MM, DD) como clave ordenable."""
    date_part = raw_fecha.split(" ")[0]
    try:
        day, month, year = date_part.split("/")
        return (year, month, day)
    except ValueError:
        return None


def parse_latest_day_rows(csv_text: str) -> list[dict]:
    """Parsea el CSV completo y devuelve solo las filas del último día presente.

    A diferencia del CSV diario de `ruido_madrid.py` (ordenado
    cronológicamente de forma global), este fichero está agrupado **por
    estación** (todo el histórico de una estación seguido, luego el de la
    siguiente): las filas del último día no forman un único tramo contiguo
    al final del fichero, sino un tramo final distinto dentro de cada bloque
    de estación. Por eso hace falta un primer recorrido para determinar cuál
    es la fecha máxima real de todo el fichero, y un segundo filtrado por esa
    fecha — no basta con "cortar" al cambiar de fecha como en
    `parse_latest_day_entries`. Se verificó en vivo que las 30
    estaciones/53 estaciones de esta fuente comparten la misma última fecha,
    así que el resultado sigue siendo "el último día, todas las estaciones".
    """
    rows = list(csv.DictReader(csv_text.splitlines(), delimiter=";"))
    keyed_rows = [(_date_sort_key(row.get("fecha") or ""), row) for row in rows]
    valid_keys = [key for key, _ in keyed_rows if key is not None]
    if not valid_keys:
        return []
    latest_key = max(valid_keys)
    return [row for key, row in keyed_rows if key == latest_key]


def select_sample_rows(rows: list[dict], max_stations: int, max_hours_per_station: int) -> list[dict]:
    """Se queda con las primeras `max_stations` estaciones (por orden de aparición)
    y, de cada una, sus primeras `max_hours_per_station` filas (horas) del día."""
    counts: dict[str, int] = {}
    selected_stations: list[str] = []
    selected: list[dict] = []
    for row in rows:
        station_id = _clean(row.get("identificador"))
        if station_id is None:
            continue
        if station_id not in counts:
            if len(selected_stations) >= max_stations:
                continue
            selected_stations.append(station_id)
            counts[station_id] = 0
        if counts[station_id] >= max_hours_per_station:
            continue
        counts[station_id] += 1
        selected.append(row)
    return selected


def normalize_record(row: dict, mode: str, ingested_at: datetime) -> dict:
    """Normaliza una fila estación+hora al esquema mínimo, para el `mode` dado
    (`MODE_PEDESTRIAN` o `MODE_BICYCLE`)."""
    measured_at = _parse_measured_at(row.get("fecha"))
    count = _to_int(row.get(mode))

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "station_id": _clean(row.get("identificador")),
        "mode": mode,
        "measured_at": measured_at.astimezone(timezone.utc).isoformat() if measured_at else None,
        "ingested_at": ingested_at.astimezone(timezone.utc).isoformat(),
        "pedestrian_count": count if mode == MODE_PEDESTRIAN else None,
        "bicycle_count": count if mode == MODE_BICYCLE else None,
        "district_code": _clean(row.get("Número_distrito")),
        "district": _clean(row.get("distrito")),
        "address": _clean(row.get("direccion")),
        "address_notes": _clean(row.get("observaciones_direccion")),
        "location": {
            "lat": _parse_grouped_decimal(row.get("latitude")),
            "lon": _parse_grouped_decimal(row.get("longitude")),
            "srid": "EPSG:4326",
        },
    }


def _write_json(records: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de aforos de peatones y
    bicicletas.

    Igual que en las tareas 003-008, esto NO escribe en la capa Bronze
    particionada: escribe una única muestra pequeña (como mucho
    `config.sample_stations` estaciones por modo, con hasta
    `config.sample_hours_per_station` horas cada una, del último día
    disponible en cada CSV de origen) en un fichero fijo, pensado para
    commitearse como fixture, no para acumular capturas.
    """
    ingested_at = datetime.now(timezone.utc)
    records: list[dict] = []

    pedestrian_csv = fetch_raw_pedestrians(config)
    pedestrian_rows = parse_latest_day_rows(pedestrian_csv)
    logger.info(
        "Filas de peatones descargadas del último día disponible: %d", len(pedestrian_rows)
    )
    pedestrian_sample = select_sample_rows(
        pedestrian_rows, config.sample_stations, config.sample_hours_per_station
    )
    records.extend(normalize_record(row, MODE_PEDESTRIAN, ingested_at) for row in pedestrian_sample)

    bicycle_csv = fetch_raw_bicycles(config)
    bicycle_rows = parse_latest_day_rows(bicycle_csv)
    logger.info("Filas de bicicletas descargadas del último día disponible: %d", len(bicycle_rows))
    bicycle_sample = select_sample_rows(
        bicycle_rows, config.sample_stations, config.sample_hours_per_station
    )
    records.extend(normalize_record(row, MODE_BICYCLE, ingested_at) for row in bicycle_sample)

    logger.info("Muestra normalizada: %d registros (peatones + bicicletas)", len(records))

    _write_json(records, out_path)
    logger.info("Muestra escrita en %s", out_path)
    return out_path


def capture_all(config: CaptureConfig) -> "list[dict]":
    """Descarga y normaliza el último día disponible, TODAS las estaciones, ambos modos.

    A diferencia de `capture_sample` (que corta a `config.sample_stations` x
    `config.sample_hours_per_station`), esto es la captura completa pensada
    para el handler Lambda (tarea 027): las 30 estaciones de peatones y las
    53 de bicicletas, con todas las horas del último día disponible en cada
    CSV de origen.
    """
    ingested_at = datetime.now(timezone.utc)
    records: "list[dict]" = []

    pedestrian_csv = fetch_raw_pedestrians(config)
    pedestrian_rows = parse_latest_day_rows(pedestrian_csv)
    records.extend(normalize_record(row, MODE_PEDESTRIAN, ingested_at) for row in pedestrian_rows)

    bicycle_csv = fetch_raw_bicycles(config)
    bicycle_rows = parse_latest_day_rows(bicycle_csv)
    records.extend(normalize_record(row, MODE_BICYCLE, ingested_at) for row in bicycle_rows)

    logger.info("Normalizados %d registros de aforos (captura completa)", len(records))
    return records


def lambda_handler(event, context):
    """Punto de entrada AWS Lambda (tarea 027): comprobación de recurso + captura completa.

    Antes de capturar, avisa (sin bloquear) si el catálogo CKAN ya tiene un
    recurso más reciente que el configurado (ver `check_for_newer_resources`
    y el docstring del módulo, "Formato real encontrado"): este dataset solo
    se actualiza trimestralmente, así que vale la pena dejar constancia en
    los logs de cuándo conviene actualizar `MADRID_COUNTERS_PEDESTRIAN_URL`/
    `MADRID_COUNTERS_BICYCLE_URL`. La captura en sí ("si aplica") siempre
    procede con la fuente configurada.
    """
    config = CaptureConfig.from_env()
    check_for_newer_resources(config)
    records = capture_all(config)
    writer = BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=DATASET_NAME)
    out_path = writer.write_batch(records)
    logger.info("Captura Lambda completada: %s", out_path)
    return {"dataset": DATASET_NAME, "records_written": len(records), "location": str(out_path)}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Captura una muestra puntual de aforos de peatones y bicicletas de "
            "Madrid y la guarda como fixture pequeño. No admite ejecución en "
            "bucle ni programada: es siempre una única captura."
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
    out_path = capture_sample(config, args.out)
    logger.info("Captura completada: %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
