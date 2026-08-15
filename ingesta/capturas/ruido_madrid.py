"""Productor de datos abiertos de contaminación acústica (ruido) de Madrid
(muestra puntual).

Descarga los valores diarios de contaminación acústica registrados por la Red
Fija del Sistema Integral de Vigilancia de la Contaminación Acústica (SIVCA)
del Ayuntamiento de Madrid y, para poder resolver nombre/ubicación de cada
estación, su catálogo de estaciones, y los normaliza a un esquema mínimo y
consistente. Igual que `transporte_publico_madrid.py` (tarea 003),
`bicimad.py` (tarea 004), `aparcamientos_madrid.py` (tarea 005) y
`calidad_aire_madrid.py` (tarea 006), esto es a propósito **solo una captura
puntual de muestra** — ver "Alcance reducido" en `ingesta/README.md`.

## Fuente elegida y por qué

Dataset "Contaminación acústica. Datos diarios" (id `215885-0-contaminacion-ruido`)
de [datos.madrid.es](https://datos.madrid.es/dataset/215885-0-contaminacion-ruido):
valores diarios (LAeq y percentiles L1/L10/L50/L90/L99) de las 31 estaciones
fijas de la Red Fija del SIVCA, para cada uno de los 4 periodos horarios
(diurno, vespertino, nocturno, total). Se actualiza a diario (excepto fines
de semana y festivos), con el último día finalizado disponible al día
siguiente. A diferencia de calidad del aire (tarea 006), que sí publica un
feed horario en tiempo real, **no existe un dataset de ruido con granularidad
horaria/tiempo real** en datos.madrid.es: solo un agregado diario por
estación+periodo. Es, aun así, la fuente que sugería la propia tarea
("datos.madrid.es publica niveles sonoros por estación") y la más granular
disponible para esta red — el resto de datasets de ruido del portal
(histórico mensual, mapas estratégicos de ruido) son agregados a más largo
plazo, peor ajuste para una captura de muestra "actual".

El recurso descargable es un único CSV con el histórico completo desde 2014
(~540.000 filas, ~24 MB a fecha de esta captura), no un recurso separado por
día — por eso `parse_latest_day_entries` se queda solo con las filas del
último día presente en el fichero, sin acumular el histórico completo en
memoria.

El CSV **no incluye nombre, dirección ni coordenadas de la estación** (solo
su código numérico), así que esta captura hace una segunda descarga al
dataset "Estaciones de medición de ruido de la Red Fija del SIVCA" (id
`211346-0-estaciones-acusticas`), con esos metadatos por estación — mismo
patrón de dos fuentes combinadas que `calidad_aire_madrid.py`,
`aparcamientos_madrid.py` y `bicimad.py`.

Se verificó en vivo desde este entorno que ambos recursos son accesibles
**sin ninguna autenticación ni API key**.

TODO(kafka): igual que en los productores anteriores, cuando exista un
broker Kafka (tarea 001), `normalize_record` es la única fuente de verdad
del esquema a reutilizar tanto para el fixture/Bronze como para un topic
Kafka.

## Handler Lambda (tarea 027, lote 2/3)

`lambda_handler`/`capture_all` implementan el productor programado: la
captura completa (todas las estaciones del último día disponible, sin el
recorte `sample_stations` de `capture_sample`) escrita en Bronze real vía
`BronzeWriter`, mismo patrón que los 5 productores del lote 1 (tarea 026).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests

from .bronze import BronzeWriter, MADRID_TZ, now_madrid

logger = logging.getLogger(__name__)

DEFAULT_DAILY_URL = (
    "https://datos.madrid.es/dataset/215885-0-contaminacion-ruido/resource/"
    "215885-0-contaminacion-ruido/download/215885-0-contaminacion-ruido.csv"
)
DEFAULT_STATIONS_URL = (
    "https://datos.madrid.es/dataset/211346-0-estaciones-acusticas/resource/"
    "211346-4-estaciones-acusticas-csv/download/211346-4-estaciones-acusticas-csv.csv"
)

SOURCE_NAME = "madrid_ruido_diario"
DATASET_NAME = "ruido"
DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "ruido_madrid_sample.json"
# A diferencia de las otras capturas de muestra (5 *registros*), aquí se
# cuenta en *estaciones*: cada estación aporta hasta 4 registros (uno por
# periodo D/E/N/T), así que "unas pocas estaciones" (ver objetivo de la
# tarea) ya produce una muestra de tamaño similar a las anteriores.
DEFAULT_SAMPLE_STATIONS = 5

# Anexo del PDF "Contaminación acústica. Datos diarios. Contenido y
# estructura del fichero": código de periodo -> nombre.
PERIODS: dict[str, str] = {
    "D": "diurno",
    "E": "vespertino",
    "N": "nocturno",
    "T": "total",
}

# Ambos recursos CSV de este dataset se publican en ISO-8859-1 (Latin-1),
# a diferencia del JSON/CSV UTF-8 con BOM de calidad del aire (tarea 006).
SOURCE_ENCODING = "iso-8859-1"


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

    daily_url: str
    stations_url: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_stations: int

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            daily_url=os.environ.get("MADRID_NOISE_DAILY_URL", DEFAULT_DAILY_URL),
            stations_url=os.environ.get("MADRID_NOISE_STATIONS_URL", DEFAULT_STATIONS_URL),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 15.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_stations=_env_int("MADRID_NOISE_SAMPLE_STATIONS", DEFAULT_SAMPLE_STATIONS),
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


def fetch_raw_daily(config: CaptureConfig) -> str:
    """Descarga el CSV completo del histórico de contaminación acústica diaria."""
    return _fetch_with_retries(config, config.daily_url).decode(SOURCE_ENCODING)


def fetch_raw_stations(config: CaptureConfig) -> str:
    """Descarga el CSV del catálogo de estaciones de la Red Fija del SIVCA."""
    return _fetch_with_retries(config, config.stations_url).decode(SOURCE_ENCODING)


def _to_float(raw: Optional[str]) -> Optional[float]:
    """Convierte un número con coma decimal (formato de origen) a `float`."""
    if raw is None or raw.strip() == "":
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


def _parse_grouped_decimal(raw: Optional[str]) -> Optional[float]:
    """Convierte latitud/longitud tal como las publica el catálogo de estaciones.

    El CSV de origen las exporta con puntos de más (p.ej. `"-3.691.877"` en
    vez de `-3.691877`, o `"40.422.599"` en vez de `40.422599`): el primer
    fragmento tras un signo opcional es la parte entera, y el resto de
    fragmentos separados por `.` son la parte decimal concatenada.
    """
    if raw is None or raw.strip() == "":
        return None
    parts = raw.strip().split(".")
    if len(parts) <= 1:
        try:
            return float(raw.strip())
        except ValueError:
            return None
    integer_part, fraction_parts = parts[0], parts[1:]
    try:
        return float(f"{integer_part}.{''.join(fraction_parts)}")
    except ValueError:
        return None


def parse_stations(csv_text: str) -> dict[str, dict]:
    """Parsea el CSV del catálogo de estaciones a un diccionario por código de estación."""
    reader = csv.DictReader(csv_text.splitlines(), delimiter=";")
    stations: dict[str, dict] = {}
    for row in reader:
        code = (row.get("ESTACIÓN") or "").strip()
        if not code:
            continue
        stations[code] = {
            "name": (row.get("NOMBRE") or "").strip() or None,
            "address": (row.get("UBICACIÓN") or "").strip() or None,
            "district": (row.get("DISTRITO") or "").strip() or None,
            "neighbourhood": (row.get("BARRIO") or "").strip() or None,
            "lat": _parse_grouped_decimal(row.get("LATITUD")),
            "lon": _parse_grouped_decimal(row.get("LONGITUD")),
            "altitude_m": _to_int(row.get("ALTITUD")),
        }
    return stations


def parse_latest_day_entries(csv_text: str) -> list[dict]:
    """Parsea el CSV diario y devuelve solo las filas del último día presente.

    El fichero de origen está ordenado cronológicamente ascendente (crece
    cada día hábil desde 2014), así que en vez de acumular las ~540.000
    filas de histórico en memoria, esta función se queda únicamente con las
    filas cuya fecha (Año/Mes/Día) coincide con la última vista al terminar
    de recorrer el fichero.
    """
    reader = csv.DictReader(csv_text.splitlines(), delimiter=";")
    latest_key: Optional[tuple] = None
    latest_rows: list[dict] = []
    for row in reader:
        key = (row.get("Año"), row.get("Mes"), row.get("Día"))
        if key != latest_key:
            latest_key = key
            latest_rows = []
        latest_rows.append(row)
    return latest_rows


def _station_id(raw_code: Optional[str]) -> Optional[str]:
    """Normaliza el código numérico plano de la fuente (p.ej. `"3"`) al código
    del catálogo de estaciones (p.ej. `"RF-03"`)."""
    if raw_code is None:
        return None
    raw_code = raw_code.strip()
    if not raw_code.isdigit():
        return None
    return f"RF-{int(raw_code):02d}"


def normalize_record(entry: dict, stations: dict[str, dict], ingested_at: datetime) -> dict:
    """Normaliza una fila estación+periodo+día al esquema mínimo."""
    station_id = _station_id(entry.get("Estación"))
    station_info = stations.get(station_id, {}) if station_id else {}

    period_code = (entry.get("Periodo") or "").strip()
    measured_date = date(int(entry["Año"]), int(entry["Mes"]), int(entry["Día"]))

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "station_id": station_id,
        "station_name": station_info.get("name"),
        "station_address": station_info.get("address"),
        "district": station_info.get("district"),
        "neighbourhood": station_info.get("neighbourhood"),
        "period": period_code,
        "period_name": PERIODS.get(period_code),
        # Agregado diario, sin hora asociada: a diferencia de `measured_at`
        # en el resto de capturas (un instante concreto), aquí solo hay
        # fecha, tal como la publica la fuente.
        "measured_date": measured_date.isoformat(),
        "ingested_at": ingested_at.astimezone(MADRID_TZ).isoformat(),
        "laeq_db": _to_float(entry.get("LAeq")),
        "l1_db": _to_float(entry.get("L1")),
        "l10_db": _to_float(entry.get("L10")),
        "l50_db": _to_float(entry.get("L50")),
        "l90_db": _to_float(entry.get("L90")),
        "l99_db": _to_float(entry.get("L99")),
        "location": {
            "lat": station_info.get("lat"),
            "lon": station_info.get("lon"),
            "srid": "EPSG:4326",
            "altitude_m": station_info.get("altitude_m"),
        },
    }


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña de niveles de ruido diarios.

    Igual que en las tareas 003-006, esto NO escribe en la capa Bronze
    particionada: escribe una única muestra pequeña (como mucho
    `config.sample_stations` estaciones, con hasta 4 registros cada una —
    uno por periodo D/E/N/T — del último día disponible) en un fichero fijo,
    pensado para commitearse como fixture, no para acumular capturas.
    """
    ingested_at = now_madrid()

    stations_csv = fetch_raw_stations(config)
    stations = parse_stations(stations_csv)
    logger.info("Catálogo de estaciones descargado: %d estaciones", len(stations))

    daily_csv = fetch_raw_daily(config)
    latest_entries = parse_latest_day_entries(daily_csv)
    logger.info(
        "Lecturas diarias descargadas: %d filas del último día disponible", len(latest_entries)
    )

    records = []
    selected_stations: list[str] = []
    for entry in latest_entries:
        raw_code = (entry.get("Estación") or "").strip()
        if raw_code not in selected_stations:
            if len(selected_stations) >= config.sample_stations:
                continue
            selected_stations.append(raw_code)
        records.append(normalize_record(entry, stations, ingested_at))

    logger.info(
        "Muestra normalizada: %d lecturas de %d estaciones", len(records), len(selected_stations)
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)

    logger.info("Muestra escrita en %s", out_path)
    return out_path


def capture_all(config: CaptureConfig) -> "list[dict]":
    """Descarga y normaliza el último día disponible, TODAS las estaciones (31 x hasta 4 periodos).

    A diferencia de `capture_sample` (que corta a `config.sample_stations`
    estaciones), esto es la captura completa pensada para el handler Lambda
    (tarea 027): el último día ya es, de por sí, el recorte necesario (el
    CSV de origen es un histórico completo desde 2014, ver docstring del
    módulo) — "completa" aquí es "todas las estaciones de ese último día".
    """
    ingested_at = now_madrid()

    stations_csv = fetch_raw_stations(config)
    stations = parse_stations(stations_csv)

    daily_csv = fetch_raw_daily(config)
    latest_entries = parse_latest_day_entries(daily_csv)

    records = [normalize_record(entry, stations, ingested_at) for entry in latest_entries]
    logger.info("Normalizadas %d lecturas de ruido del último día (captura completa)", len(records))
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
            "Captura una muestra puntual de niveles de ruido diarios de Madrid "
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
