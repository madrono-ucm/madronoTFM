"""Captura de cartelera y horarios de cines de Madrid (muestra).

Ir al cine es uno de los "planes alternativos" que Madroño podría recomendar
(ver `documents/Memoria_TFM FV.docx`), y complementa a la tarea 022 (agenda
de grandes recintos): a diferencia de un partido en el Bernabéu, no hay una
API oficial de las grandes cadenas de cines (Cinesa, Yelmo Cines).

## Investigación de la fuente: JSON-LD sí, pero no `ScreeningEvent`

El enunciado pedía investigar primero si las páginas de cartelera exponen
`schema.org/ScreeningEvent` en JSON-LD antes de asumir que hace falta
scraping de HTML. Se investigó en vivo durante esta sesión:

- **`cinesa.es`**: bloqueado por Cloudflare a nivel de dominio completo
  (`403` con página de challenge incluso en `/robots.txt`, con cualquier
  User-Agent probado) — mismo tipo de bloqueo de WAF ya documentado para
  `wizinkcenter.es` en la tarea 022.
- **`yelmocines.es`**: no bloqueado, pero su sitio es una aplicación
  ASP.NET clásica sin URLs de cartelera adivinables ni JSON-LD; forzar el
  scraping de este sitio en concreto habría exigido primero mapear su
  navegación (selector de ciudad/cine) a mano, con el riesgo de fragilidad
  que el enunciado pedía evitar si era "excesivamente frágil".
- **SensaCine** (`sensacine.com`, propiedad de Webedia/AlloCiné): agrega la
  cartelera de **todas** las cadenas de España, incluidas Cinesa y Yelmo,
  bajo una única web. Verificado en vivo: **sí publica JSON-LD**, pero solo
  `schema.org/MovieTheater` (nombre, dirección, número de salas) e
  `ItemList` (enlaces a las fichas de película); **no publica
  `ScreeningEvent`** en ningún JSON-LD — los horarios concretos con su hora
  no están en el bloque estructurado.

Sí se encontró, en cambio, algo casi tan bueno: los horarios están en el
HTML servido (sin necesidad de ejecutar JavaScript — `curl` sin cabecera de
navegador ya devuelve el HTML completo) como **atributos `data-*`
explícitos y ya tipados** en cada franja horaria
(`data-showtime-time="2026-08-13T22:10:00+02:00"`, `data-showtime-id`,
`data-experiences` con la versión/formato en JSON), no como texto libre que
haya que interpretar. No es JSON-LD, pero es sensiblemente más robusto que
"parsear HTML a mano" en el sentido que preocupaba al enunciado: son
atributos con nombre y forma estables pensados por el propio sitio para que
su JavaScript de reserva los lea, no prosa. Por eso se eligió SensaCine
como fuente única para ambas cadenas, en vez de un scraper distinto por
cadena.

## Términos de uso de SensaCine: zona gris, igual que la tarea 012

Se leyeron en vivo los términos legales de SensaCine
(`https://www.sensacine.com/servicios/terminos/`): reservan expresamente la
reproducción/distribución del sitio y limitan su uso a "privado y
personal", prohibiendo cualquier fin comercial sin consentimiento escrito.
Es exactamente el mismo tipo de zona gris ya documentado en la tarea 012
(`afluencia_lugares_madrid.py`, apartado 6.8 de la memoria): admisible aquí
como muestra pequeña en el marco académico de este TFM, pero **no** apto
para escalar a un scraping masivo o comercial sin revisar antes esos
términos con la propia SensaCine. `robots.txt` no añade una restricción
adicional relevante (solo excluye rutas de utilidades internas y algunos
bots de entrenamiento de IA por nombre — ninguno coincide con este cliente,
verificado en vivo; a diferencia de la tarea 022, aquí no hay ninguna señal
tipo `Disallow: /` dirigida a un User-Agent de Claude). El `User-Agent` de
este módulo se identifica honestamente
(`madrono-tfm-ingesta/0.1 (+madrono.ucm@gmail.com; academic research)`,
mismo patrón que `bluesky_menciones_madrid.py`), sin suplantar un
navegador.

## Dos modos

- `fetch_cinema_showtimes(cinema_id, ...)`: cartelera completa de un cine
  concreto (película + horario + versión de idioma) — pensado para uso bajo
  demanda por el asistente conversacional.
- `sweep_premieres(...)`: estrenos destacados de la semana en España (no
  hay estrenos "solo Madrid": SensaCine publica una única lista nacional) —
  pensado para una futura captura programada ligera y diaria, ya que la
  cartelera cambia semanalmente pero puede haber cambios/cancelaciones
  puntuales de un día para otro.

## Deduplicación por `data-showtime-id`: un defecto real de la fuente

Se descubrió en vivo, inspeccionando el HTML real de Cinesa Proyecciones,
que **algunas versiones de idioma aparecen duplicadas byte a byte** en el
propio HTML de origen (mismo bloque "En V.O.S.E.", mismo
`data-showtime-id`, repetido dos veces seguidas) — un defecto de plantilla
de SensaCine, no un error de este parser. `_parse_showtimes_page` deduplica
por `data-showtime-id` dentro de cada cine para no producir horarios
repetidos en el esquema normalizado.

## Cines cubiertos

`CINEMAS` registra 4 cines (2 Cinesa + 2 Yelmo) verificados en vivo
mediante su identificador interno de SensaCine (`E0xxx`, visible en la URL
de cada ficha de cine); `DEFAULT_CINEMA_IDS` (los usados por la muestra por
defecto de `capture_sample`) se limita a **uno de cada cadena**, tal como
pedía el objetivo de la tarea — el resto queda disponible para que
`fetch_cinema_showtimes` los sirva bajo demanda sin tener que ampliar el
registro más adelante.

## Esto es una captura puntual de muestra, no un productor continuo

Igual que el resto de tareas 003-022, este módulo no tiene modo
`--interval-seconds` ni bucle, y no escribe en la capa Bronze particionada.

TODO(kafka): igual que el resto de productores de muestra, el punto donde
se conectaría un productor Kafka para un futuro barrido diario real
(`sweep_premieres`, o un barrido de `CINEMAS` completo) está marcado aquí
por consistencia, aunque no se despliega ningún scheduling en esta tarea.

## Handler Lambda (tarea 028): solo `sweep_premieres`, no `fetch_cinema_showtimes`

`lambda_handler` envuelve únicamente `sweep_premieres` (sin límite, no los
`DEFAULT_PREMIERES_LIMIT` de la muestra), pensado para el barrido diario
ligero que ya anticipaba su docstring. `fetch_cinema_showtimes` no tiene
handler propio: queda para que lo invoque bajo demanda el futuro servicio
conversacional (mismo criterio que `search_place` en
`bluesky_menciones_madrid.py` o `fetch_venue_agenda` en
`agenda_recintos_madrid.py`), no un schedule — la cartelera horaria de un
cine concreto solo tiene sentido cuando alguien pregunta por ese cine.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .bronze import BronzeWriter, now_madrid

logger = logging.getLogger(__name__)

SOURCE_NAME = "cartelera_cines_madrid"
DATASET_NAME = "cartelera_cines_estrenos"

DEFAULT_BASE_URL = "https://www.sensacine.com"

CINEMA_PATH_TEMPLATE = "/cines/cine/{sensacine_id}/"

PREMIERES_PATH = "/peliculas/estrenos/"

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "cartelera_cines_madrid_sample.json"

DEFAULT_SHOWTIMES_LIMIT_PER_CINEMA = 6

DEFAULT_PREMIERES_LIMIT = 6

MESES_ES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


@dataclass(frozen=True)
class Cinema:
    """Un cine de Madrid y su identificador interno en SensaCine."""

    cinema_id: str
    chain: str
    sensacine_id: str
    display_name: str


# Identificadores `E0xxx` verificados en vivo (visibles en la URL de la
# ficha de cada cine, p.ej. https://www.sensacine.com/cines/cine/E0402/).
CINEMAS: "dict[str, Cinema]" = {
    "cinesa_proyecciones": Cinema(
        cinema_id="cinesa_proyecciones",
        chain="cinesa",
        sensacine_id="E0402",
        display_name="Cinesa Proyecciones",
    ),
    "cinesa_mendez_alvaro": Cinema(
        cinema_id="cinesa_mendez_alvaro",
        chain="cinesa",
        sensacine_id="E0247",
        display_name="Cinesa Méndez Álvaro",
    ),
    "yelmo_ideal": Cinema(
        cinema_id="yelmo_ideal",
        chain="yelmo",
        sensacine_id="E0621",
        display_name="Yelmo Cines Ideal",
    ),
    "yelmo_la_vaguada": Cinema(
        cinema_id="yelmo_la_vaguada",
        chain="yelmo",
        sensacine_id="E0459",
        display_name="Yelmo Cines La Vaguada",
    ),
}

# Un cine por cadena, tal como pedía el objetivo de la tarea ("al menos un
# cine de Cinesa y uno de Yelmo").
DEFAULT_CINEMA_IDS = ["cinesa_proyecciones", "yelmo_ideal"]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_list(name: str, default: "list[str]") -> "list[str]":
    raw = os.environ.get(name)
    return [item.strip() for item in raw.split(",") if item.strip()] if raw else list(default)


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la captura, leída de variables de entorno.

    No requiere ninguna credencial: las páginas de SensaCine son públicas,
    sin autenticación.
    """

    base_url: str
    cinema_ids: "list[str]"
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            base_url=os.environ.get("SENSACINE_BASE_URL", DEFAULT_BASE_URL),
            cinema_ids=_env_list("CARTELERA_CINES_MADRID_CINEMA_IDS", DEFAULT_CINEMA_IDS),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 15.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
        )


