"""Productor de datos meteorológicos de Madrid (muestra puntual).

Descarga las lecturas horarias en tiempo real de la red de estaciones
meteorológicas del Ayuntamiento de Madrid y, para poder resolver
nombre/ubicación de cada estación, el catálogo de estaciones, y los
normaliza a un esquema mínimo y consistente. Igual que
`transporte_publico_madrid.py` (tarea 003), `bicimad.py` (tarea 004),
`aparcamientos_madrid.py` (tarea 005), `calidad_aire_madrid.py` (tarea 006)
y `ruido_madrid.py` (tarea 007), esto es a propósito **solo una captura
puntual de muestra** — ver "Alcance reducido" en `ingesta/README.md`.

## Fuente elegida y por qué

Dataset "Datos meteorológicos. Datos en tiempo real" (id
`300392-0-meteorologia-tiempo-real`) de
[datos.madrid.es](https://datos.madrid.es/dataset/300392-0-meteorologia-tiempo-real):
lecturas horarias (actualizadas cada 20 minutos, en los minutos 15/35/55) de
la red de ~25 estaciones meteorológicas fijas del Ayuntamiento. Se
descartó AEMET OpenData (alternativa sugerida en el objetivo de la tarea):
requiere una API key gratuita con registro, y esta fuente municipal ya
cubre el objetivo (temperatura, humedad, viento, precipitación...) sin
necesidad de credenciales.

Igual que `calidad_aire_madrid.py`, este dataset usa el mismo backend
"bdca" (Servicio de Calidad del Aire) que calidad del aire: **no** es una
lista plana de lecturas, sino un registro por combinación
estación+magnitud+día, con las 24 lecturas horarias de ese día ya
embebidas en columnas `H01`..`H24` (cada una con su código de validación
`V01`..`V24`; `"V"` = válido, `"N"` = no válido/sin dato). A diferencia del
JSON de calidad del aire, aquí **no** hay campo `PUNTO_MUESTREO`: el
código de estación es directamente el campo `ESTACION` (p.ej. `"102"`),
que coincide con la columna `CÓDIGO_CORTO` del catálogo de estaciones (ver
más abajo), así que no hace falta reconstruirlo.

Se eligió el recurso **JSON** (también hay TXT/CSV/XML con el mismo
contenido, documentados en el mismo PDF "Intérprete de ficheros de datos
meteorológicos horarios – diarios y tiempo real" que publica el propio
dataset) por ser el más simple de parsear sin dependencias extra.

Códigos de magnitud (Anexo II del PDF): `80` radiación ultravioleta
(Mw/m2), `81` velocidad de viento (m/s), `82` dirección de viento (sin
unidad según el PDF — se asume grados, convención estándar meteorológica),
`83` temperatura (ºC), `86` humedad relativa (%), `87` presión barométrica
(mb), `88` radiación solar (W/m2), `89` precipitación (l/m2). No todas las
estaciones miden todas las magnitudes (el catálogo marca con `X` cuáles).

El JSON de tiempo real no incluye nombre, dirección ni coordenadas de la
estación (solo su código corto), así que esta captura hace una segunda
descarga al dataset "Datos meteorológicos. Estaciones de control" (id
`300360-0-meteorologicos-estaciones`), un CSV con esos metadatos por
estación — mismo patrón de dos fuentes combinadas que
`calidad_aire_madrid.py`, `ruido_madrid.py`, `aparcamientos_madrid.py` y
`bicimad.py`. Ese catálogo ya publica `LONGITUD`/`LATITUD` en WGS84
decimal con punto (no hace falta ninguna corrección de formato, a
diferencia del catálogo de ruido de la tarea 007).

Se verificó en vivo desde este entorno que ambos recursos son accesibles
**sin ninguna autenticación ni API key**.

Cada registro normalizado agrega, para una estación y un instante, todas
las magnitudes que reporta esa estación en un único registro (temperatura,
humedad, viento, presión, radiación, precipitación como columnas), en vez
de un registro por magnitud como en `calidad_aire_madrid.py` — el objetivo
de la tarea pide explícitamente un esquema con "temperatura, humedad,
viento, precipitación" como campos de un mismo registro. `measured_at` es
la hora válida más reciente entre todas las magnitudes de esa estación (en
la práctica, una misma estación actualiza todas sus magnitudes a la vez).

TODO(kafka): igual que en los productores anteriores, cuando exista un
broker Kafka (tarea 001), `normalize_station_record` es la única fuente de
verdad del esquema a reutilizar tanto para el fixture/Bronze como para un
topic Kafka.

## Handler Lambda (tarea 027, lote 2/3)

`lambda_handler`/`capture_all` implementan el productor programado: la
captura completa (todas las estaciones, sin el recorte `sample_size` de
`capture_sample`) escrita en Bronze real vía `BronzeWriter`, mismo patrón
que los 5 productores del lote 1 (tarea 026).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from .bronze import BronzeWriter, now_madrid

logger = logging.getLogger(__name__)

DEFAULT_REALTIME_URL = (
    "https://datos.madrid.es/dataset/300392-0-meteorologia-tiempo-real/resource/"
    "300392-5-meteorologia-tiempo-real/download/300392-5-meteorologia-tiempo-real.json"
)
DEFAULT_STATIONS_URL = (
    "https://datos.madrid.es/dataset/300360-0-meteorologicos-estaciones/resource/"
    "300360-1-meteorologicos-estaciones-csv/download/300360-1-meteorologicos-estaciones-csv.csv"
)

SOURCE_NAME = "madrid_meteorologia"
DATASET_NAME = "meteorologia"
DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "meteorologia_madrid_sample.json"
DEFAULT_SAMPLE_SIZE = 5

# Los datos horarios se publican en hora local de Madrid (mismo backend y
# mismo criterio que `calidad_aire_madrid.py`).
MADRID_TZ = ZoneInfo("Europe/Madrid")

# Anexo II del PDF "Intérprete de ficheros de datos meteorológicos
# horarios – diarios y tiempo real": código de magnitud -> campo normalizado.
MAGNITUDES: dict[str, str] = {
    "80": "uv_radiation_mwm2",
    "81": "wind_speed_ms",
    "82": "wind_direction_deg",
    "83": "temperature_c",
    "86": "humidity_pct",
    "87": "pressure_mb",
    "88": "solar_radiation_wm2",
    "89": "precipitation_lm2",
}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración del productor, leída de variables de entorno.

    No hay campos de credenciales: ambos recursos de datos.madrid.es usados
    aquí son públicos y no requieren API key.
    """

    realtime_url: str
    stations_url: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_size: int

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            realtime_url=os.environ.get("MADRID_WEATHER_REALTIME_URL", DEFAULT_REALTIME_URL),
            stations_url=os.environ.get("MADRID_WEATHER_STATIONS_URL", DEFAULT_STATIONS_URL),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 15.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_size=_env_int("MADRID_WEATHER_SAMPLE_SIZE", DEFAULT_SAMPLE_SIZE),
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


