"""Carga batch puntual de calles y plazas del Servicio de Estacionamiento
Regulado (SER) de Madrid (muestra, referencia).

Descarga el listado de calles con aparcamiento regulado en superficie (zona
azul/verde/naranja) y lo normaliza a un esquema mínimo. Dataset distinto al
ya integrado por `aparcamientos_madrid.py` (tarea 005, aparcamientos
rotacionales **fuera de calle** -- parkings municipales/privados): el SER es
aparcamiento **en calle**, con capacidad y tipo de zona por tramo de vía, no
por parking. Verificado no solapado leyendo el docstring de
`aparcamientos_madrid.py` antes de escribir este módulo.

## Por qué esta fuente (sesión de arquitectura del 25/8)

El Gold de `aparcamientos` lleva roto y sin diagnosticar desde antes de la
tarea 083 (`NEXT_STEPS.md`, Prioridad 2) -- el tool pendiente
`disponibilidad_aparcamiento` no tiene ninguna fuente real utilizable hoy.
El SER es una vía alternativa: capacidad y ubicación reales, ya verificadas
en vivo (27.758 tramos de calle a fecha de esta captura), independiente del
pipeline roto de aparcamientos rotacionales.

**No incluye ocupación en tiempo real** -- esto es solo el listado estático
de calles/plazas/zonas (capacidad, no disponibilidad instantánea); la
ocupación real vendría de un dataset distinto ("SER. Tiques de
aparcamiento"), fuera de alcance de esta captura.

## Esto es una carga puntual de referencia, NO una captura periódica

Mismo criterio que `poi_madrid.py`/`barrios_distritos_madrid.py`: la
capacidad y zonificación de las calles SER cambia con muy poca frecuencia
(la propia fuente se actualiza trimestralmente). Sin `--interval-seconds`
ni bucle.

## Fuente elegida y por qué

Dataset "Servicio de Estacionamiento Regulado (SER). Calles y número de
plazas" (id `218228-0`) de
[datos.madrid.es](https://datos.madrid.es/dataset/218228-0-ser-calles),
publicado por el Ayuntamiento de Madrid, actualización trimestral. Se toma
el recurso CSV más reciente, resuelto vía la API de catálogo
`package_show` por fecha real (`last_modified`/`created`), no por el
sufijo numérico del `id` del recurso -- verificado en vivo que ese sufijo
**no** se corresponde con el orden cronológico de publicación en este
dataset (ver el docstring de `resolve_latest_csv_url`).

**Coordenadas en UTM ETRS89 huso 30N (`gis_x`/`gis_y`), sin reproyectar a
lat/lon en esta tarea** -- mismo criterio que `trafico_madrid.py` (tarea
002, ver su docstring): no añadir una dependencia de geoprocesado en
Bronze/ingesta sin necesidad. La reproyección (fórmulas cerradas de Snyder,
sin `pyproj`, ya implementada en
`procesamiento/silver_gold/trafico/geo.py::utm_etrs89_to_wgs84`) es trabajo
de una futura tarea de Silver/Gold para este dataset, no de esta captura.

**Bug real de la fuente, verificado en vivo (no de este módulo)**: el
recurso CSV de 2026 (el real, resuelto por `resolve_latest_csv_url`) trae
`gis_x`/`gis_y` corruptos -- la coma decimal se perdió en algún proceso de
conversión de la propia fuente, dejando un entero enorme en vez del decimal
esperado (mismo problema reproducido también en el XLSX equivalente, así
que no es un artefacto de parseo CSV). `_to_corrupted_gis_coord` recupera
el valor real dividiendo por `1e10` -- ver su docstring para la evidencia
completa. El esquema de columnas también cambió frente a recursos
anteriores de este mismo dataset (`distrito`/`cod_distrito` separados,
`numero_finca`/`numero_plazas` en vez de `num_finca`/`num_plazas`,
`color` con un prefijo RGB de 9 dígitos) -- no asumas que el esquema de un
dataset de datos.madrid.es es estable entre años sin comprobarlo primero.

**Codificación no constante entre recursos** -- ver el docstring de
`fetch_raw_calles`: se intenta UTF-8 con BOM primero, con Latin-1 como
fallback.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from .bronze import MADRID_TZ, BronzeWriter, now_madrid

logger = logging.getLogger(__name__)

# Prefijo de la capa Bronze para este dataset (ver `lambda_handler`).
DATASET_NAME = "ser_calles"

DATASET_ID = "218228-0-ser-calles"
CATALOG_API_URL = f"https://datos.madrid.es/api/action/package_show?id={DATASET_ID}"

SOURCE_NAME = "madrid_ser_calles"

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "ser_calles_madrid_sample.json"
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
    credenciales: el recurso es público, sin API key."""

    catalog_api_url: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_size: int

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            catalog_api_url=os.environ.get("MADRID_SER_CATALOG_API_URL", CATALOG_API_URL),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 30.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_size=_env_int("MADRID_SER_SAMPLE_SIZE", DEFAULT_SAMPLE_SIZE),
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


