"""Captura de menciones públicas de lugares de Madrid en Bluesky (dos modos).

Bluesky es la red social elegida como señal de opiniones/eventos recientes
sobre un lugar (ver `documents/Memoria_TFM FV.docx`, apartado 6.7: «¿voy al
centro a las nueve de la noche del viernes?»). Se descartó Twitter/X (API de
pago, sin tier gratuito viable) y se investigaron dos alternativas: Bluesky
tiene una API pública de lectura (`app.bsky.feed.searchPosts`) sin API key ni
registro, con buena cobertura en español; Mastodon/Fediverso se descartó por
estar fragmentado por instancia sin búsqueda unificada, y CAMARA/Telefónica
Population Density Data se descartó por exigir partner comercial y consentimiento
por usuario (no autoservicio). Se eligió Bluesky.

## Dos modos, un mismo esquema normalizado

- `search_place(config, query, tags=None, lang="es", since=None, ...)`:
  búsqueda puntual por lugar/hashtag concretos. Pensada para que el
  **asistente conversacional** la invoque en tiempo de consulta cuando no
  tenga información de un lugar que el usuario menciona (p.ej. "¿qué tal
  está el Retiro hoy?" -> `search_place(config, "Retiro Madrid")`). Esta
  tarea implementa la función reutilizable, no la despliega como servicio.
- `search_district_sweep(config, districts, lang="es", since=None, ...)`:
  recorre una lista de distritos de Madrid con una búsqueda general por cada
  uno, más una tanda de búsquedas genéricas de eventos (términos positivos y
  negativos: conciertos, fiestas, quejas, aglomeraciones, incidencias,
  recomendaciones). Pensada para un **productor programado cada hora**
  (cuando exista scheduling, ver más abajo) que alimente una serie histórica
  agregada por zona y hora para entrenamiento, no para responder una
  pregunta puntual.

Ambos modos comparten `search_posts_raw`/`normalize_post`: mismo esquema de
salida, solo cambia `mode` (`"bajo_demanda"` / `"distrito_sweep"`) y
`match_term` (el lugar/hashtag o el distrito/término de evento que produjo
el resultado).

## Privacidad — restricción de diseño explícita del proyecto

La memoria (apartado 6.8) exige que «las señales de discurso social se
tratan de forma agregada, sin almacenar identificadores». Por eso
`normalize_post` **descarta explícitamente** todo el bloque `author` de la
respuesta de Bluesky (`did`, `handle`, `displayName`, `avatar`...) y el
`uri`/`cid` del post (el `uri` contiene el DID del autor: `at://did:plc:.../
app.bsky.feed.post/...`, así que conservarlo sería casi equivalente a
conservar el identificador). Se decidió **conservar el texto literal del
post** (`text`), no un hash: es contenido ya público (cualquiera puede
leerlo en la app de Bluesky) y es la señal que de verdad hace falta para una
futura clasificación de sentimiento en Silver/Gold (fuera de alcance aquí,
ver "Sin clasificación" más abajo); un hash lo haría inútil para ese fin. Lo
que se excluye no es el contenido del post, sino todo lo que identifique a
quién lo escribió. Se añade `post_hash` (SHA-256 truncado del texto) como
clave de deduplicación barata entre términos de búsqueda solapados, sin
depender del `uri` real.

## Sin clasificación de sentimiento

Este módulo captura y normaliza; no etiqueta "bueno"/"malo" ni hace ningún
análisis de sentimiento — esa es una transformación de Silver/Gold, fuera de
alcance de un productor de Bronze (mismo criterio que el resto de
`ingesta/capturas/`).

## Host real usado: `api.bsky.app`, no `public.api.bsky.app`

El endpoint documentado por el AT Protocol para lectura pública sin
autenticación es `https://public.api.bsky.app`. Se ha verificado en vivo
desde este entorno que **ese host específico bloquea con un 403 (WAF de
BunnyCDN, página HTML de error, no JSON) únicamente la llamada
`app.bsky.feed.searchPosts`**, mientras que otros métodos de solo lectura en
el mismo host (`app.bsky.actor.searchActors`,
`app.bsky.unspecced.getPopularFeedGenerators`, `/xrpc/_health`) responden
`200` con normalidad. El bloqueo persiste cambiando `User-Agent`,
añadiendo `Accept`/`Origin`/`Referer` de navegador, y con o sin parámetros —
apunta a un bloqueo de la ruta concreta para el rango de IP de esta EC2 (muy
probablemente porque `searchPosts` es el endpoint más costoso de servir y
más atractivo para scraping masivo, así que Bluesky/BunnyCDN lo protegen más
que el resto). En cambio, `https://api.bsky.app` (el mismo host que usa
`bsky.app`, la propia web de Bluesky, para sus peticiones al AppView) expone
la **misma operación `app.bsky.feed.searchPosts`, con la misma respuesta**,
y sí responde `200` desde este entorno, verificado en vivo repetidamente
durante esta sesión. Por eso este módulo usa `https://api.bsky.app` como
`BLUESKY_API_BASE_URL` por defecto, configurable por si en otro entorno
(p.ej. la máquina donde corra el asistente en producción) `public.api.bsky.app`
sí funciona o se prefiere por ser el host oficialmente documentado.

TODO(kafka): igual que el resto de productores de datos que cambian con el
tiempo (tráfico, calidad del aire, aforos...), el punto donde se conectaría
un productor Kafka para el modo `search_district_sweep` en su despliegue
cada hora está marcado aquí por consistencia, aunque en esta tarea no se
despliega ningún scheduling (ver "Sin despliegue" más abajo).

## Sin despliegue: ni cron, ni bucle, ni servicio

Esta tarea implementa ambas funciones y las ejecuta una vez para generar una
muestra pequeña versionada como fixture (`capture_sample`, invocado por
`main()`). A propósito, **no** hay modo `--interval-seconds`/`--daemon`, ni
se registra ningún cron/systemd timer: ni la invocación bajo demanda del
asistente ni el barrido programado cada hora se despliegan aquí — quedan
implementados y probados, listos para que un futuro `EnterWorktree`/tarea de
scheduling real (y, para el modo asistente, el propio servicio conversacional)
los invoque.

## Handler Lambda (tarea 027, lote 2/3): solo `search_district_sweep`, no `search_place`

`lambda_handler` envuelve únicamente el modo "barrido programado"
(`search_district_sweep`), con **todos** los distritos (`DEFAULT_DISTRICTS`,
21) y **todos** los términos de evento (`DEFAULT_EVENT_TERMS`, 6) — no los
subconjuntos truncados que usa `CaptureConfig.from_env()` por defecto para
la muestra pequeña (`BLUESKY_SAMPLE_DISTRICTS`/`BLUESKY_EVENT_TERMS`, ambas
pensadas solo para el fixture versionado). `search_place` (modo "bajo
demanda") no tiene handler propio: como dice el nombre, está pensado para
que lo invoque el futuro servicio conversacional en tiempo de consulta, no
un schedule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import requests

from .bronze import MADRID_TZ, BronzeWriter, now_madrid

logger = logging.getLogger(__name__)

SOURCE_NAME = "bluesky_menciones_madrid"
DATASET_NAME = "bluesky_menciones"

SEARCH_POSTS_PATH = "/xrpc/app.bsky.feed.searchPosts"

DEFAULT_API_BASE_URL = "https://api.bsky.app"

DEFAULT_SAMPLE_PATH = Path(__file__).parent / "samples" / "bluesky_menciones_madrid_sample.json"

MODE_SEARCH_PLACE = "bajo_demanda"
MODE_DISTRICT_SWEEP = "distrito_sweep"

# Los 21 distritos oficiales de Madrid, tal como los devuelve el mismo
# servicio ArcGIS (capa "DISTRITOS") que usa `barrios_distritos_madrid.py`
# (tarea 010): https://sigma.madrid.es/hosted/rest/services/CARTOGRAFIA/
# LIMITES_ADMINISTRATIVOS/MapServer/26/query?outFields=*&f=geojson
# (consultado en vivo durante esta sesión para no adivinar el nombre/grafía
# oficial, p.ej. "Fuencarral - El Pardo" con espacios alrededor del guion).
DEFAULT_DISTRICTS = [
    "Centro",
    "Arganzuela",
    "Retiro",
    "Salamanca",
    "Chamartín",
    "Tetuán",
    "Chamberí",
    "Fuencarral - El Pardo",
    "Moncloa - Aravaca",
    "Latina",
    "Carabanchel",
    "Usera",
    "Puente de Vallecas",
    "Moratalaz",
    "Ciudad Lineal",
    "Hortaleza",
    "Villaverde",
    "Villa de Vallecas",
    "Vicálvaro",
    "San Blas - Canillejas",
    "Barajas",
]

# Términos razonables para la búsqueda genérica de "eventos Madrid" del
# barrido programado: mezcla deliberada de señales positivas (ocio,
# recomendaciones) y negativas (quejas, incidencias, aglomeraciones), tal
# como pide el objetivo de la tarea ("buenos o malos"). La clasificación en
# sí no ocurre aquí (ver docstring, "Sin clasificación").
DEFAULT_EVENT_TERMS = [
    "concierto",
    "fiesta",
    "recomendación",
    "queja",
    "aglomeración",
    "incidencia",
]

# Lugares de ejemplo para el modo "bajo demanda" en la muestra de esta
# tarea: simula lo que preguntaría un usuario del asistente conversacional.
DEFAULT_PLACE_QUERIES = [
    "Puerta del Sol",
    "Parque del Retiro",
    "Malasaña",
]


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _env_list(name: str, default: "list[str]") -> "list[str]":
    raw = os.environ.get(name)
    return [item.strip() for item in raw.split("|") if item.strip()] if raw else list(default)


@dataclass(frozen=True)
class CaptureConfig:
    """Configuración de la captura, leída de variables de entorno.

    No requiere ninguna credencial: `app.bsky.feed.searchPosts` es un
    endpoint de lectura pública (ver docstring del módulo).
    """

    api_base_url: str
    lang: str
    limit_per_query: int
    place_queries: "list[str]"
    districts: "list[str]"
    event_terms: "list[str]"
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float

    @classmethod
    def from_env(cls) -> "CaptureConfig":
        return cls(
            api_base_url=os.environ.get("BLUESKY_API_BASE_URL", DEFAULT_API_BASE_URL),
            lang=os.environ.get("BLUESKY_LANG", "es"),
            limit_per_query=_env_int("BLUESKY_LIMIT_PER_QUERY", 5),
            place_queries=_env_list("BLUESKY_SAMPLE_PLACES", DEFAULT_PLACE_QUERIES),
            districts=_env_list("BLUESKY_SAMPLE_DISTRICTS", DEFAULT_DISTRICTS[:3]),
            event_terms=_env_list("BLUESKY_EVENT_TERMS", DEFAULT_EVENT_TERMS[:2]),
            timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 15.0),
            max_retries=_env_int("HTTP_MAX_RETRIES", 3),
            retry_backoff_seconds=_env_float("HTTP_RETRY_BACKOFF_SECONDS", 2.0),
        )


def _get_json_with_retries(config: CaptureConfig, url: str, params: dict) -> dict:
    """Petición GET con reintentos simples y backoff lineal, devuelve JSON."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "madrono-tfm-ingesta/0.1 (+madrono.ucm@gmail.com; academic research)",
    }
    last_exc: Optional[Exception] = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=config.timeout_seconds)
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


