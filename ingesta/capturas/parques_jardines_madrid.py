"""Carga batch puntual de parques y jardines municipales de Madrid (muestra, referencia).

Descarga el catálogo de "Principales parques y jardines municipales" del
Ayuntamiento de Madrid y lo normaliza a un esquema mínimo pensado para que
el asistente conversacional pueda recomendar un parque real (caso de uso
"quiero dar un paseo por el parque", discutido en la sesión de arquitectura
del 25/8 al diseñar `afluencia_estimada`, tarea 086/089) — `poi_madrid.py`
(tarea 011) cubre "Edificios y monumentos" únicamente, a propósito (ver su
docstring, "Una sola categoría elegida"), así que no había ningún `:Lugar`
de tipo parque en el grafo hasta esta tarea.

## Esto es una carga puntual de referencia, NO una captura periódica

Mismo criterio que `poi_madrid.py`/`barrios_distritos_madrid.py`: la lista
de parques y jardines municipales de Madrid no cambia minuto a minuto — es
un dato de referencia (aunque la fuente se declare de actualización
"diaria", es para altas/bajas/correcciones puntuales de fichas, no para
reflejar un estado que varía por sí solo). Este módulo, a propósito, no
tiene modo `--interval-seconds` ni bucle.

## Fuente elegida y por qué

Dataset "Principales parques y jardines municipales" (id `200761-0`) de
[datos.madrid.es](https://datos.madrid.es/dataset/200761-0-parques-jardines),
publicado por la Dirección General de Gestión del Agua y Zonas Verdes. Cubre
"los parques y zonas verdes más significativos de cada distrito cuya
conservación corresponde al Ayuntamiento de Madrid" (jardines históricos,
singulares, forestales, rosaledas y colecciones botánicas) — no todas las
zonas verdes de la ciudad (medianas, rotondas, jardines pequeños quedan
fuera, según la propia descripción del dataset), pero sí los parques con
entidad propia suficiente para ser un destino de "paseo" con nombre.

Mismo esquema XML `EntidadesYOrganismos` que usan otros catálogos del
Ayuntamiento (`<atributos><atributo nombre="...">`), verificado en vivo
contra el XML real (208 parques a fecha de esta captura): cada ficha trae
`NOMBRE`, `DESCRIPCION-ENTIDAD`, `HORARIO`, `TRANSPORTE`, `ACCESIBILIDAD`, y
un bloque `LOCALIZACION` anidado con dirección postal completa, distrito,
barrio y `LATITUD`/`LONGITUD` en WGS84 ya resueltas (sin necesidad de
reproyección, a diferencia de datasets que traen coordenadas UTM planas).
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
from defusedxml import ElementTree as ET

from .bronze import MADRID_TZ, BronzeWriter, now_madrid

logger = logging.getLogger(__name__)

# Prefijo de la capa Bronze para este dataset (ver `lambda_handler`).
DATASET_NAME = "parques_jardines"

DEFAULT_SOURCE_URL = (
    "https://datos.madrid.es/dataset/200761-0-parques-jardines/resource/"
    "200761-2-parques-jardines-xml/download/200761-2-parques-jardines-xml"
)

SOURCE_NAME = "madrid_parques_jardines"

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "parques_jardines_madrid_sample.json"
DEFAULT_SAMPLE_SIZE = 8

# El servidor de datos.madrid.es filtra peticiones sin User-Agent (mismo
# comportamiento que ya documentaron poi_madrid.py/ruido_madrid.py).
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
    credenciales: el recurso es público, sin API key."""

    source_url: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_size: int

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            source_url=os.environ.get("MADRID_PARQUES_SOURCE_URL", DEFAULT_SOURCE_URL),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 30.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_size=_env_int("MADRID_PARQUES_SAMPLE_SIZE", DEFAULT_SAMPLE_SIZE),
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


def fetch_raw_parques(config: CaptureConfig) -> bytes:
    """Descarga el XML completo del catálogo (todos los parques)."""
    return _fetch_with_retries(config, config.source_url)