def fetch_raw_realtime(config: CaptureConfig) -> str:
    """Descarga el JSON de lecturas horarias en tiempo real."""
    return _fetch_with_retries(config, config.realtime_url).decode("utf-8-sig")


def fetch_raw_stations(config: CaptureConfig) -> str:
    """Descarga el CSV del catálogo de estaciones meteorológicas."""
    return _fetch_with_retries(config, config.stations_url).decode("utf-8-sig")


def _to_float(raw: Optional[str]) -> Optional[float]:
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _to_int(raw: Optional[str]) -> Optional[int]:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def parse_stations(csv_text: str) -> dict[str, dict]:
    """Parsea el CSV de estaciones a un diccionario por código corto de estación.

    El código corto (`CÓDIGO_CORTO`, p.ej. `"102"`) es el que usa el feed de
    tiempo real en su campo `ESTACION`; `CÓDIGO` es el código completo
    (p.ej. `"28079102"`) que se usa como `station_id` en el esquema
    normalizado, igual que en `calidad_aire_madrid.py`.
    """
    reader = csv.DictReader(csv_text.splitlines(), delimiter=";")
    stations: dict[str, dict] = {}
    for row in reader:
        short_code = (row.get("CÓDIGO_CORTO") or "").strip()
        if not short_code:
            continue
        stations[short_code] = {
            "code": (row.get("CÓDIGO") or "").strip() or None,
            "name": (row.get("ESTACION") or "").strip() or None,
            "address": (row.get("DIRECCION") or "").strip() or None,
            "lat": _to_float(row.get("LATITUD")),
            "lon": _to_float(row.get("LONGITUD")),
            "altitude_m": _to_int(row.get("ALTITUD")),
        }
    return stations


def parse_realtime_entries(json_text: str) -> list[dict]:
    """Parsea el JSON crudo de tiempo real a su lista de registros (uno por estación+magnitud)."""
    data = json.loads(json_text)
    return data.get("records", [])


def group_by_station(entries: list[dict]) -> dict[str, list[dict]]:
    """Agrupa los registros estación+magnitud+día por código corto de estación,
    conservando el orden de aparición en la fuente."""
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        code = (entry.get("ESTACION") or "").strip()
        if not code:
            continue
        groups.setdefault(code, []).append(entry)
    return groups


def _latest_valid_hour(entry: dict) -> Optional[tuple[int, str]]:
    """Busca la lectura horaria válida más reciente del día (`H24` hacia `H01`)."""
    for hour in range(24, 0, -1):
        if entry.get(f"V{hour:02d}") == "V":
            return hour, entry.get(f"H{hour:02d}")
    return None


def _measured_at(entry: dict, hour: int) -> datetime:
    """`H01` = 1h tras medianoche, ..., `H24` = medianoche del día siguiente."""
    base = datetime(int(entry["ANO"]), int(entry["MES"]), int(entry["DIA"]), tzinfo=MADRID_TZ)
    return base + timedelta(hours=hour)