def resolve_latest_csv_url(config: CaptureConfig) -> str:
    """Consulta la API de catálogo (`package_show`) y devuelve la URL del
    recurso CSV más reciente, por `last_modified` (o `created` si falta).

    **El sufijo numérico del `id` NO se corresponde con el año/orden
    cronológico de publicación** -- verificado en vivo: el recurso
    `218228-26-ser-calles-csv` (sufijo alto) resultó ser el CSV de 2021,
    mientras que el dato de 2026 real vive en `218228-1-ser-calles-csv`
    (sufijo bajo). Un primer intento de este módulo asumía "sufijo más
    alto = más reciente" y habría descargado datos de hace 5 años
    silenciosamente -- no repitas ese error si tocas esta función."""
    raw = _fetch_with_retries(config, config.catalog_api_url)
    payload = json.loads(raw)
    resources = payload["result"]["resources"]
    csv_resources = [r for r in resources if r.get("format", "").upper() == "CSV"]
    if not csv_resources:
        raise RuntimeError(f"El dataset {DATASET_ID} no tiene ningún recurso CSV")

    def _resource_date(resource: dict) -> str:
        return resource.get("last_modified") or resource.get("created") or ""

    latest = max(csv_resources, key=_resource_date)
    return latest["url"]


def fetch_raw_calles(config: CaptureConfig, csv_url: str) -> str:
    """Descarga el CSV completo (todas las calles) y lo decodifica.

    **La codificación no es constante entre recursos de este dataset**:
    verificado en vivo que el CSV de 2021 (`218228-26-...`) es UTF-8 con
    BOM, pero el de 2026 (`218228-1-...`, el real usado por
    `resolve_latest_csv_url`) es Latin-1 -- probablemente publicados en
    momentos distintos con herramientas distintas. Se intenta UTF-8 (con
    BOM) primero y se cae a Latin-1 si falla, en vez de asumir una
    codificación fija."""
    raw_bytes = _fetch_with_retries(config, csv_url)
    try:
        return raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw_bytes.decode("latin-1")


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


def _to_corrupted_gis_coord(raw: Optional[str]) -> Optional[float]:
    """Recupera `gis_x`/`gis_y` del recurso 2026 (`218228-1-ser-calles-csv`),
    que llega corrupto en la fuente misma -- verificado también en el XLSX
    equivalente (`218228-0-ser-calles-xlsx`), no es un artefacto de parseo
    CSV.

    El valor esperado es un decimal con coma (formato español, mismo
    criterio que el recurso de 2021: `"439569,0700000000"`, con la parte
    decimal rellenada a 10 dígitos). En este recurso, algún proceso de
    conversión de la fuente eliminó la coma sin tratarla como separador
    decimal, concatenando la parte entera y la fraccionaria de 10 dígitos
    en un único entero (`"439569,0700000000"` -> `4395690700000000`) --
    verificado con varios puntos reales de esta captura: dividir por
    `1e10` recupera una coordenada UTM plausible dentro de Madrid (huso
    30N, easting ~440.000, northing ~4.474.000).

    El CSV además usa `.` como separador de miles dentro de ese entero ya
    corrupto (`"4.427.249.100.000.000"`), así que primero se quitan los
    puntos."""
    value = _clean(raw)
    if value is None:
        return None
    digits = value.replace(".", "")
    try:
        return int(digits) / 1e10
    except ValueError:
        return None


def _split_zone_color(raw: Optional[str]) -> "tuple[Optional[str], Optional[str]]":
    """`color` llega como `"<RGB de 9 dígitos><espacio><nombre>"`
    (p.ej. `"043000255 Azul"` = RGB `(043, 000, 255)` + `"Azul"`) --
    verificado en vivo, no documentado por la fuente. Devuelve
    `(rgb, nombre)`; si no matchea ese patrón devuelve `(None, raw)` sin
    perder el dato."""
    value = _clean(raw)
    if value is None:
        return None, None
    parts = value.split(" ", 1)
    if len(parts) == 2 and parts[0].isdigit() and len(parts[0]) == 9:
        return parts[0], parts[1]
    return None, value


