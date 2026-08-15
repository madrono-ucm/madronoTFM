"""Captura puntual de afluencia (popularidad tipo Google) de lugares de Madrid.

Descarga, para una muestra pequeña de lugares conocidos de Madrid (Puerta
del Sol, Parque del Retiro, Mercado de San Miguel...), la popularidad en
vivo (`live_pct`) si está disponible en el momento de la captura y el patrón
típico de afluencia por día de la semana y hora (`typical_by_hour`), para que
el asistente conversacional pueda responder tanto «¿está muy lleno esto
ahora?» como «¿un viernes a las 21h suele haber mucha gente aquí?» (ver
`documents/Memoria_TFM FV.docx`, apartado 6.1 «Contexto urbano»: afluencia de
lugares públicos).

## Zona gris deliberada, solo admisible en el marco académico de este TFM

**Léase antes de tocar este módulo.** No existe ninguna API oficial que
venda este dato concreto (afluencia estimada de un lugar público, en vivo y
por patrón habitual); Google no lo expone en su API oficial de pago (Places
API). La única vía conocida y con algo de mantenimiento es la librería
[`m-wrzr/populartimes`](https://github.com/m-wrzr/populartimes): usa la API
oficial de Google Places (Find Place, de pago con tier gratuito mensual)
solo para localizar el lugar (`place_id`), y obtiene el dato de popularidad
real haciendo **scraping de un endpoint interno no documentado de Google**
(`google.*/search?tbm=map...`), parseando por posición un JSON sin contrato
público — es intrínsecamente frágil (puede romperse sin aviso si Google
cambia su página) y su propio issue más comentado en GitHub es, literalmente,
sobre posible violación de las condiciones de uso de Google.

Tal y como reconoce explícitamente la memoria de este TFM (apartado 6.8):
esta fuente concreta usa «librerías de código abierto» en una «zona gris»
respecto a las condiciones de uso de terceros, **admisible únicamente en el
marco académico de este trabajo**. En producción, este productor se
sustituiría por un proveedor comercial con licencia sobre este mismo tipo de
dato (p.ej. [BestTime.app](https://besttime.app) o similar) — no se integra
aquí, solo se deja constancia de la alternativa.

Por eso este módulo, a propósito, **no reimplementa el scraping a mano**:
usa `populartimes` tal cual como dependencia externa (ver
`ingesta/requirements.txt`, instalada desde el repositorio de GitHub porque
no está publicada en PyPI — comprobado en vivo durante esta sesión,
`https://pypi.org/pypi/populartimes/json` devuelve `404`).

## Esto es una captura puntual de muestra, no un productor continuo

Igual que las tareas 003-008, este módulo **no tiene modo `--interval-seconds`
ni bucle**, y no escribe en la capa Bronze particionada: escribe un único
fichero de muestra pequeño (como mucho `MADRID_PLACES_SAMPLE_SIZE`, 5 por
defecto) pensado para commitearse como fixture. A diferencia de esas tareas,
aquí la razón no es solo "todavía no hay infraestructura" — es también que
raspar Google en bucle agravaría el problema de zona gris descrito arriba;
un futuro productor continuo real de este dato debería usar el proveedor
comercial mencionado, no esta librería.

## Cómo funciona (dos llamadas por lugar)

1. **Resolución del lugar**: `resolve_place_id` llama a la API oficial
   "Find Place from Text" de Google Places
   (`https://maps.googleapis.com/maps/api/place/findplacefromtext/json`) con
   el nombre del lugar (p.ej. "Puerta del Sol, Madrid") para obtener su
   `place_id`, nombre canónico, dirección y coordenadas. Esta llamada sí es
   100% oficial y de pago con tier gratuito.
2. **Popularidad**: `fetch_populartimes` llama a
   `populartimes.get_id(api_key, place_id)`, que internamente combina la API
   de detalles de Google (oficial) con el scraping no documentado descrito
   arriba, y devuelve `current_popularity` (0-100, puede faltar si Google no
   tiene datos suficientes para ese lugar) y `populartimes` (patrón por día
   de la semana, 24 valores 0-100 por día).

`normalize_record` combina ambas respuestas en el esquema mínimo de este
productor.

## Autenticación (API key gratuita de Google Cloud)

Se necesita una **API key de Google Maps Platform** con la "Places API"
habilitada. Se obtiene gratis (tier mensual gratuito, sin necesidad de
tarjeta de crédito para el nivel usado por esta muestra) en
<https://console.cloud.google.com/google/maps-apis/credentials>: crear un
proyecto, habilitar "Places API", y crear una clave de API. Se lee de la
variable de entorno `GOOGLE_MAPS_API_KEY`, nunca hardcodeada; sin ella,
`main()` falla explícitamente con un mensaje claro. Los tests de este módulo
no la necesitan: usan una respuesta de ejemplo de la librería, no la red.

## Nota sobre el intento de captura real en esta sesión

Este entorno **no tiene configurada ninguna `GOOGLE_MAPS_API_KEY`** (no hay
forma de completar el registro de una cuenta de Google Cloud de forma
autónoma en este pipeline, igual que el bloqueo de verificación por email de
la tarea 003 con la EMT). Se verificó igualmente, en vivo y desde este
entorno, que la librería `populartimes` se instala correctamente desde
GitHub y que su código realiza peticiones HTTP reales: con una clave de
prueba inválida, `populartimes.get_id(...)` lanza
`populartimes.crawler.PopulartimesException` con el mensaje exacto
`('Google Places REQUEST_DENIED', 'Request was denied, the API key is
invalid.')` — el fallo esperado por falta de credencial válida, no un error
de la librería en sí ni de este módulo. Por eso el fixture commiteado en
`ingesta/capturas/samples/afluencia_lugares_madrid_sample.json` se generó a
mano con datos de ejemplo (mock) que siguen exactamente el esquema que
produce `normalize_record` (cada registro lleva `"is_mock": true` para que
quede explícito en el propio dato, no solo en esta nota, que no proviene de
una captura en vivo). El código queda completo y listo para ejecutarse tal
cual el día que alguien configure una `GOOGLE_MAPS_API_KEY` real.

TODO(kafka): igual que el resto de productores de muestra (tareas 003-008),
el punto donde se conectaría un productor Kafka está marcado aquí por
consistencia, aunque dado el carácter de zona gris de esta fuente (ver
arriba), un productor continuo real debería migrar al proveedor comercial
mencionado antes de conectarse a ningún broker en producción.

## Handler Lambda (tarea 027, lote 2/3): solo el patrón típico, no la popularidad "en vivo"

`lambda_handler`/`capture_typical_patterns` implementan el productor
programado, pero **deliberadamente excluyen `live_pct`** (siempre `None`
en sus registros, vía `normalize_record(..., include_live=False)`): la
popularidad "en vivo" solo tiene sentido en el instante exacto en que
alguien pregunta "¿está muy lleno esto ahora?" — capturarla en un barrido
programado (p.ej. cada hora) produciría un dato ya obsoleto para cuando el
asistente lo necesite. Esa pregunta puntual sigue siendo responsabilidad
de una futura invocación bajo demanda (mismo patrón que `search_place` en
`bluesky_menciones_madrid.py`, tarea 016), no de este handler. El patrón
típico por hora/día, en cambio, cambia poco de una semana a otra, así que
sí encaja con una captura programada periódica (p.ej. semanal) que lo
mantenga fresco en Bronze.
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

from .bronze import MADRID_TZ, BronzeWriter, now_madrid

logger = logging.getLogger(__name__)

SOURCE_NAME = "google_populartimes"
DATASET_NAME = "afluencia_lugares_patron_tipico"

FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "afluencia_lugares_madrid_sample.json"

# Muestra de 5 lugares conocidos y muy visitados de Madrid (objetivo de la
# tarea: "3-5, p.ej. Puerta del Sol, Parque del Retiro, Mercado de San
# Miguel..."). Son búsquedas de texto libre, tal como las resolvería
# cualquier usuario en Google Maps; `resolve_place_id` las convierte en un
# `place_id` concreto.
DEFAULT_PLACE_QUERIES = [
    "Puerta del Sol, Madrid",
    "Parque del Retiro, Madrid",
    "Mercado de San Miguel, Madrid",
    "Museo del Prado, Madrid",
    "Plaza Mayor de Madrid",
]

# Días tal como los devuelve `populartimes` (nombres en inglés, lunes primero)
# normalizados a las claves en español que usa el resto de este proyecto.
_DAY_KEY_ES = {
    "Monday": "lunes",
    "Tuesday": "martes",
    "Wednesday": "miercoles",
    "Thursday": "jueves",
    "Friday": "viernes",
    "Saturday": "sabado",
    "Sunday": "domingo",
}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la captura, leída de variables de entorno.

    `api_key` es la única credencial: una Google Maps API key gratuita (ver
    docstring del módulo, sección "Autenticación").
    """

    api_key: str
    place_queries: "list[str]"
    sample_size: int
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        raw_queries = os.environ.get("MADRID_PLACES_QUERIES")
        place_queries = (
            [q.strip() for q in raw_queries.split("|") if q.strip()]
            if raw_queries
            else list(DEFAULT_PLACE_QUERIES)
        )
        return cls(
            api_key=os.environ.get("GOOGLE_MAPS_API_KEY", ""),
            place_queries=place_queries,
            sample_size=_env_int("MADRID_PLACES_SAMPLE_SIZE", len(DEFAULT_PLACE_QUERIES)),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 30.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
        )


