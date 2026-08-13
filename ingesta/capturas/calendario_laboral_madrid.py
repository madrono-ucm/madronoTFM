"""Carga batch puntual del calendario laboral y festivos de Madrid (muestra, referencia).

Descarga el calendario laboral oficial del Ayuntamiento de Madrid (un
registro por cada día natural, con su tipo de jornada y, si es festivo, el
nombre y ámbito del festivo) y lo normaliza a un esquema mínimo pensado para
que el resto del pipeline (y, en última instancia, el modelo de afluencia)
pueda distinguir un martes festivo de un martes laborable normal: a efectos
de afluencia, un festivo se comporta como domingo, no como el día de la
semana que sea.

## Esto es una carga puntual de referencia, NO una captura periódica

Igual que `callejero_madrid.py` (tarea 009) y `barrios_distritos_madrid.py`
(tarea 010), el calendario laboral es un dato de **referencia** casi
estático: el Ayuntamiento lo publica de una vez para años completos, con
antelación (el recurso vigente en el momento de esta tarea ya cubre
2013-2026 completos, incluido lo que queda de 2026 y toda la previsión
oficial de festivos ya aprobados). No tiene sentido programar su recaptura
con una cadencia frecuente ni siquiera cuando exista infraestructura real:
por eso este módulo, a propósito, **no tiene modo `--interval-seconds` ni
bucle**. La carga real, el día que se aplique la infraestructura de la tarea
001, seguirá siendo una carga batch puntual invocada a mano cuando el
Ayuntamiento publique la actualización anual (o corrija un festivo local),
no un productor en bucle.

## Fuente elegida y por qué

Dataset "Calendario laboral" (id `300082-0-calendario_laboral`) de
[datos.madrid.es](https://datos.madrid.es/egob/catalogo/300082-0-calendario_laboral),
en concreto su recurso CSV
(`.../resource/300082-1-calendario_laboral-csv/download/300082-1-calendario_laboral-csv.csv`).
El dataset también publica ICS y XLS/PDF, pero se descartaron en favor del
CSV:

- Los recursos **ICS** (hay dos, con contenido distinto entre sí) solo
  incluyen los días **festivos** de un único año natural (14 eventos cada
  uno, verificado en vivo: el primero para 2025, el segundo con un evento
  suelto de 2026), sin el resto del calendario (laborable/sábado/domingo).
  Para el objetivo de esta tarea —poder consultar el tipo de cualquier día,
  no solo si es festivo— hace falta el calendario completo día a día, no
  solo la lista de festivos.
- El **CSV**, en cambio, trae **un registro por cada día natural desde el
  01/01/2013 hasta el 31/12/2026** (5.112 filas, verificado en vivo), con
  columnas `Dia`, `Dia_semana`, la clasificación de jornada
  (`laborable`/`festivo`/`sabado`/`domingo`), y —solo en los días festivos—
  `Tipo de Festivo` y `Festividad` (el nombre del festivo). Es el único
  recurso que cubre el caso general (cualquier día, no solo festivos) que
  pide el enunciado de esta tarea.

Se ha verificado en vivo desde este entorno que el recurso CSV es accesible
**sin ninguna autenticación ni API key**.

### Formato real encontrado y mapeo de `Tipo de Festivo`

El CSV se publica en **UTF-8 con BOM**, con `;` como separador y fechas en
formato `DD/MM/AAAA`. La columna `Tipo de Festivo` solo tiene valor en los
días festivos y toma, en la práctica, cuatro valores no vacíos (verificado
recorriendo las 5.112 filas): `"Festivo nacional"`, `"Festivo de la
Comunidad de Madrid"`, `"Traslado de la fiesta de la Comunidad de Madrid"` y
`"Festivo local de la ciudad de Madrid"` — que este módulo mapea al ámbito
pedido por el enunciado (nacional/regional/local) vía `HOLIDAY_TYPE_MAP`,
conservando además el texto original de la fuente en `holiday_type_raw` por
si una tarea futura necesita distinguir un traslado de una fiesta regional
del festivo original.

### Dos problemas de calidad de datos de la propia fuente (documentados, no corregidos)

Se detectaron en vivo, recorriendo las 5.112 filas del CSV real, dos
inconsistencias de la fuente que este módulo **no intenta adivinar o
corregir**, solo documenta y expone tal cual:

1. **Falta el 29/02/2016**: 2016 fue año bisiesto, pero el CSV salta
   directamente del 28/02/2016 al 01/03/2016 (verificado: es el único hueco
   en toda la serie 2013-2026, que por lo demás es contigua día a día). El
   recuento de días de 2016 en la fuente es 365, no 366. No se rellena ese
   día ausente con un valor inventado.
2. **Dos días festivos sin `Tipo de Festivo`** (`15/05/2016`, domingo, y
   `02/05/2023`, sin nombre de festividad y con nombre de festividad
   respectivamente vacíos/rellenos de forma inconsistente): en ambos casos
   `laborable / festivo / domingo festivo` marca el día como `festivo` pero
   la columna de tipo viene vacía. `normalize_day_record` conserva
   `holiday_type`/`holiday_type_raw` como `None` en vez de inferir un valor,
   y deja constancia del nombre de festividad (`Festividad`) tal cual venga
   (vacío en el primer caso, con texto en el segundo).

## Relevante para el modelo de afluencia

El campo derivado `is_holiday` (`day_type == "festivo"`) es, junto con
`day_type` en general (`laborable`/`festivo`/`sabado`/`domingo`), el dato
que motiva esta tarea: permite tratar un martes festivo como un domingo a
efectos de afluencia sin tener que mantener una lista de festivos aparte ni
calcularla a mano.

TODO(kafka): igual que `callejero_madrid.py` y `barrios_distritos_madrid.py`,
esta fuente es de referencia y no encaja con el patrón de un topic Kafka por
evento — su destino natural es una tabla/dimensión de calendario en el
lakehouse (o un nodo de calendario en Neo4j), no un stream. Se deja la nota
igualmente por consistencia con el resto de módulos, pero no se espera que
esta fuente conecte nunca a un broker Kafka.
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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_CSV_URL = (
    "https://datos.madrid.es/dataset/300082-0-calendario_laboral/resource/"
    "300082-1-calendario_laboral-csv/download/300082-1-calendario_laboral-csv.csv"
)

SOURCE = "madrid_calendario_laboral"

# El Ayuntamiento publica este CSV en UTF-8 con BOM (a diferencia del
# ISO-8859-1 del callejero, tarea 009).
SOURCE_ENCODING = "utf-8-sig"

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "calendario_laboral_madrid_sample.json"

# Mapeo del texto de "Tipo de Festivo" de la fuente al ámbito normalizado
# nacional/regional/local pedido por el enunciado de esta tarea. Los dos
# valores de "traslado" comparten ámbito con su festivo original: solo
# existe traslado documentado a nivel regional en la fuente (verificado
# recorriendo las 5.112 filas del CSV real), pero se deja también el mapeo
# de un hipotético traslado nacional/local por si apareciera en una
# actualización futura del dataset.
HOLIDAY_TYPE_MAP = {
    "Festivo nacional": "nacional",
    "Traslado de la fiesta nacional": "nacional",
    "Festivo de la Comunidad de Madrid": "regional",
    "Traslado de la fiesta de la Comunidad de Madrid": "regional",
    "Festivo local de la ciudad de Madrid": "local",
    "Traslado de la fiesta local de la ciudad de Madrid": "local",
}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la carga, leída de variables de entorno.

    No hay campos de credenciales: el recurso CSV usado aquí es público y no
    requiere API key.
    """

    csv_url: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    sample_year: Optional[int]

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        sample_year_raw = os.environ.get("MADRID_CALENDAR_SAMPLE_YEAR")
        return cls(
            csv_url=os.environ.get("MADRID_CALENDAR_CSV_URL", DEFAULT_CSV_URL),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 30.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
            sample_year=int(sample_year_raw) if sample_year_raw else None,
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


def fetch_raw_csv(config: CaptureConfig) -> str:
    """Descarga el CSV completo del calendario laboral (2013-2026)."""
    return _fetch_with_retries(config, config.csv_url).decode(SOURCE_ENCODING)


def parse_csv_rows(raw_csv: str) -> list[dict]:
    """Parsea el CSV crudo (delimitado por `;`) a filas dict."""
    reader = csv.DictReader(io.StringIO(raw_csv), delimiter=";")
    return list(reader)


def _clean(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def normalize_day_record(row: dict, ingested_at: datetime) -> dict:
    """Normaliza una fila del CSV al esquema mínimo de un día del calendario."""
    day = datetime.strptime(row["Dia"].strip(), "%d/%m/%Y").date()
    day_type = _clean(row.get("laborable / festivo / domingo festivo"))
    holiday_type_raw = _clean(row.get("Tipo de Festivo"))
    return {
        "schema_version": 1,
        "source": SOURCE,
        "date": day.isoformat(),
        "weekday": _clean(row.get("Dia_semana")),
        "day_type": day_type,
        "is_holiday": day_type == "festivo",
        "holiday_type": HOLIDAY_TYPE_MAP.get(holiday_type_raw) if holiday_type_raw else None,
        "holiday_type_raw": holiday_type_raw,
        "holiday_name": _clean(row.get("Festividad")),
        "ingested_at": ingested_at.astimezone(timezone.utc).isoformat(),
    }


def select_year(records: list[dict], year: Optional[int] = None) -> list[dict]:
    """Filtra los registros normalizados a un único año natural.

    Si `year` es `None`, se queda con el año más reciente presente en
    `records` (el calendario laboral se publica con años completos de
    antelación, así que el año más reciente es también el más relevante
    "de cara al futuro" para el modelo de afluencia).
    """
    if not records:
        return []
    target_year = year if year is not None else max(date.fromisoformat(r["date"]).year for r in records)
    return [r for r in records if date.fromisoformat(r["date"]).year == target_year]


def _write_json(records: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Descarga, normaliza y guarda una muestra de un único año del calendario laboral.

    Se descarga el CSV completo (2013-2026, ~5.100 filas, ~150 KB: no hay
    forma de filtrar por año en origen y el fichero completo ya es pequeño),
    se normaliza entero, y solo se escribe a disco el año seleccionado
    (`config.sample_year`, o el más reciente disponible si no se fija) —
    igual que otras cargas de referencia de este proyecto, esto NO escribe en
    la capa Bronze particionada ni deja nada programado.
    """
    ingested_at = datetime.now(timezone.utc)

    raw_csv = fetch_raw_csv(config)
    rows = parse_csv_rows(raw_csv)
    logger.info("Días descargados del calendario laboral: %d", len(rows))

    records = [normalize_day_record(row, ingested_at) for row in rows]
    sample = select_year(records, config.sample_year)
    logger.info(
        "Muestra seleccionada: %d días de %s",
        len(sample),
        sample[0]["date"][:4] if sample else "?",
    )

    _write_json(sample, out_path)
    logger.info("Muestra escrita en %s", out_path)
    return out_path


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Carga batch puntual de referencia del calendario laboral y festivos de "
            "Madrid, y la guarda como fixture pequeño (un único año). No admite "
            "ejecución en bucle ni programada: es una carga puntual invocada a mano, "
            "pensada para no repetirse salvo que el Ayuntamiento publique una "
            "actualización anual o corrija un festivo."
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
    capture_sample(config, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
