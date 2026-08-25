"""Carga batch puntual de incidencias y alteraciones del servicio de EMT
Madrid (muestra, referencia de un feed real en vivo).

Descarga el feed RSS de incidencias de la Empresa Municipal de Transportes
(EMT) de Madrid -- cortes de línea, paradas suprimidas, desvíos por obras,
manifestaciones, eventos deportivos... -- y lo normaliza a un esquema
mínimo. Complementa `transporte_publico_madrid.py` (tarea 003, paradas/
tiempos de espera de EMT): sin esto, una recomendación de
`opciones_movilidad` (tool pendiente) podría sugerir una línea que hoy no
pasa por una parada suprimida.

## A diferencia de otras fuentes de referencia de esta sesión: esto SÍ es un feed en vivo

Verificado en la propia captura de esta tarea: el feed trae 90 incidencias
activas, la más reciente con `pubDate` de hoy mismo. No es un dato de
referencia que cambie con poca frecuencia (como los parques o las calles
SER) -- es información operativa real que cambia varias veces al día. Aun
así, esta captura sigue el mismo patrón de "muestra puntual, sin bucle" que
el resto de productores de este proyecto sin infraestructura de scheduling
real detrás (ver `ingesta/README.md`, "Alcance reducido") -- un futuro
productor continuo debería programarse con la cadencia que merece un feed
en vivo (minutos, no hora en hora), no asumir que basta con añadir
`--interval-seconds` sin revisar la cadencia real de publicación.

## Fuente elegida y por qué

Dataset "EMT. Incidencias o alteraciones del servicio de EMT" (id
`202992-0`) de
[datos.madrid.es](https://datos.madrid.es/dataset/202992-0-emt-incidencias),
publicado por la propia EMT -- redistribuye "el Canal de Noticias de la
Empresa Municipal de Transportes de Madrid" como RSS 2.0. Cada `<item>`
trae, además de los campos RSS estándar (`title`, `description`, `pubDate`,
`link`), extensiones propias: `category` repetido una vez por línea
afectada, `rssAfectaDesde`/`rssAfectaHasta` (ventana de vigencia real de la
incidencia) y `GoogleTransitCause`/`GoogleTransitEffect` (clasificación
estandarizada del motivo/efecto, vocabulario tipo GTFS-RT: "08 - Obras",
"08 - Parada suprimida", etc.) -- se conservan tal cual en vez de
reinterpretarlos, son ya un vocabulario controlado útil para el asistente.

No requiere API key -- feed público, sin autenticación.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

import requests

from .bronze import MADRID_TZ, now_madrid

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_URL = (
    "https://datos.madrid.es/dataset/202992-0-emt-incidencias/resource/"
    "202992-0-emt-incidencias/download/202992-0-emt-incidencias.rss"
)

SOURCE_NAME = "madrid_emt_incidencias"

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "emt_incidencias_madrid_sample.json"
DEFAULT_SAMPLE_SIZE = 10

_REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; madrono-ingesta/1.0)"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la carga, leída de variables de entorno. Sin
    credenciales: el feed es público, sin API key."""

    source_url: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_size: int

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            source_url=os.environ.get("MADRID_EMT_INCIDENCIAS_URL", DEFAULT_SOURCE_URL),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 30.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_size=_env_int("MADRID_EMT_INCIDENCIAS_SAMPLE_SIZE", DEFAULT_SAMPLE_SIZE),
        )


def _fetch_with_retries(config: CaptureConfig, url: str) -> bytes:
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.get(url, headers=_REQUEST_HEADERS, timeout=config.timeout_seconds)
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


def fetch_raw_incidencias(config: CaptureConfig) -> bytes:
    """Descarga el feed RSS completo (todas las incidencias activas)."""
    return _fetch_with_retries(config, config.source_url)


def _clean(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _text(item: ET.Element, tag: str) -> Optional[str]:
    child = item.find(tag)
    if child is None or child.text is None:
        return None
    return _clean(child.text)


def _parse_rfc822(raw: Optional[str]) -> Optional[str]:
    """`pubDate` viene en formato RFC 822 (`Tue, 25 Aug 2026 14:46:47 GMT`);
    se normaliza a ISO 8601 en hora de Madrid. Devuelve `None` si no se
    puede parsear en vez de lanzar -- una incidencia sin fecha parseable
    sigue siendo información útil (título/líneas afectadas)."""
    value = _clean(raw)
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(MADRID_TZ).isoformat()


def select_sample_incidencias(incidencias_rss: bytes, sample_size: int) -> "list[ET.Element]":
    """Recorre el feed en orden (más reciente primero, orden nativo del RSS)
    y toma los primeros `sample_size` items."""
    root = ET.fromstring(incidencias_rss)
    items = root.findall(".//item")
    return items[:sample_size]


def normalize_record(item: ET.Element, ingested_at: datetime) -> dict:
    """Normaliza un `<item>` del feed al esquema mínimo de incidencias."""
    affected_lines = [_clean(c.text) for c in item.findall("category") if _clean(c.text)]

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "incident_id": _text(item, "guid"),
        "title": _text(item, "title"),
        "description": _text(item, "description"),
        "affected_lines": affected_lines,
        "cause": _text(item, "GoogleTransitCause"),
        "effect": _text(item, "GoogleTransitEffect"),
        "published_at": _parse_rfc822(_text(item, "pubDate")),
        "valid_from": _text(item, "rssAfectaDesde"),
        "valid_until": _text(item, "rssAfectaHasta"),
        "link": _text(item, "link"),
        "ingested_at": ingested_at.astimezone(MADRID_TZ).isoformat(),
    }


def _write_json(records: "list[dict]", out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de incidencias de EMT.

    Igual que el resto de cargas de este módulo: NO escribe en Bronze
    particionado ni deja nada programado -- un único fichero de muestra
    pequeño y fijo, pensado para commitearse como fixture (con la salvedad,
    documentada arriba, de que el feed en sí sí es en vivo -- la muestra
    commiteada es una foto fija de un momento concreto, no un dato
    permanente).
    """
    ingested_at = now_madrid()

    incidencias_rss = fetch_raw_incidencias(config)
    sample = select_sample_incidencias(incidencias_rss, config.sample_size)
    records = [normalize_record(item, ingested_at) for item in sample]
    logger.info("Incidencias de muestra seleccionadas: %d", len(records))

    _write_json(records, out_path)
    logger.info("Muestra escrita en %s", out_path)
    return out_path


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Carga batch puntual de referencia de incidencias del servicio de EMT "
            "Madrid y la guarda como fixture pequeño. No admite ejecución en bucle "
            "ni programada, aunque la fuente sí es un feed en vivo (ver docstring "
            "del módulo)."
        )
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_SAMPLE_PATH, help="Ruta del fichero de muestra a escribir")
    parser.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "INFO"), help="Nivel de logging")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = CaptureConfig.from_env()
    capture_sample(config, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