def _iter_calles_con_coordenadas(calles_csv: str) -> "list[dict]":
    """Todas las filas del CSV que traen `gis_x` y `gis_y` no vacíos."""
    reader = csv.DictReader(io.StringIO(calles_csv), delimiter=";")
    return [
        row
        for row in reader
        if (row.get("gis_x") or "").strip() and (row.get("gis_y") or "").strip()
    ]


def select_sample_calles(calles_csv: str, sample_size: int) -> "list[dict]":
    """Las primeras `sample_size` filas con coordenadas conocidas."""
    return _iter_calles_con_coordenadas(calles_csv)[:sample_size]


def normalize_record(row: dict, ingested_at: datetime) -> dict:
    """Normaliza una fila del CSV al esquema mínimo de tramos SER.

    Columnas verificadas en vivo contra el recurso 2026 real
    (`distrito`/`barrio` como nombre, `cod_distrito`/`cod_barrio` como
    código, separados -- a diferencia de recursos antiguos que traían
    `"01  CENTRO"` combinado en una sola columna `distrito`)."""
    rgb, zone_name = _split_zone_color(row.get("color"))
    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "district_code": _clean(row.get("cod_distrito")),
        "district": _clean(row.get("distrito")),
        "neighbourhood_code": _clean(row.get("cod_barrio")),
        "neighbourhood": _clean(row.get("barrio")),
        "street": _clean(row.get("calle")),
        "street_number": _clean(row.get("numero_finca")),
        "zone_color": zone_name,
        "zone_rgb": rgb,
        "layout": _clean(row.get("bateria_linea")),
        "num_spaces": _to_int(row.get("numero_plazas")),
        "ingested_at": ingested_at.astimezone(MADRID_TZ).isoformat(),
        "location": {
            "x": _to_corrupted_gis_coord(row.get("gis_x")),
            "y": _to_corrupted_gis_coord(row.get("gis_y")),
            "srid": "EPSG:25830",
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
    """Descarga, normaliza y guarda una muestra pequeña de tramos de calle SER.

    Igual que el resto de cargas de referencia: NO escribe en Bronze
    particionado ni deja nada programado. El CSV completo (27.758 filas a
    fecha de esta captura) se descarga en memoria porque la fuente no ofrece
    filtrado remoto, pero nunca se escribe a disco completo.
    """
    ingested_at = now_madrid()

    csv_url = resolve_latest_csv_url(config)
    logger.info("Recurso CSV más reciente resuelto: %s", csv_url)
    calles_csv = fetch_raw_calles(config, csv_url)
    sample = select_sample_calles(calles_csv, config.sample_size)
    records = [normalize_record(row, ingested_at) for row in sample]
    logger.info("Tramos de calle SER de muestra seleccionados: %d", len(records))

    _write_json(records, out_path)
    logger.info("Muestra escrita en %s", out_path)
    return out_path


def capture_all(config: CaptureConfig) -> "list[dict]":
    """Descarga y normaliza TODOS los tramos de calle SER (sin recorte de muestra).

    Pensado para el handler Lambda: dato de referencia (la fuente se
    actualiza trimestralmente), así que el schedule real debe ser semanal,
    no horario -- ver docstring del módulo y `FIL_05`.
    """
    ingested_at = now_madrid()
    csv_url = resolve_latest_csv_url(config)
    logger.info("Recurso CSV más reciente resuelto: %s", csv_url)
    calles_csv = fetch_raw_calles(config, csv_url)
    records = [
        normalize_record(row, ingested_at)
        for row in _iter_calles_con_coordenadas(calles_csv)
    ]
    logger.info("Tramos de calle SER capturados (captura completa): %d", len(records))
    return records


def lambda_handler(event, context):
    """Punto de entrada AWS Lambda (FIL_05): captura completa a Bronze real."""
    config = CaptureConfig.from_env()
    records = capture_all(config)
    writer = BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=DATASET_NAME)
    out_path = writer.write_batch(records)
    logger.info("Captura Lambda completada: %s", out_path)
    return {"dataset": DATASET_NAME, "records_written": len(records), "location": str(out_path)}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Carga batch puntual de referencia de calles y plazas del Servicio de "
            "Estacionamiento Regulado (SER) de Madrid y la guarda como fixture "
            "pequeño. No admite ejecución en bucle ni programada."
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