def _get_json_with_retries(config: CaptureConfig, url: str, params: dict) -> dict:
    """Petición GET con reintentos simples y backoff lineal, devuelve JSON."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.get(url, params=params, timeout=config.timeout_seconds)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Fallo al consultar %s (intento %d/%d): %s", url, attempt, config.max_retries, exc
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_backoff_seconds * attempt)
    raise RuntimeError(f"No se pudo consultar {url} tras {config.max_retries} intentos") from last_exc


def _pick_candidate(payload: dict, query: str) -> Optional[dict]:
    """Extrae el primer candidato de una respuesta de "Find Place from Text".

    Función pura (sin red), separada de `resolve_place_id` para poder
    testear el manejo de "sin resultados" con una respuesta de ejemplo, sin
    necesidad de mockear peticiones HTTP.
    """
    status = payload.get("status")
    if status != "OK":
        logger.warning("Find Place sin resultado para %r: status=%s", query, status)
        return None
    candidates = payload.get("candidates") or []
    if not candidates:
        return None
    return candidates[0]


def resolve_place_id(config: CaptureConfig, query: str) -> Optional[dict]:
    """Resuelve un nombre de lugar a su `place_id` de Google, vía la API oficial "Find Place".

    Devuelve `None` si Google no encuentra ningún candidato para la
    búsqueda (no debería ocurrir con las búsquedas de la muestra por
    defecto, pero se comprueba por robustez).
    """
    params = {
        "input": query,
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address,geometry",
        "key": config.api_key,
    }
    payload = _get_json_with_retries(config, FIND_PLACE_URL, params)
    return _pick_candidate(payload, query)


def fetch_populartimes(config: CaptureConfig, place_id: str) -> dict:
    """Obtiene popularidad en vivo y patrón habitual para un `place_id` ya resuelto.

    Delega en `populartimes.get_id`, que combina la API oficial de detalles
    de Google con el scraping no documentado descrito en el docstring del
    módulo. No se reimplementa aquí: se usa la librería tal cual.
    """
    import populartimes  # import perezoso: solo hace falta para captura real, no para los tests

    return populartimes.get_id(config.api_key, place_id)


def _typical_by_hour(raw_populartimes: Optional[list]) -> Optional[dict]:
    """Normaliza la lista `populartimes` de la librería a un dict `día_es -> [24 valores]`.

    Devuelve `None` si la fuente no tiene ningún patrón habitual para este
    lugar (Google no siempre tiene datos suficientes, sobre todo para
    lugares al aire libre poco "comerciales" como un parque).
    """
    if not raw_populartimes:
        return None
    by_day = {}
    for day in raw_populartimes:
        day_name_en = day.get("name")
        day_key = _DAY_KEY_ES.get(day_name_en)
        if day_key is None:
            continue
        by_day[day_key] = list(day.get("data") or [])
    return by_day or None


def normalize_record(
    raw: dict, query: str, captured_at: datetime, is_mock: bool = False, include_live: bool = True
) -> dict:
    """Normaliza la respuesta combinada (Find Place + `populartimes.get_id`) al esquema mínimo.

    `include_live=False` fuerza `live_pct` a `None`: lo usa
    `capture_typical_patterns` (handler Lambda, tarea 027), que solo
    captura el patrón habitual programado, no la popularidad "en vivo" del
    instante de la captura (ver docstring del módulo, sección "Handler
    Lambda").
    """
    coordinates = raw.get("coordinates") or {}
    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "place_id": raw.get("id"),
        "name": raw.get("name"),
        "query": query,
        "address": raw.get("address"),
        "location": {
            "lat": coordinates.get("lat"),
            "lon": coordinates.get("lng"),
            "srid": "EPSG:4326",
        },
        "captured_at": captured_at.astimezone(MADRID_TZ).isoformat(),
        "live_pct": raw.get("current_popularity") if include_live else None,
        "typical_by_hour": _typical_by_hour(raw.get("populartimes")),
        "is_mock": is_mock,
    }


def _write_json(records: "list[dict]", out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Resuelve, descarga, normaliza y guarda una muestra pequeña de afluencia de lugares.

    Igual que las tareas 009-011, esto NO escribe en la capa Bronze
    particionada ni deja nada programado: escribe un único fichero de
    muestra pequeño y fijo (como mucho `config.sample_size` lugares),
    pensado para commitearse como fixture.
    """
    if not config.api_key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY no está configurada. Ver docstring del módulo, "
            "sección 'Autenticación', para obtener una clave gratuita."
        )

    captured_at = now_madrid()
    records = []
    for query in config.place_queries[: config.sample_size]:
        candidate = resolve_place_id(config, query)
        if candidate is None:
            logger.warning("Sin place_id para %r, se omite del lote", query)
            continue
        place_id = candidate["place_id"]
        raw = fetch_populartimes(config, place_id)
        records.append(normalize_record(raw, query, captured_at))
    logger.info("Lugares de muestra capturados: %d", len(records))

    _write_json(records, out_path)
    logger.info("Muestra escrita en %s", out_path)
    return out_path


