"""Productor de datos abiertos de calidad del aire de Madrid (muestra puntual).

Descarga las lecturas horarias en tiempo real de la red de estaciones de
control de contaminación del Ayuntamiento de Madrid y, para poder resolver
el nombre/ubicación de cada estación, el catálogo de estaciones, y los
normaliza a un esquema mínimo y consistente. Igual que
`transporte_publico_madrid.py` (tarea 003), `bicimad.py` (tarea 004) y
`aparcamientos_madrid.py` (tarea 005), esto es a propósito **solo una
captura puntual de muestra** — ver "Alcance reducido" en `ingesta/README.md`.

## Fuente elegida y por qué

Dataset "Calidad del aire. Datos en tiempo real" (id `212531-0-calidad-aire-tiempo-real`)
de [datos.madrid.es](https://datos.madrid.es/egob/catalogo/212531-0-calidad-aire-tiempo-real):
lecturas horarias (actualizadas cada 20 minutos, en los minutos 15/35/55) de
las 24 estaciones fijas de la red de vigilancia de calidad del aire del
Ayuntamiento. A diferencia del XML de tráfico (tarea 002), aquí se eligió el
recurso **JSON** del dataset (también hay TXT/CSV/XML disponibles, mismo
contenido) por ser el más simple de parsear sin dependencias extra.

Formato real encontrado (confirmado descargando el recurso en vivo desde
este entorno y contrastado con el PDF "Intérprete de ficheros de calidad del
aire" que publica el propio dataset): **no** es una lista plana de lecturas,
sino un registro por combinación estación+magnitud+día, con las 24 lecturas
horarias de ese día ya embebidas en columnas `H01`..`H24` (cada una con su
código de validación `V01`..`V24`, `"V"` = válido, `"N"` = no válido/sin
dato). El campo `PUNTO_MUESTREO` (p.ej. `"28079011_12_8"`) codifica estación
(`28079011`) + magnitud (`12`) + técnica de muestreo (`8`). El campo
`MAGNITUD` da el código de magnitud sin ceros a la izquierda (p.ej. `"1"`
para SO2, código real `"01"`); esta captura lo normaliza con `zfill(2)`
contra la tabla de magnitudes del Anexo II del PDF.

El JSON de tiempo real **no incluye nombre, dirección ni coordenadas de la
estación** (solo su código), así que esta captura hace una segunda descarga
al dataset "Calidad del aire. Estaciones de control" (id
`212629-0-estaciones-control-aire`), un CSV con esos metadatos por estación
(mismo patrón de dos fuentes combinadas que `aparcamientos_madrid.py`
combinando `GetListParking` + `GetDetailParking`, o `bicimad.py` combinando
`station_information` + `station_status`).

Se verificó en vivo desde este entorno que ambos recursos son accesibles
**sin ninguna autenticación ni API key**.

TODO(kafka): igual que en los productores anteriores, cuando exista un
broker Kafka (tarea 001), `normalize_record` es la única fuente de verdad
del esquema a reutilizar tanto para el fixture/Bronze como para un topic
Kafka.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

DEFAULT_REALTIME_URL = (
    "https://datos.madrid.es/dataset/212531-0-calidad-aire-tiempo-real/resource/"
    "212531-0-calidad-aire-tiempo-real/download/212531-0-calidad-aire-tiempo-real.json"
)
DEFAULT_STATIONS_URL = (
    "https://datos.madrid.es/dataset/212629-0-estaciones-control-aire/resource/"
    "212629-0-estaciones-control-aire-csv/download/212629-0-estaciones-control-aire-csv.csv"
)

SOURCE_NAME = "madrid_calidad_aire"
DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "calidad_aire_madrid_sample.json"
DEFAULT_SAMPLE_SIZE = 5

# Los datos horarios se publican en hora local de Madrid (ver Anexo/Notas del
# PDF "Intérprete de ficheros de calidad del aire").
MADRID_TZ = ZoneInfo("Europe/Madrid")

# Anexo II del PDF "Intérprete de ficheros de calidad del aire": código de
# magnitud -> (abreviatura, nombre, unidad). No se incluyen aquí todas las
# magnitudes del anexo, solo las que puede devolver el feed de tiempo real.
MAGNITUDES: dict[str, tuple[str, str, str]] = {
    "01": ("SO2", "Dióxido de Azufre", "µg/m³"),
    "06": ("CO", "Monóxido de Carbono", "mg/m³"),
    "07": ("NO", "Monóxido de Nitrógeno", "µg/m³"),
    "08": ("NO2", "Dióxido de Nitrógeno", "µg/m³"),
    "09": ("PM2.5", "Partículas < 2.5 µm", "µg/m³"),
    "10": ("PM10", "Partículas < 10 µm", "µg/m³"),
    "12": ("NOx", "Óxidos de Nitrógeno", "µg/m³"),
    "14": ("O3", "Ozono", "µg/m³"),
    "20": ("TOL", "Tolueno", "µg/m³"),
    "30": ("BEN", "Benceno", "µg/m³"),
    "35": ("EBE", "Etilbenceno", "µg/m³"),
    "37": ("MXY", "Metaxileno", "µg/m³"),
    "38": ("PXY", "Paraxileno", "µg/m³"),
    "39": ("OXY", "Ortoxileno", "µg/m³"),
    "42": ("TCH", "Hidrocarburos totales (hexano)", "mg/m³"),
    "43": ("CH4", "Metano", "mg/m³"),
    "44": ("NMHC", "Hidrocarburos no metánicos (hexano)", "mg/m³"),
    "431": ("MPX", "Metaparaxileno", "mg/m³"),
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
            realtime_url=os.environ.get("MADRID_AIR_QUALITY_REALTIME_URL", DEFAULT_REALTIME_URL),
            stations_url=os.environ.get("MADRID_AIR_QUALITY_STATIONS_URL", DEFAULT_STATIONS_URL),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 15.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_size=_env_int("MADRID_AIR_QUALITY_SAMPLE_SIZE", DEFAULT_SAMPLE_SIZE),
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
    """Descarga el CSV del catálogo de estaciones de control."""
    return _fetch_with_retries(config, config.stations_url).decode("utf-8-sig")


def _to_float(raw: Optional[str]) -> Optional[float]:
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_stations(csv_text: str) -> dict[str, dict]:
    """Parsea el CSV de estaciones de control a un diccionario por código de estación."""
    reader = csv.DictReader(csv_text.splitlines(), delimiter=";")
    stations: dict[str, dict] = {}
    for row in reader:
        code = (row.get("CODIGO") or "").strip()
        if not code:
            continue
        stations[code] = {
            "name": (row.get("ESTACION") or "").strip() or None,
            "address": (row.get("DIRECCION") or "").strip() or None,
            "lat": _to_float(row.get("LATITUD")),
            "lon": _to_float(row.get("LONGITUD")),
        }
    return stations


def parse_realtime_entries(json_text: str) -> list[dict]:
    """Parsea el JSON crudo de tiempo real a su lista de registros (uno por estación+magnitud)."""
    data = json.loads(json_text)
    return data.get("records", [])


def _latest_valid_hour(entry: dict) -> Optional[tuple[int, str]]:
    """Busca la lectura horaria válida más reciente del día (`H24` hacia `H01`)."""
    for hour in range(24, 0, -1):
        if entry.get(f"V{hour:02d}") == "V":
            return hour, entry.get(f"H{hour:02d}")
    return None


def _measured_at(entry: dict, hour: int) -> datetime:
    """`H01` = 1h tras medianoche, ..., `H24` = medianoche del día siguiente (ver PDF, Notas)."""
    base = datetime(int(entry["ANO"]), int(entry["MES"]), int(entry["DIA"]), tzinfo=MADRID_TZ)
    return base + timedelta(hours=hour)


def normalize_record(entry: dict, stations: dict[str, dict], ingested_at: datetime) -> Optional[dict]:
    """Normaliza un registro estación+magnitud+día al esquema mínimo, usando su lectura horaria
    válida más reciente. Devuelve `None` si el registro no tiene ninguna lectura válida ese día.
    """
    latest = _latest_valid_hour(entry)
    if latest is None:
        return None
    hour, raw_value = latest

    station_id = (entry.get("PUNTO_MUESTREO") or "").split("_")[0] or None
    station_info = stations.get(station_id, {}) if station_id else {}

    magnitude_code = (entry.get("MAGNITUD") or "").zfill(2)
    magnitude_info = MAGNITUDES.get(magnitude_code)

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "station_id": station_id,
        "station_name": station_info.get("name"),
        "station_address": station_info.get("address"),
        "magnitude_code": magnitude_code,
        "magnitude_abbr": magnitude_info[0] if magnitude_info else None,
        "magnitude_name": magnitude_info[1] if magnitude_info else None,
        "unit": magnitude_info[2] if magnitude_info else None,
        "value": _to_float(raw_value),
        "measured_at": _measured_at(entry, hour).astimezone(timezone.utc).isoformat(),
        "ingested_at": ingested_at.astimezone(timezone.utc).isoformat(),
        "location": {
            "lat": station_info.get("lat"),
            "lon": station_info.get("lon"),
            "srid": "EPSG:4326",
        },
    }


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de lecturas de calidad del aire.

    Igual que `transporte_publico_madrid.capture_sample`, `bicimad.capture_sample` y
    `aparcamientos_madrid.capture_sample`, esto NO escribe en la capa Bronze particionada:
    escribe una única muestra pequeña (como mucho `config.sample_size` lecturas, en el
    orden en que las devuelve la fuente) en un fichero fijo, pensado para commitearse
    como fixture, no para acumular capturas.
    """
    ingested_at = datetime.now(timezone.utc)

    stations_csv = fetch_raw_stations(config)
    stations = parse_stations(stations_csv)
    logger.info("Catálogo de estaciones descargado: %d estaciones", len(stations))

    realtime_json = fetch_raw_realtime(config)
    entries = parse_realtime_entries(realtime_json)
    logger.info("Lecturas de tiempo real descargadas: %d registros estación+magnitud", len(entries))

    records = []
    for entry in entries:
        record = normalize_record(entry, stations, ingested_at)
        if record is not None:
            records.append(record)
        if len(records) >= config.sample_size:
            break

    logger.info("Muestra normalizada: %d lecturas de calidad del aire", len(records))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)

    logger.info("Muestra escrita en %s", out_path)
    return out_path


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Captura una muestra puntual de lecturas de calidad del aire de Madrid "
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