def _clean(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _attr(atributos: Optional[ET.Element], name: str) -> Optional[str]:
    """Busca `<atributo nombre="NAME">` directo (no recursivo) dentro de `atributos`."""
    if atributos is None:
        return None
    for child in atributos.findall("atributo"):
        if child.get("nombre") == name:
            return _clean(child.text)
    return None


def _attr_element(atributos: Optional[ET.Element], name: str) -> Optional[ET.Element]:
    if atributos is None:
        return None
    for child in atributos.findall("atributo"):
        if child.get("nombre") == name:
            return child
    return None


def _to_float(raw: Optional[str]) -> Optional[float]:
    value = _clean(raw)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _iter_parques_con_coordenadas(parques_xml: bytes) -> "list[ET.Element]":
    """Todos los `<contenido>` del catálogo que traen LATITUD y LONGITUD.
    Se descartan los que no las traen por robustez (no debería ocurrir,
    mismo criterio que `poi_madrid.py`)."""
    root = ET.fromstring(parques_xml)
    parques: "list[ET.Element]" = []
    for contenido in root.findall(".//contenido"):
        atributos = contenido.find("atributos")
        localizacion = _attr_element(atributos, "LOCALIZACION")
        if localizacion is None:
            continue
        if not _attr(localizacion, "LATITUD") or not _attr(localizacion, "LONGITUD"):
            continue
        parques.append(contenido)
    return parques


def select_sample_parques(parques_xml: bytes, sample_size: int) -> "list[ET.Element]":
    """Los primeros `sample_size` parques con coordenadas conocidas."""
    return _iter_parques_con_coordenadas(parques_xml)[:sample_size]


def normalize_record(contenido: ET.Element, ingested_at: datetime) -> dict:
    """Normaliza un `<contenido>` del catálogo al esquema mínimo de parques."""
    atributos = contenido.find("atributos")
    localizacion = _attr_element(atributos, "LOCALIZACION")

    calle = " ".join(
        part
        for part in (
            _attr(localizacion, "CLASE-VIAL"),
            _attr(localizacion, "NOMBRE-VIA"),
            _attr(localizacion, "NUM"),
        )
        if part
    ) or None

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "park_id": _attr(atributos, "ID-ENTIDAD"),
        "name": _attr(atributos, "NOMBRE"),
        "park_type": _attr(atributos, "TIPO"),
        "description": _attr(atributos, "DESCRIPCION-ENTIDAD"),
        "schedule": _attr(atributos, "HORARIO"),
        "transport": _attr(atributos, "TRANSPORTE"),
        "accessibility": _attr(atributos, "ACCESIBILIDAD"),
        "address": calle,
        "postal_code": _attr(localizacion, "CODIGO-POSTAL"),
        "district": _attr(localizacion, "DISTRITO"),
        "neighbourhood": _attr(localizacion, "BARRIO"),
        "ingested_at": ingested_at.astimezone(MADRID_TZ).isoformat(),
        "location": {
            "lat": _to_float(_attr(localizacion, "LATITUD")),
            "lon": _to_float(_attr(localizacion, "LONGITUD")),
            "srid": "EPSG:4326",
        },
    }


def _write_json(records: "list[dict]", out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de parques.

    Igual que `poi_madrid.py`/`barrios_distritos_madrid.py`: NO escribe en
    Bronze particionado ni deja nada programado -- un único fichero de
    muestra pequeño y fijo, pensado para commitearse como fixture. El
    catálogo completo (208 parques a fecha de esta captura) se descarga en
    memoria porque la fuente no ofrece filtrado remoto, pero nunca se
    escribe a disco completo.
    """
    ingested_at = now_madrid()

    parques_xml = fetch_raw_parques(config)
    sample = select_sample_parques(parques_xml, config.sample_size)
    records = [normalize_record(contenido, ingested_at) for contenido in sample]
    logger.info("Parques de muestra seleccionados: %d", len(records))

    _write_json(records, out_path)
    logger.info("Muestra escrita en %s", out_path)
    return out_path


def capture_all(config: CaptureConfig) -> "list[dict]":
    """Descarga y normaliza TODOS los parques del catálogo (sin recorte de muestra).

    Pensado para el handler Lambda: es un dato de referencia (cambia poco),
    así que el schedule real de este productor debe ser de baja frecuencia
    (semanal), no horario -- ver docstring del módulo y `FIL_04`.
    """
    ingested_at = now_madrid()
    parques_xml = fetch_raw_parques(config)
    records = [
        normalize_record(contenido, ingested_at)
        for contenido in _iter_parques_con_coordenadas(parques_xml)
    ]
    logger.info("Parques capturados (captura completa): %d", len(records))
    return records


def lambda_handler(event, context):
    """Punto de entrada AWS Lambda (FIL_04): captura completa a Bronze real."""
    config = CaptureConfig.from_env()
    records = capture_all(config)
    writer = BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=DATASET_NAME)
    out_path = writer.write_batch(records)
    logger.info("Captura Lambda completada: %s", out_path)
    return {"dataset": DATASET_NAME, "records_written": len(records), "location": str(out_path)}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Carga batch puntual de referencia de parques y jardines municipales "
            "de Madrid y la guarda como fixture pequeño. No admite ejecución en "
            "bucle ni programada."
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