def _fetch_html(config: CaptureConfig, path: str) -> str:
    """Petición GET con reintentos simples y backoff lineal, devuelve el HTML como texto."""
    url = urljoin(config.base_url, path)
    headers = {
        "Accept": "text/html",
        "User-Agent": "madrono-tfm-ingesta/0.1 (+madrono.ucm@gmail.com; academic research)",
    }
    last_exc: "Optional[Exception]" = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=config.timeout_seconds)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("Fallo al consultar %s (intento %d/%d): %s", url, attempt, config.max_retries, exc)
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * attempt)
    raise RuntimeError(f"No se pudo consultar {url} tras {config.max_retries} intentos") from last_exc


def _parse_theater_info(soup: BeautifulSoup) -> dict:
    """Extrae el bloque JSON-LD `schema.org/MovieTheater` de la ficha del cine.

    Devuelve un dict con todos los campos a `None` si la página no trae
    ningún bloque `MovieTheater` (defensivo: no debería ocurrir en una
    ficha de cine válida, pero un cambio de plantilla de SensaCine no debe
    tumbar la captura del resto de cines).
    """
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("@type") == "MovieTheater":
            address = data.get("address") or {}
            screen_count_raw = data.get("screenCount")
            return {
                "cinema_name": data.get("name"),
                "address": address.get("streetAddress"),
                "postal_code": address.get("postalCode"),
                "locality": address.get("addressLocality"),
                "screen_count": int(screen_count_raw) if screen_count_raw else None,
            }
    return {"cinema_name": None, "address": None, "postal_code": None, "locality": None, "screen_count": None}