def capture_typical_patterns(config: CaptureConfig) -> "list[dict]":
    """Captura el patrón típico (no la popularidad en vivo) de TODOS `config.place_queries`.

    A diferencia de `capture_sample` (que corta a `config.sample_size` y
    conserva `live_pct`), esto es la captura completa pensada para el
    handler Lambda (tarea 027): recorre todos los lugares configurados y
    fuerza `live_pct` a `None` en cada registro (ver docstring del módulo,
    sección "Handler Lambda").
    """
    if not config.api_key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY no está configurada. Ver docstring del módulo, "
            "sección 'Autenticación', para obtener una clave gratuita."
        )

    captured_at = now_madrid()
    records = []
    for query in config.place_queries:
        candidate = resolve_place_id(config, query)
        if candidate is None:
            logger.warning("Sin place_id para %r, se omite del lote", query)
            continue
        place_id = candidate["place_id"]
        raw = fetch_populartimes(config, place_id)
        records.append(normalize_record(raw, query, captured_at, include_live=False))
    logger.info("Patrones típicos capturados (captura completa): %d", len(records))
    return records


def lambda_handler(event, context):
    """Punto de entrada AWS Lambda (tarea 027): captura completa a Bronze real."""
    config = CaptureConfig.from_env()
    records = capture_typical_patterns(config)
    writer = BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=DATASET_NAME)
    out_path = writer.write_batch(records)
    logger.info("Captura Lambda completada: %s", out_path)
    return {"dataset": DATASET_NAME, "records_written": len(records), "location": str(out_path)}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Captura puntual de muestra de afluencia (popularidad en vivo y patrón "
            "habitual) de lugares conocidos de Madrid, vía la librería populartimes. "
            "No admite ejecución en bucle ni programada."
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
