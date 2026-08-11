"""Productor de datos abiertos de intensidad de tráfico de Madrid.

Descarga el XML de estado del tráfico en tiempo real que publica el
Ayuntamiento de Madrid (servicio Informo, parte del ecosistema de datos
abiertos de datos.madrid.es), lo normaliza a un esquema mínimo y consistente,
y lo aterriza como un lote JSON en la capa Bronze del lakehouse (en local por
ahora, ver `bronze.BronzeWriter`).

Fuente: https://informo.madrid.es/informo/tmadrid/pm.xml — sensores de
intensidad de tráfico ("puntos de medida") del Ayuntamiento de Madrid, datos
públicos sin necesidad de credenciales. Catálogo del dataset en
https://datos.madrid.es (búsqueda: "Tráfico. Intensidad y velocidad").

TODO(kafka): cuando exista un broker Kafka desplegado (ver infraestructura de
la tarea 001), sustituir o complementar `BronzeWriter.write_batch` en
`capture_once` por la publicación de cada registro normalizado en un topic
Kafka (p.ej. `trafico-madrid`), manteniendo `normalize_record` como la única
fuente de verdad del esquema para ambos destinos (Bronze y el topic).
"""

from __future__ import annotations

import argparse
import logging
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional
from zoneinfo import ZoneInfo

import requests

from .bronze import BronzeWriter

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_URL = "https://informo.madrid.es/informo/tmadrid/pm.xml"
DATASET_NAME = "trafico"
SOURCE_NAME = "madrid_trafico_intensidad"
# El feed de Informo publica su timestamp global en hora local de Madrid.
MADRID_TZ = ZoneInfo("Europe/Madrid")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración del productor, leída de variables de entorno.

    `bronze_base_path` es a propósito una ruta de disco local: todavía no hay
    infraestructura S3 aplicada (ver tarea 001), así que apunta por defecto a
    `./bronze`. El día que se aplique esa infraestructura, bastará con
    apuntar esta variable a un punto de montaje S3 (p.ej. vía s3fs/mountpoint-s3)
    sin tocar el código del productor.
    """

    source_url: str
    bronze_base_path: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            source_url=os.environ.get("MADRID_TRAFFIC_SOURCE_URL", DEFAULT_SOURCE_URL),
            bronze_base_path=os.environ.get("BRONZE_BASE_PATH", "./bronze"),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 15.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
        )


def fetch_raw_xml(config: CaptureConfig) -> str:
    """Descarga el XML de la fuente, con reintentos simples y backoff lineal."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.get(config.source_url, timeout=config.timeout_seconds)
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            return response.text
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Fallo al descargar %s (intento %d/%d): %s",
                config.source_url,
                attempt,
                config.max_retries,
                exc,
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * attempt)
    raise RuntimeError(
        f"No se pudo descargar {config.source_url} tras {config.max_retries} intentos"
    ) from last_exc


def _parse_fecha_hora(raw: str, fallback: datetime) -> datetime:
    """Parsea el timestamp global del feed ('DD/MM/YYYY H:MM:SS', hora de Madrid)."""
    try:
        naive = datetime.strptime(raw.strip(), "%d/%m/%Y %H:%M:%S")
        return naive.replace(tzinfo=MADRID_TZ)
    except (ValueError, AttributeError):
        logger.warning("No se pudo parsear fecha_hora=%r del feed, se usa la hora de descarga", raw)
        return fallback


def _parse_decimal_coma(raw: Optional[str]) -> Optional[float]:
    """El feed usa coma como separador decimal en st_x/st_y (p.ej. '438339,37...')."""
    if not raw:
        return None
    try:
        return float(raw.strip().replace(",", "."))
    except ValueError:
        return None


def _to_int(raw: Optional[str]) -> Optional[int]:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def normalize_record(pm: ET.Element, measured_at: datetime, ingested_at: datetime) -> dict:
    """Normaliza un elemento `<pm>` del feed al esquema mínimo del dataset `trafico`."""

    def text(tag: str) -> Optional[str]:
        el = pm.find(tag)
        if el is None or el.text is None:
            return None
        value = el.text.strip()
        return value or None

    error_code = text("error") or "N"

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "point_id": text("idelem"),
        "measured_at": measured_at.astimezone(timezone.utc).isoformat(),
        "ingested_at": ingested_at.astimezone(timezone.utc).isoformat(),
        "description": text("descripcion"),
        "access_code": text("accesoAsociado"),
        "subarea": text("subarea"),
        "intensity_vph": _to_int(text("intensidad")),
        "occupancy_pct": _to_int(text("ocupacion")),
        "load_pct": _to_int(text("carga")),
        "service_level": _to_int(text("nivelServicio")),
        "saturation_intensity_vph": _to_int(text("intensidadSat")),
        "has_error": error_code != "N",
        "error_code": error_code,
        "location": {
            "x": _parse_decimal_coma(text("st_x")),
            "y": _parse_decimal_coma(text("st_y")),
            "srid": "EPSG:25830",
        },
    }


def parse_records(xml_text: str, ingested_at: datetime) -> Iterator[dict]:
    """Parsea el XML crudo del feed y produce registros normalizados."""
    root = ET.fromstring(xml_text)
    fecha_hora = root.findtext("fecha_hora")
    measured_at = _parse_fecha_hora(fecha_hora, fallback=ingested_at) if fecha_hora else ingested_at

    for pm in root.findall("pm"):
        yield normalize_record(pm, measured_at, ingested_at)


def capture_once(config: CaptureConfig) -> Path:
    """Descarga, normaliza y aterriza en Bronze un lote de intensidad de tráfico."""
    ingested_at = datetime.now(timezone.utc)
    xml_text = fetch_raw_xml(config)
    records = list(parse_records(xml_text, ingested_at))
    logger.info("Descargados %d puntos de medida de tráfico", len(records))

    writer = BronzeWriter(config.bronze_base_path, dataset=DATASET_NAME)
    return writer.write_batch(records, moment=ingested_at)


def run_loop(config: CaptureConfig, interval_seconds: float) -> None:
    """Ejecuta `capture_once` indefinidamente, sin abortar el bucle ante fallos."""
    logger.info("Iniciando captura periódica cada %.0fs", interval_seconds)
    while True:
        try:
            capture_once(config)
        except Exception:
            logger.exception("Fallo capturando tráfico; se reintentará en el próximo ciclo")
        time.sleep(interval_seconds)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description="Captura datos abiertos de intensidad de tráfico de Madrid a la capa Bronze"
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=None,
        help="Si se indica, captura en bucle cada N segundos en vez de una sola vez",
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

    if args.interval_seconds:
        run_loop(config, args.interval_seconds)
    else:
        out_path = capture_once(config)
        logger.info("Captura completada: %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