def _parse_language_version(text: str) -> "Optional[str]":
    """De `"13 de agosto de 2026 -\\n    En Versión doblada"` extrae `"En Versión doblada"`.

    El nodo de texto de origen (`div.showtimes-version .text`) trae la
    fecha y la versión de idioma en dos líneas separadas por un salto de
    línea real dentro de un único nodo de texto, así que hace falta
    normalizar espacios/saltos de línea antes de separar por `" - "`.
    """
    normalized = re.sub(r"\s+", " ", text).strip()
    if " - " not in normalized:
        return normalized or None
    return normalized.split(" - ", 1)[1].strip() or None


def normalize_showtime(
    theater_info: dict,
    cinema: Cinema,
    movie_title: str,
    movie_url: str,
    language_version: "Optional[str]",
    showtime_span,
    captured_at: datetime,
) -> "Optional[dict]":
    """Normaliza una franja horaria (`span.showtimes-hour-item`) al esquema de este productor."""
    showtime_id = showtime_span.get("data-showtime-id")
    showtime_time = showtime_span.get("data-showtime-time")
    if not showtime_id or not showtime_time:
        return None
    experiences_raw = showtime_span.get("data-experiences")
    try:
        experiences = json.loads(experiences_raw) if experiences_raw else []
    except ValueError:
        experiences = []
    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "cinema_id": cinema.cinema_id,
        "chain": cinema.chain,
        "cinema_name": theater_info.get("cinema_name") or cinema.display_name,
        "address": theater_info.get("address"),
        "postal_code": theater_info.get("postal_code"),
        "locality": theater_info.get("locality"),
        "screen_count": theater_info.get("screen_count"),
        "movie_title": movie_title,
        "movie_url": movie_url,
        "language_version": language_version,
        "experiences": experiences,
        "showtime_datetime": showtime_time,
        "showtime_id": showtime_id,
        "captured_at": captured_at.isoformat(),
    }


