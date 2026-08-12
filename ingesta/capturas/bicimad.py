"""Productor de datos abiertos de BiciMAD (bicicleta compartida, muestra puntual).

Descarga el estado en tiempo real de las estaciones de BiciMAD (bicis y
anclajes disponibles) y lo normaliza a un esquema mínimo y consistente. Igual
que `transporte_publico_madrid.py` (tarea 003), esto es a propósito **solo
una captura puntual de muestra** — ver "Alcance reducido" más abajo.

## Fuente elegida: feed público GBFS, sin autenticación

BiciMAD (operado por la EMT Madrid) publica un feed estándar **GBFS**
(General Bikeshare Feed Specification) — catalogado como dataset "Bicimad.
GBFS" tanto en https://datos.madrid.es como en https://datos.emtmadrid.es —
cuyo documento de descubrimiento está en:

    https://madrid.publicbikesystem.net/customer/gbfs/v2/gbfs.json

De ahí cuelgan, entre otros, `station_information` (metadatos fijos de cada
estación: id, nombre, lat/lon, capacidad) y `station_status` (estado variable:
bicis y anclajes disponibles, `last_reported`). A diferencia de la API
MobilityLabs usada en la tarea 003 (transporte público), **este feed GBFS no
requiere registro ni API key**: se ha verificado en vivo desde este entorno
que responde sin ninguna cabecera de autenticación (ver más abajo). GBFS es
el estándar de facto para sistemas de bicicleta/patinete compartidos en
todo el mundo, por lo que se prefirió sobre la alternativa de usar la API
MobilityLabs de BiciMAD (`openapi.emtmadrid.es/v1/transport/bicimad/stations/`),
que sí exige las mismas credenciales de cuenta verificada por email que
bloquearon la tarea 003.

TODO(kafka): igual que en `trafico_madrid.py` y `transporte_publico_madrid.py`,
cuando exista un broker Kafka (tarea 001), `normalize_record` es la única
fuente de verdad del esquema a reutilizar tanto para el fixture/Bronze como
para un topic Kafka.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_STATION_INFORMATION_URL = (
    "https://madrid.publicbikesystem.net/customer/gbfs/v2/es/station_information"
)
DEFAULT_STATION_STATUS_URL = (
    "https://madrid.publicbikesystem.net/customer/gbfs/v2/es/station_status"
)
SOURCE_NAME = "bicimad_gbfs"
DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "bicimad_sample.json"
DEFAULT_SAMPLE_SIZE = 5


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración del productor, leída de variables de entorno.

    No hay campos de credenciales: el feed GBFS de BiciMAD es público y no
    requiere API key (a diferencia de la API MobilityLabs usada en la tarea
    003 para transporte público).
    """

    station_information_url: str
    station_status_url: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_size: int

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            station_information_url=os.environ.get(
                "BICIMAD_STATION_INFORMATION_URL", DEFAULT_STATION_INFORMATION_URL
            ),
            station_status_url=os.environ.get(
                "BICIMAD_STATION_STATUS_URL", DEFAULT_STATION_STATUS_URL
            ),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 15.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_size=_env_int("BICIMAD_SAMPLE_SIZE", DEFAULT_SAMPLE_SIZE),
        )


def _fetch_gbfs_json(config: CaptureConfig, url: str) -> dict:
    """Descarga y parsea un feed GBFS (JSON), con reintentos simples y backoff lineal."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.get(url, timeout=config.timeout_seconds)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Fallo al descargar %s (intento %d/%d): %s",
                url,
                attempt,
                config.max_retries,
                exc,
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * attempt)
    raise RuntimeError(f"No se pudo descargar {url} tras {config.max_retries} intentos") from last_exc


def fetch_raw_station_information(config: CaptureConfig) -> dict:
    """Descarga el feed GBFS `station_information` (metadatos fijos de cada estación)."""
    return _fetch_gbfs_json(config, config.station_information_url)


def fetch_raw_station_status(config: CaptureConfig) -> dict:
    """Descarga el feed GBFS `station_status` (bicis/anclajes disponibles ahora mismo)."""
    return _fetch_gbfs_json(config, config.station_status_url)


def normalize_record(info: dict, status: Optional[dict], ingested_at: datetime) -> dict:
    """Normaliza una estación (uniendo `station_information` + `station_status`) al esquema mínimo."""
    status = status or {}
    last_reported = status.get("last_reported")
    measured_at = (
        datetime.fromtimestamp(last_reported, tz=timezone.utc).isoformat()
        if last_reported is not None
        else None
    )

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "station_id": str(info["station_id"]),
        "name": info.get("name"),
        "address": info.get("address"),
        "measured_at": measured_at,
        "ingested_at": ingested_at.astimezone(timezone.utc).isoformat(),
        "bikes_available": status.get("num_bikes_available"),
        "bikes_disabled": status.get("num_bikes_disabled"),
        "docks_available": status.get("num_docks_available"),
        "docks_disabled": status.get("num_docks_disabled"),
        "docks_total": info.get("capacity"),
        "status": status.get("status"),
        "is_renting": status.get("is_renting"),
        "is_returning": status.get("is_returning"),
        "is_installed": status.get("is_installed"),
        "location": {
            "lat": info.get("lat"),
            "lon": info.get("lon"),
            "srid": "EPSG:4326",
        },
    }


def parse_records(
    station_information_json: dict, station_status_json: dict, ingested_at: datetime
) -> Iterator[dict]:
    """Une los feeds `station_information`/`station_status` por `station_id` y normaliza.

    Recorre las estaciones en el orden en que las publica `station_information`
    (estable entre llamadas), cruzando cada una con su estado más reciente si
    existe; si una estación no tiene estado (raro, pero posible por
    desincronización entre feeds), se normaliza igualmente con los campos de
    estado a `None` en vez de descartarla.
    """
    stations_info = station_information_json.get("data", {}).get("stations", [])
    stations_status = station_status_json.get("data", {}).get("stations", [])
    status_by_id = {str(s["station_id"]): s for s in stations_status}

    for info in stations_info:
        status = status_by_id.get(str(info["station_id"]))
        yield normalize_record(info, status, ingested_at)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de estaciones de BiciMAD.

    Igual que `transporte_publico_madrid.capture_sample`, esto NO escribe en
    la capa Bronze particionada: escribe una única muestra pequeña (como
    mucho `config.sample_size` estaciones, de las ~670 que tiene la red
    completa) en un fichero fijo, pensado para commitearse como fixture, no
    para acumular capturas.
    """
    ingested_at = datetime.now(timezone.utc)
    station_information_json = fetch_raw_station_information(config)
    station_status_json = fetch_raw_station_status(config)
    records = list(parse_records(station_information_json, station_status_json, ingested_at))[
        : config.sample_size
    ]
    logger.info("Descargadas %d estaciones de muestra de BiciMAD", len(records))

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
            "Captura una muestra puntual del estado de estaciones de BiciMAD "
            "(bicis y anclajes disponibles) y la guarda como fixture pequeño. "
            "No admite ejecución en bucle ni programada: es siempre una única captura."
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