def normalize_station_record(
    station_code: str, entries: list[dict], stations: dict[str, dict], ingested_at: datetime
) -> Optional[dict]:
    """Normaliza los registros de una estación (uno por magnitud) a un único registro.

    Cada magnitud se resuelve a su lectura horaria válida más reciente,
    igual que en `calidad_aire_madrid.py`. Devuelve `None` si ninguna
    magnitud de la estación tiene ninguna lectura válida ese día. Códigos
    de magnitud no reconocidos (fuera de `MAGNITUDES`) se ignoran sin hacer
    fallar la captura.
    """
    values: dict[str, float] = {}
    freshest: Optional[tuple[int, dict]] = None
    for entry in entries:
        latest = _latest_valid_hour(entry)
        if latest is None:
            continue
        hour, raw_value = latest
        field_key = MAGNITUDES.get(entry.get("MAGNITUD"))
        if field_key is None:
            continue
        values[field_key] = _to_float(raw_value)
        if freshest is None or hour > freshest[0]:
            freshest = (hour, entry)

    if freshest is None:
        return None
    hour, ref_entry = freshest

    station_info = stations.get(station_code, {})
    station_id = station_info.get("code") or (
        f"{ref_entry.get('PROVINCIA', '')}{ref_entry.get('MUNICIPIO', '')}{int(station_code):03d}"
    )

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "station_id": station_id,
        "station_name": station_info.get("name"),
        "station_address": station_info.get("address"),
        "measured_at": _measured_at(ref_entry, hour).astimezone(MADRID_TZ).isoformat(),
        "ingested_at": ingested_at.astimezone(MADRID_TZ).isoformat(),
        "temperature_c": values.get("temperature_c"),
        "humidity_pct": values.get("humidity_pct"),
        "wind_speed_ms": values.get("wind_speed_ms"),
        "wind_direction_deg": values.get("wind_direction_deg"),
        "pressure_mb": values.get("pressure_mb"),
        "solar_radiation_wm2": values.get("solar_radiation_wm2"),
        "uv_radiation_mwm2": values.get("uv_radiation_mwm2"),
        "precipitation_lm2": values.get("precipitation_lm2"),
        "location": {
            "lat": station_info.get("lat"),
            "lon": station_info.get("lon"),
            "srid": "EPSG:4326",
            "altitude_m": station_info.get("altitude_m"),
        },
    }


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de lecturas meteorológicas.

    Igual que en las tareas 003-007, esto NO escribe en la capa Bronze
    particionada: escribe una única muestra pequeña (como mucho
    `config.sample_size` estaciones, una por registro, en el orden en que
    las devuelve la fuente) en un fichero fijo, pensado para commitearse
    como fixture, no para acumular capturas.
    """
    ingested_at = now_madrid()

    stations_csv = fetch_raw_stations(config)
    stations = parse_stations(stations_csv)
    logger.info("Catálogo de estaciones descargado: %d estaciones", len(stations))

    realtime_json = fetch_raw_realtime(config)
    entries = parse_realtime_entries(realtime_json)
    groups = group_by_station(entries)
    logger.info(
        "Lecturas de tiempo real descargadas: %d registros de %d estaciones",
        len(entries),
        len(groups),
    )

    records = []
    for station_code, station_entries in groups.items():
        if len(records) >= config.sample_size:
            break
        record = normalize_station_record(station_code, station_entries, stations, ingested_at)
        if record is not None:
            records.append(record)

    logger.info("Muestra normalizada: %d estaciones meteorológicas", len(records))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)

    logger.info("Muestra escrita en %s", out_path)
    return out_path


def capture_all(config: CaptureConfig) -> "list[dict]":
    """Descarga y normaliza TODAS las estaciones meteorológicas (sin recorte de muestra).

    A diferencia de `capture_sample` (que corta a `config.sample_size`),
    esto es la captura completa pensada para el handler Lambda (tarea 027):
    las ~25 estaciones de la red completa.
    """
    ingested_at = now_madrid()

    stations_csv = fetch_raw_stations(config)
    stations = parse_stations(stations_csv)

    realtime_json = fetch_raw_realtime(config)
    entries = parse_realtime_entries(realtime_json)
    groups = group_by_station(entries)

    records = [
        record
        for record in (
            normalize_station_record(code, station_entries, stations, ingested_at)
            for code, station_entries in groups.items()
        )
        if record is not None
    ]
    logger.info("Normalizadas %d estaciones meteorológicas (captura completa)", len(records))
    return records


def lambda_handler(event, context):
    """Punto de entrada AWS Lambda (tarea 027): captura completa a Bronze real."""
    config = CaptureConfig.from_env()
    records = capture_all(config)
    writer = BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=DATASET_NAME)
    out_path = writer.write_batch(records)
    logger.info("Captura Lambda completada: %s", out_path)
    return {"dataset": DATASET_NAME, "records_written": len(records), "location": str(out_path)}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Captura una muestra puntual de datos meteorológicos de Madrid "
            "y la guarda como fixture pequeño. No admite ejecución en bucle ni "
            "programada: es siempre una única captura."
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