def _parse_showtimes_page(html: str, cinema: Cinema, captured_at: datetime) -> "list[dict]":
    soup = BeautifulSoup(html, "html.parser")
    theater_info = _parse_theater_info(soup)

    records: "list[dict]" = []
    seen_showtime_ids: "set[str]" = set()
    for card in soup.select(".movie-card-theater"):
        title_el = card.select_one(".meta-title-link")
        if title_el is None:
            continue
        movie_title = title_el.get_text(strip=True)
        movie_url = urljoin(DEFAULT_BASE_URL, title_el.get("href") or "")

        for version in card.select(".showtimes-version"):
            text_el = version.select_one(".text")
            language_version = _parse_language_version(text_el.get_text(" ", strip=True)) if text_el else None
            for showtime_span in version.select(".showtimes-hour-item"):
                showtime_id = showtime_span.get("data-showtime-id")
                if not showtime_id or showtime_id in seen_showtime_ids:
                    # Deduplica bloques repetidos de la propia fuente (ver
                    # docstring del módulo, "Deduplicación por
                    # data-showtime-id").
                    continue
                record = normalize_showtime(
                    theater_info, cinema, movie_title, movie_url, language_version, showtime_span, captured_at
                )
                if record is None:
                    continue
                seen_showtime_ids.add(showtime_id)
                records.append(record)

    records.sort(key=lambda r: r["showtime_datetime"])
    return records


def fetch_cinema_showtimes(
    cinema_id: str,
    config: "Optional[CaptureConfig]" = None,
    captured_at: "Optional[datetime]" = None,
    html: "Optional[str]" = None,
    limit: "Optional[int]" = None,
) -> "list[dict]":
    """Cartelera completa de un cine concreto — modo bajo demanda.

    `html`, si se pasa, evita la descarga real (lo usan los tests); si no
    se pasa, hace su propia petición HTTP a la ficha del cine en SensaCine.
    """
    if cinema_id not in CINEMAS:
        raise ValueError(f"Cine desconocido: '{cinema_id}'. Cines disponibles: {sorted(CINEMAS)}")
    cinema = CINEMAS[cinema_id]
    captured_at = captured_at or now_madrid()
    if html is None:
        config = config or CaptureConfig.from_env()
        html = _fetch_html(config, CINEMA_PATH_TEMPLATE.format(sensacine_id=cinema.sensacine_id))

    records = _parse_showtimes_page(html, cinema, captured_at)
    if limit is not None:
        records = records[:limit]
    return records


def _parse_duration_minutes(text: str) -> "Optional[int]":
    match = re.search(r"(\d+)\s*h\s*(\d+)?\s*min", text)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2)) if match.group(2) else 0
        return hours * 60 + minutes
    match = re.search(r"(?<!\d)(\d+)\s*min", text)
    if match:
        return int(match.group(1))
    return None


def _parse_spanish_date(text: str) -> "Optional[str]":
    match = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", text.lower())
    if not match:
        return None
    day, month_name, year = match.groups()
    month = MESES_ES.get(month_name)
    if month is None:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def normalize_premiere(card, captured_at: datetime) -> "Optional[dict]":
    """Normaliza una tarjeta de película (`div.card.entity-card`) de la página de estrenos."""
    title_el = card.select_one(".meta-title-link")
    if title_el is None:
        return None
    info = card.select_one(".meta-body-info")
    date_el = info.select_one(".date") if info else None
    release_date = _parse_spanish_date(date_el.get_text(strip=True)) if date_el else None
    duration_minutes = _parse_duration_minutes(info.get_text(" ", strip=True)) if info else None
    genres = [span.get_text(strip=True) for span in info.select("span.dark-grey-link")] if info else []
    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "record_type": "estreno_semana",
        "movie_title": title_el.get_text(strip=True),
        "movie_url": urljoin(DEFAULT_BASE_URL, title_el.get("href") or ""),
        "release_date": release_date,
        "duration_minutes": duration_minutes,
        "genres": genres,
        "captured_at": captured_at.isoformat(),
    }