def _hash_text(text: str) -> str:
    """Hash corto y estable del texto, usado como clave de deduplicación sin `uri`."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _build_query(base_term: str, extra_terms: "Optional[Iterable[str]]" = None) -> str:
    parts = [base_term, *(extra_terms or [])]
    return " ".join(p for p in parts if p)


def normalize_post(raw_post: dict, match_term: str, mode: str, captured_at: datetime) -> dict:
    """Normaliza un post crudo de `searchPosts` al esquema mínimo agregable.

    Descarta a propósito `author` y `uri`/`cid` (identifican al autor, ver
    docstring del módulo, sección "Privacidad"). Conserva el texto y
    contadores públicos tal cual.
    """
    record = raw_post.get("record") or {}
    text = record.get("text", "") or ""
    langs = record.get("langs") or []
    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "mode": mode,
        "match_term": match_term,
        "post_hash": _hash_text(text),
        "text": text,
        "lang": langs[0] if langs else None,
        "created_at": record.get("createdAt"),
        "indexed_at": raw_post.get("indexedAt"),
        "like_count": raw_post.get("likeCount"),
        "repost_count": raw_post.get("repostCount"),
        "reply_count": raw_post.get("replyCount"),
        "quote_count": raw_post.get("quoteCount"),
        "captured_at": captured_at.astimezone(MADRID_TZ).isoformat(),
    }


def search_posts_raw(
    config: CaptureConfig,
    q: str,
    lang: "Optional[str]" = None,
    since: "Optional[str]" = None,
    until: "Optional[str]" = None,
    limit: "Optional[int]" = None,
) -> "list[dict]":
    """Llama a `app.bsky.feed.searchPosts` y devuelve la lista cruda de `posts`.

    `since`/`until` son timestamps ISO-8601 tal como los espera la API
    (p.ej. `"2026-08-01T00:00:00.000Z"`). Sin autenticación.
    """
    params: dict = {"q": q, "limit": limit or config.limit_per_query}
    if lang:
        params["lang"] = lang
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    url = config.api_base_url.rstrip("/") + SEARCH_POSTS_PATH
    payload = _get_json_with_retries(config, url, params)
    return payload.get("posts") or []


def search_place(
    config: CaptureConfig,
    query: str,
    tags: "Optional[list[str]]" = None,
    lang: str = "es",
    since: "Optional[str]" = None,
    until: "Optional[str]" = None,
    limit: "Optional[int]" = None,
    captured_at: "Optional[datetime]" = None,
) -> "list[dict]":
    """Búsqueda puntual por lugar/hashtag — modo "bajo demanda" del asistente.

    Pensada para invocarse en tiempo de consulta cuando el asistente no
    tenga información concreta de un lugar que el usuario menciona.
    """
    captured_at = captured_at or now_madrid()
    q = _build_query(query, [f"#{tag.lstrip('#')}" for tag in (tags or [])])
    raw_posts = search_posts_raw(config, q, lang=lang, since=since, until=until, limit=limit)
    return [
        normalize_post(post, match_term=query, mode=MODE_SEARCH_PLACE, captured_at=captured_at)
        for post in raw_posts
    ]


def search_district_sweep(
    config: CaptureConfig,
    districts: "list[str]",
    lang: str = "es",
    since: "Optional[str]" = None,
    until: "Optional[str]" = None,
    limit: "Optional[int]" = None,
    event_terms: "Optional[list[str]]" = None,
    captured_at: "Optional[datetime]" = None,
) -> "list[dict]":
    """Barrido general por distrito + eventos — modo "programado cada hora".

    Una búsqueda por cada distrito de `districts` (combinado con "Madrid"
    para evitar falsos positivos con distritos homónimos de otras ciudades),
    más una búsqueda por cada término de `event_terms` (por defecto
    `config.event_terms`) combinado con "Madrid". Pensada para nutrir una
    serie histórica agregada por zona y hora, no para responder una
    pregunta puntual.
    """
    captured_at = captured_at or now_madrid()
    event_terms = event_terms if event_terms is not None else config.event_terms
    records: "list[dict]" = []

    for district in districts:
        q = _build_query(district, ["Madrid"])
        raw_posts = search_posts_raw(config, q, lang=lang, since=since, until=until, limit=limit)
        records.extend(
            normalize_post(post, match_term=district, mode=MODE_DISTRICT_SWEEP, captured_at=captured_at)
            for post in raw_posts
        )

    for term in event_terms:
        q = _build_query("Madrid", [term])
        raw_posts = search_posts_raw(config, q, lang=lang, since=since, until=until, limit=limit)
        records.extend(
            normalize_post(
                post, match_term=f"eventos:{term}", mode=MODE_DISTRICT_SWEEP, captured_at=captured_at
            )
            for post in raw_posts
        )

    return records


def _write_json(records: "list[dict]", out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(out_path)


def capture_sample(config: CaptureConfig, out_path: Path) -> Path:
    """Ejecuta ambos modos de verdad y guarda el resultado como un único dataset.

    Igual que `aforos_peatones_bicicletas_madrid.py` (tarea 013), ambos
    modos se guardan como un único dataset con un campo `mode` para
    distinguirlos, no como dos ficheros separados: quien solo necesite un
    modo puede filtrar por `mode`.
    """
    captured_at = now_madrid()
    records: "list[dict]" = []

    for query in config.place_queries:
        records.extend(search_place(config, query, lang=config.lang, captured_at=captured_at))

    records.extend(
        search_district_sweep(config, config.districts, lang=config.lang, captured_at=captured_at)
    )

    logger.info("Posts de muestra capturados: %d", len(records))
    _write_json(records, out_path)
    logger.info("Muestra escrita en %s", out_path)
    return out_path


def lambda_handler(event, context):
    """Punto de entrada AWS Lambda (tarea 027): barrido completo por distrito a Bronze real.

    Solo el modo `search_district_sweep`, con la lista completa de distritos
    y términos de evento (ver docstring del módulo, "Handler Lambda"), no la
    muestra truncada que usa `CaptureConfig.from_env()` por defecto.
    """
    config = replace(CaptureConfig.from_env(), districts=DEFAULT_DISTRICTS, event_terms=DEFAULT_EVENT_TERMS)
    records = search_district_sweep(
        config, config.districts, lang=config.lang, event_terms=config.event_terms
    )
    logger.info("Menciones capturadas (barrido completo por distrito): %d", len(records))
    writer = BronzeWriter(os.environ["BRONZE_BASE_PATH"], dataset=DATASET_NAME)
    out_path = writer.write_batch(records)
    logger.info("Captura Lambda completada: %s", out_path)
    return {"dataset": DATASET_NAME, "records_written": len(records), "location": str(out_path)}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Captura puntual de muestra de menciones de Bluesky sobre lugares de Madrid, "
            "combinando el modo 'bajo demanda' (search_place) y el modo 'barrido por distrito' "
            "(search_district_sweep). No admite ejecución en bucle ni programada."
        )
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_SAMPLE_PATH, help="Ruta del fichero de muestra a escribir")
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Nivel de logging (DEBUG, INFO, WARNING, ...)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = CaptureConfig.from_env()
    capture_sample(config, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
