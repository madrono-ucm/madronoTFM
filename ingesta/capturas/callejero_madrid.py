"""Carga batch puntual del callejero y grafo viario de Madrid (muestra, referencia).

Descarga el callejero vigente del Ayuntamiento de Madrid (viales y sus cruces
con otros viales) y lo normaliza a un esquema mínimo y consistente pensado
para alimentar más adelante el grafo urbano en Neo4j (ver
`documents/Memoria_TFM FV.docx`, apartado 5.2).

## Esto es una carga puntual de referencia, NO una captura periódica

A diferencia de todas las capturas anteriores de `ingesta/capturas/`
(tráfico, transporte público, BiciMAD, aparcamientos, calidad del aire,
ruido, meteorología — datos que cambian minuto a minuto u hora a hora), el
callejero de Madrid es un dato de **referencia** que apenas cambia (el
propio dataset se actualiza "diariamente" solo para incorporar aprobaciones
puntuales de nuevos viales o cambios de numeración, no para reflejar un
estado que varía por sí solo). No tiene sentido programarlo ni siquiera
cuando exista infraestructura real: por eso este módulo, a propósito, **no
tiene modo `--interval-seconds` ni bucle**, igual que las capturas de
muestra de las tareas 003-008, pero por una razón distinta (no es que la
infraestructura AWS todavía no exista — es que este dato nunca necesitará
recaptura periódica, ni siquiera en producción). La carga completa real, el
día que se aplique la infraestructura de la tarea 001, será una carga batch
puntual directa a su destino (S3/Neo4j), invocada a mano cuando haga falta
(p.ej. tras una actualización relevante del callejero oficial), no un
productor en bucle.

## Fuente elegida y por qué

Dataset "Callejero. Información adicional asociada. Códigos postales, zonas
SER, categoría fiscal, parcela catastral, etc." (id `200075-0-callejero`) de
[datos.madrid.es](https://datos.madrid.es/dataset/200075-0-callejero), en
concreto dos de sus recursos CSV:

- **"Viales oficiales y topónimos"**: un registro por vial vigente (calle,
  avenida, plaza...) con su código, nombre, tipo, distritos que atraviesa,
  código(s) postal(es), y las coordenadas de inicio y fin del vial (en
  WGS84) — el nodo del grafo viario.
- **"Cruces de viales con coordenadas geográficas"**: un registro por cada
  cruce/enlace de un vial con otro vial, con la coordenada del cruce — la
  arista del grafo viario (qué vial conecta con qué otro vial, y dónde).

Se descartaron otras alternativas encontradas en la investigación:

- **"Callejero oficial del Ayuntamiento de Madrid"** (id
  `213605-0-callejero-oficial-madrid`): mismo origen (sistema CADMA), pero
  sus CSV de "viales vigentes" no incluyen coordenadas de inicio/fin ni
  cruces — solo intervalos de numeración por distrito/barrio. Útil para una
  futura tarea de direcciones/geocodificación, no para el grafo viario.
- **"Callejero oficial. Viales vigentes"** (id `300735-0-mapas-callejero-viales`):
  solo expone un servicio WMS (mapa renderizado), sin un recurso
  descargable con la topología vial/cruces en un formato tabular simple.
- **"Callejero Oficial del Ayuntamiento de Madrid (Servicio Web)"** (id
  `300274-0-callejero-oficial-webservice`): un servicio SOAP pensado para
  sincronizar *cambios* incrementales del callejero desde sistemas externos,
  no para una carga inicial de referencia.

Se ha verificado en vivo desde este entorno que ambos recursos elegidos son
accesibles **sin ninguna autenticación ni API key**.

### Formato real encontrado

Ambos CSV se publican en **ISO-8859-1 (Latin-1)** con `;` como separador (a
diferencia del UTF-8 de calidad del aire/meteorología). Las coordenadas
WGS84 vienen como texto en formato grados-minutos-segundos con el símbolo
`º` (p.ej. `"3º40'16.72'' W"`, `"40º30'55.78'' N"`), no como decimal — este
módulo las convierte a grados decimales (`_parse_dms`). El "Código de vía"
(p.ej. `"00000127"`) es el identificador estable que enlaza ambos ficheros
(un vial en "Viales" con sus cruces en "Cruces"), y se conserva tal cual
como `vial_id` (cadena de 8 dígitos con ceros a la izquierda, no se
convierte a entero) para no perder esa capacidad de cruce con la fuente
oficial ni con una futura carga completa.

El campo "Distritos atravesados" puede traer varios códigos separados por
`-` (p.ej. `"18-20-21"` si el vial cruza tres distritos); se normaliza a una
lista. El campo "Códigos postales" puede ser un único código, el literal
`"varios"` (la fuente no detalla cuáles cuando un vial tiene más de uno), o
estar vacío — se conserva tal cual como texto, sin inventar una lista que la
fuente no da.

TODO(kafka): a diferencia de las demás capturas, esta fuente es de
referencia y no encaja con el patrón de un topic Kafka por evento — el
destino natural de una carga de referencia es directamente el grafo Neo4j
(o una tabla de dimensión en el lakehouse), no un stream. Se deja la nota
igualmente por consistencia con el resto de módulos, pero no se espera que
esta fuente conecte nunca a un broker Kafka.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from .bronze import MADRID_TZ, now_madrid

logger = logging.getLogger(__name__)

DEFAULT_VIAS_URL = (
    "https://datos.madrid.es/dataset/200075-0-callejero/resource/"
    "200075-3-callejero-csv/download/callejero_vigente_viales_202607.csv"
)
DEFAULT_CROSSINGS_URL = (
    "https://datos.madrid.es/dataset/200075-0-callejero/resource/"
    "200075-8-callejero-csv/download/callejero_vigente_cruces_202607.csv"
)

SOURCE_VIAS = "madrid_callejero_vias"
SOURCE_CROSSINGS = "madrid_callejero_cruces"

DEFAULT_VIAS_SAMPLE_PATH = Path(__file__).parent / "samples" / "callejero_madrid_vias_sample.json"
DEFAULT_CROSSINGS_SAMPLE_PATH = (
    Path(__file__).parent / "samples" / "callejero_madrid_cruces_sample.json"
)
# Nº de viales (nodos del grafo) en la muestra; ver también
# MAX_CROSSINGS_PER_VIAL para acotar las aristas de cada uno.
DEFAULT_SAMPLE_SIZE = 5
# Algunos viales (grandes avenidas) tienen hasta ~150 cruces; se acota por
# vial para que la muestra siga siendo pequeña sin depender de qué viales
# concretos caigan en `DEFAULT_SAMPLE_SIZE`.
DEFAULT_MAX_CROSSINGS_PER_VIAL = 8

# El Ayuntamiento publica estos dos CSV en ISO-8859-1 (Latin-1), a diferencia
# del UTF-8 de calidad del aire/meteorología (tareas 006/008).
SOURCE_ENCODING = "iso-8859-1"

# Coordenadas WGS84 en formato "D<º>M'S.ss'' H" (grados, minutos, segundos,
# hemisferio N/S/E/W). El símbolo de grado de la fuente es el byte 0xBA en
# Latin-1 (U+00BA, "º"), no el signo de grado U+00B0.
_DMS_RE = re.compile(r"^(\d+)\xba(\d+)'([\d.]+)''\s*([NSEWnsew])$")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la carga, leída de variables de entorno.

    No hay campos de credenciales: ambos recursos de datos.madrid.es usados
    aquí son públicos y no requieren API key.
    """

    vias_url: str
    crossings_url: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_size: int
    max_crossings_per_vial: int

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            vias_url=os.environ.get("MADRID_STREETS_VIAS_URL", DEFAULT_VIAS_URL),
            crossings_url=os.environ.get("MADRID_STREETS_CROSSINGS_URL", DEFAULT_CROSSINGS_URL),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 30.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_size=_env_int("MADRID_STREETS_SAMPLE_SIZE", DEFAULT_SAMPLE_SIZE),
            max_crossings_per_vial=_env_int(
                "MADRID_STREETS_MAX_CROSSINGS_PER_VIAL", DEFAULT_MAX_CROSSINGS_PER_VIAL
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


def fetch_raw_vias(config: CaptureConfig) -> str:
    """Descarga el CSV completo de viales oficiales vigentes."""
    return _fetch_with_retries(config, config.vias_url).decode(SOURCE_ENCODING)


def fetch_raw_crossings(config: CaptureConfig) -> str:
    """Descarga el CSV completo de cruces de viales."""
    return _fetch_with_retries(config, config.crossings_url).decode(SOURCE_ENCODING)


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


def _parse_dms(raw: Optional[str]) -> Optional[float]:
    """Convierte una coordenada WGS84 en formato DMS de la fuente a grados decimales."""
    value = _clean(raw)
    if value is None:
        return None
    match = _DMS_RE.match(value)
    if not match:
        logger.warning("No se pudo parsear la coordenada DMS %r", raw)
        return None
    degrees, minutes, seconds, hemisphere = match.groups()
    decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if hemisphere.upper() in ("S", "W"):
        decimal = -decimal
    return round(decimal, 6)


def _parse_district_codes(raw: Optional[str]) -> list[str]:
    """El campo trae uno o varios códigos de distrito separados por '-' (p.ej. '18-20-21')."""
    value = _clean(raw)
    if not value:
        return []
    return [code.strip() for code in value.split("-") if code.strip()]


def normalize_vial_record(row: dict, ingested_at: datetime) -> dict:
    """Normaliza una fila del CSV de viales al esquema mínimo (nodo del grafo)."""
    return {
        "schema_version": 1,
        "source": SOURCE_VIAS,
        "vial_id": _clean(row.get("Codigo de vía")),
        "class": _clean(row.get("Clase de la via")),
        "particle": _clean(row.get("Particula de la via")),
        "name": _clean(row.get("Nombre de la via")),
        "full_name": _clean(row.get("Literal completo del vial ")),
        # "Vía" (calle, plaza...) o "Topónimo" (un punto singular, no un tramo con recorrido).
        "type": _clean(row.get("Tipo de la via")),
        "situation": _clean(row.get("Situacion de la via respecto al terreno")),
        "district_codes": _parse_district_codes(row.get("Distritos atravesados")),
        # Puede ser un único código postal, el literal "varios" (la fuente no
        # detalla cuáles), o None si no consta.
        "postal_code": _clean(row.get("Codigos postales")),
        "ine_code": _clean(row.get("Codigo de vía I N E ")),
        "address_count": _to_int(row.get("Cantidad de numeraciones en la via")),
        "ingested_at": ingested_at.astimezone(MADRID_TZ).isoformat(),
        "start_node": {
            "lat": _parse_dms(row.get("Latitud en S R  WGS84 (inicio)")),
            "lon": _parse_dms(row.get("Longitud en S R  WGS84 (inicio)")),
            "srid": "EPSG:4326",
        },
        "end_node": {
            "lat": _parse_dms(row.get("Latitud en S R  WGS84 (final)")),
            "lon": _parse_dms(row.get("Longitud en S R  WGS84 (final)")),
            "srid": "EPSG:4326",
        },
    }


def normalize_crossing_record(row: dict, ingested_at: datetime) -> dict:
    """Normaliza una fila del CSV de cruces al esquema mínimo (arista del grafo)."""
    return {
        "schema_version": 1,
        "source": SOURCE_CROSSINGS,
        "from_vial_id": _clean(row.get("Codigo de vía tratado")),
        "from_vial_name": _clean(row.get("Literal completo del vial tratado")),
        "to_vial_id": _clean(row.get("Codigo de via que cruza o enlaza")),
        "to_vial_name": _clean(row.get("Literal completo del vial que cruza")),
        "ingested_at": ingested_at.astimezone(MADRID_TZ).isoformat(),
        "location": {
            "lat": _parse_dms(row.get("Latitud en S R  WGS84 (cruce)")),
            "lon": _parse_dms(row.get("Longitud en S R  WGS84 (cruce)")),
            "srid": "EPSG:4326",
        },
    }


def select_sample_vias(vias_csv: str, sample_size: int) -> list[dict]:
    """Recorre el CSV de viales en orden y toma los primeros `sample_size` con coordenadas.

    Se descartan los viales sin coordenada de inicio (p.ej. topónimos sin
    recorrido, o viales con "Aproximacion poblacional" marcada como
    "nodisp"): no aportarían un nodo útil al grafo viario.
    """
    reader = csv.DictReader(vias_csv.splitlines(), delimiter=";")
    selected: list[dict] = []
    for row in reader:
        if not _clean(row.get("Longitud en S R  WGS84 (inicio)")):
            continue
        selected.append(row)
        if len(selected) >= sample_size:
            break
    return selected


def select_crossings_for_vias(
    crossings_csv: str, vial_ids: set[str], max_per_vial: int
) -> list[dict]:
    """Recorre el CSV de cruces y se queda con los que salen de alguno de `vial_ids`.

    El fichero de origen trae cada cruce dos veces (una vez con cada vial
    como "tratado"); filtrar solo por `Codigo de vía tratado` evita
    duplicar la misma arista en las dos direcciones. Se acota a
    `max_per_vial` cruces por vial para que la muestra no crezca sin
    control con viales muy concurridos (algunas avenidas grandes superan
    los 100 cruces).
    """
    reader = csv.DictReader(crossings_csv.splitlines(), delimiter=";")
    counts: dict[str, int] = {}
    selected: list[dict] = []
    for row in reader:
        vial_id = _clean(row.get("Codigo de vía tratado"))
        if vial_id not in vial_ids:
            continue
        if counts.get(vial_id, 0) >= max_per_vial:
            continue
        counts[vial_id] = counts.get(vial_id, 0) + 1
        selected.append(row)
    return selected


def _write_json(records: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, vias_out_path: Path, crossings_out_path: Path) -> tuple[Path, Path]:
    """Descarga, normaliza y guarda una muestra pequeña del grafo viario (nodos + aristas).

    Igual que las capturas de muestra de las tareas 003-008, esto NO
    escribe en la capa Bronze particionada ni deja nada programado: escribe
    dos ficheros de muestra pequeños y fijos (como mucho `config.sample_size`
    viales, con hasta `config.max_crossings_per_vial` cruces cada uno),
    pensados para commitearse como fixtures, no para acumularse en disco.
    """
    ingested_at = now_madrid()

    vias_csv = fetch_raw_vias(config)
    sample_rows = select_sample_vias(vias_csv, config.sample_size)
    vial_records = [normalize_vial_record(row, ingested_at) for row in sample_rows]
    vial_ids = {r["vial_id"] for r in vial_records if r["vial_id"]}
    logger.info("Viales de muestra seleccionados: %d", len(vial_records))

    crossings_csv = fetch_raw_crossings(config)
    crossing_rows = select_crossings_for_vias(crossings_csv, vial_ids, config.max_crossings_per_vial)
    crossing_records = [normalize_crossing_record(row, ingested_at) for row in crossing_rows]
    logger.info("Cruces de muestra seleccionados: %d", len(crossing_records))

    _write_json(vial_records, vias_out_path)
    _write_json(crossing_records, crossings_out_path)

    logger.info("Muestra de viales escrita en %s", vias_out_path)
    logger.info("Muestra de cruces escrita en %s", crossings_out_path)
    return vias_out_path, crossings_out_path


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Carga batch puntual de referencia del callejero/grafo viario de Madrid "
            "(viales y sus cruces) y la guarda como fixtures pequeños. No admite "
            "ejecución en bucle ni programada: es una carga puntual invocada a mano, "
            "pensada para no repetirse salvo que el callejero cambie de forma "
            "relevante."
        )
    )
    parser.add_argument(
        "--out-vias",
        type=Path,
        default=DEFAULT_VIAS_SAMPLE_PATH,
        help="Ruta del fichero de muestra de viales (nodos) a escribir",
    )
    parser.add_argument(
        "--out-cruces",
        type=Path,
        default=DEFAULT_CROSSINGS_SAMPLE_PATH,
        help="Ruta del fichero de muestra de cruces (aristas) a escribir",
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
    capture_sample(config, args.out_vias, args.out_cruces)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