def sweep_premieres(
    config: "Optional[CaptureConfig]" = None,
    captured_at: "Optional[datetime]" = None,
    html: "Optional[str]" = None,
    limit: "Optional[int]" = None,
) -> "list[dict]":
    """Estrenos destacados de la semana en España — modo barrido programado ligero.

    SensaCine no publica una lista de estrenos filtrada por ciudad: es una
    única lista nacional (ver docstring del módulo).
    """
    captured_at = captured_at or now_madrid()
    if html is None:
        config = config or CaptureConfig.from_env()
        html = _fetch_html(config, PREMIERES_PATH)

    soup = BeautifulSoup(html, "html.parser")
    records = [normalize_premiere(card, captured_at) for card in soup.select(".card.entity-card")]
    records = [r for r in records if r is not None]
    if limit is not None:
        records = records[:limit]
    return records


def _write_json(records: "list[dict]", out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(
    config: CaptureConfig,
    out_path: Path,
    showtimes_limit_per_cinema: int,
    premieres_limit: int,
) -> Path:
    """Descarga, normaliza y guarda una muestra pequeña: cartelera de cada cine + estrenos.

    Igual que el resto de capturas de muestra del proyecto, esto NO escribe
    en la capa Bronze particionada ni deja nada programado: escribe un
    único fichero de muestra pequeño y fijo, pensado para commitearse como
    fixture.
    """
    captured_at = now_madrid()
    records: "list[dict]" = []
    for cinema_id in config.cinema_ids:
        cinema_records = fetch_cinema_showtimes(
            cinema_id, config=config, captured_at=captured_at, limit=showtimes_limit_per_cinema
        )
        logger.info("Horarios de muestra capturados para %s: %d", cinema_id, len(cinema_records))
        records.extend(cinema_records)

    premiere_records = sweep_premieres(config=config, captured_at=captured_at, limit=premieres_limit)
    logger.info("Estrenos de muestra capturados: %d", len(premiere_records))
    records.extend(premiere_records)

    _write_json(records, out_path)
    logger.info("Muestra escrita en %s (%d registros)", out_path, len(records))
    return out_path


def lambda_handler(event, context):
    """Punto de entrada AWS Lambda (tarea 028): estrenos de la semana completos a Bronze real."""
    config = CaptureConfig.from_env()
    records = sweep_premieres(config=config)
    logger.info("Estrenos capturados (captura completa): %d", len(records))
    writer = BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=DATASET_NAME)
    out_path = writer.write_batch(records)
    logger.info("Captura Lambda completada: %s", out_path)
    return {"dataset": DATASET_NAME, "records_written": len(records), "location": str(out_path)}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Captura puntual de muestra de la cartelera y horarios de cines de Madrid "
            "(Cinesa, Yelmo, vía SensaCine) más los estrenos de la semana. "
            "No admite ejecución en bucle ni programada."
        )
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_SAMPLE_PATH, help="Ruta del fichero de muestra a escribir")
    parser.add_argument(
        "--showtimes-limit-per-cinema",
        type=int,
        default=_env_int("CARTELERA_CINES_MADRID_SHOWTIMES_LIMIT", DEFAULT_SHOWTIMES_LIMIT_PER_CINEMA),
        help="Máximo de horarios por cine en la muestra",
    )
    parser.add_argument(
        "--premieres-limit",
        type=int,
        default=_env_int("CARTELERA_CINES_MADRID_PREMIERES_LIMIT", DEFAULT_PREMIERES_LIMIT),
        help="Máximo de estrenos en la muestra",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Nivel de logging (DEBUG, INFO, WARNING, ...)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = CaptureConfig.from_env()
    capture_sample(config, args.out, args.showtimes_limit_per_cinema, args.premieres_limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
