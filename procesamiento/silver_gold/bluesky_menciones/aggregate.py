"""Agregación Silver -> Gold del dataset `bluesky_menciones`: número de
menciones por término de búsqueda (lugar/distrito/evento), modo y hora.

## Clave de agregación: `(mode, match_term, fecha, hora)`

El enunciado pide "conteo de menciones por lugar/distrito y periodo
(día/hora, según la cadencia real del productor) separado por mode". Se
agrupa por hora, no solo por día: `search_district_sweep` (modo
`"distrito_sweep"`) está pensado para un productor programado **cada hora**
(ver docstring de `ingesta/capturas/bluesky_menciones_madrid.py`, "Dos
modos, un mismo esquema normalizado"), la misma cadencia que ya usan
`trafico`/`transporte_publico_emt`/`bicimad`/`aparcamientos`/`calidad_aire`/
`meteorologia`/`aforos_peatones_bicicletas` -- a diferencia de `ruido`/
`agenda_eventos`, que agregan solo por día porque su fuente no tiene ninguna
resolución horaria real, aquí cada post de Bluesky trae un `created_at` con
resolución de segundos, así que agregar por hora no es una aproximación
forzada, es la granularidad natural de la fuente.

`mode` entra en la clave porque el enunciado lo pide explícitamente
("separado por mode"): mezclar menciones del modo bajo demanda (búsquedas
puntuales del asistente conversacional, no representativas de ninguna serie
temporal real) con las del barrido programado (pensadas para alimentar una
serie histórica) produciría un conteo sin significado agregado consistente.

`match_term` es el lugar (modo `bajo_demanda`) o distrito/término de evento
(modo `distrito_sweep`) que el enunciado pide como dimensión "lugar/distrito"
-- ver `transform.py` para el razonamiento de por qué es la única dimensión
geográfica/temática disponible en este dataset (Bluesky no publica ninguna
coordenada del post).

## Periodo: se deriva de `created_at` (cuándo se escribió el post), no de `ingested_at`

La búsqueda de Bluesky (`app.bsky.feed.searchPosts`) no está acotada a "solo
posts de la última hora" -- puede devolver posts de días atrás que
simplemente coinciden con el término buscado (ver la muestra real: posts
capturados el mismo `ingested_at` con `created_at` repartidos en un rango de
horas). Agregar por `ingested_at` (cuándo corrió el barrido) mezclaría en el
mismo bucket menciones de momentos muy distintos, y perdería la señal
temporal real de "cuándo se habló de este lugar" -- que es la pregunta que
tiene sentido responder con esta agregación (ver memoria del TFM, apartado
6.7: la señal de Bluesky sirve para inferir qué está pasando en un lugar en
un momento dado, no cuándo se ejecutó el scraper). Por eso, igual que
`cartelera_cines_estrenos` usa `showtime_datetime` (el momento real de la
sesión) en vez de `ingested_at`, y `agenda_eventos` usa `start_datetime` (el
momento real del evento), aquí se usa `created_at` (el momento real de la
publicación).

## `mentions_count` (posts distintos) vs. `samples_count` (filas Silver)

Igual que el resto del patrón, `samples_count` es el número de filas Silver
en el bucket (incluye reingestas entre ejecuciones distintas del productor:
`transform.bronze_to_silver` solo deduplica duplicados exactos dentro del
mismo lote, no entre lotes -- ver ese módulo). `mentions_count` es la
magnitud principal de este dataset: el número de `post_hash` **distintos**
en el bucket, para que una reingesta del mismo post en un barrido posterior
no se cuente dos veces como si fueran dos menciones distintas.

## Métricas de engagement agregadas (no es análisis de sentimiento)

`total_like_count`/`total_repost_count`/`total_reply_count`/
`total_quote_count` son sumas de contadores públicos que Bluesky ya expone
por post (`normalize_post`, ver el módulo de ingesta) -- no es ningún
análisis de sentimiento ni clasificación de texto (fuera de alcance de esta
tarea, ver enunciado y docstring de `ingesta/capturas/bluesky_menciones_madrid.py`,
sección "Sin clasificación"), solo una suma numérica de campos que ya
existen en Silver, igual que el resto del patrón resume sus magnitudes
numéricas (`avg_intensity_vph`, `total_count`...). Da una señal barata de
"cuánta atención" recibió un lugar/término en el periodo, útil para el
asistente conversacional sin tener que releer el texto de cada post.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def aggregate_silver_to_gold(records: "list[dict]", processed_at: datetime) -> "list[dict]":
    """Agrega registros Silver de `bluesky_menciones` por modo, término, día y hora."""
    buckets: "dict[tuple[str, str, str, int], list[dict]]" = {}

    for record in records:
        created_at = _parse_iso(record.get("created_at"))
        mode = record.get("mode")
        match_term = record.get("match_term")
        if created_at is None or not mode or not match_term:
            continue
        key = (mode, match_term, created_at.date().isoformat(), created_at.hour)
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (mode, match_term, date_str, hour), bucket in sorted(buckets.items()):
        created_ats = sorted(
            t for t in (_parse_iso(r.get("created_at")) for r in bucket) if t is not None
        )
        distinct_post_hashes = {r.get("post_hash") for r in bucket if r.get("post_hash")}
        langs = sorted({r.get("lang") for r in bucket if r.get("lang")})

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "mode": mode,
                "match_term": match_term,
                "date": date_str,
                "hour": hour,
                "samples_count": len(bucket),
                "mentions_count": len(distinct_post_hashes),
                "langs": langs,
                "total_like_count": sum(r.get("like_count") or 0 for r in bucket),
                "total_repost_count": sum(r.get("repost_count") or 0 for r in bucket),
                "total_reply_count": sum(r.get("reply_count") or 0 for r in bucket),
                "total_quote_count": sum(r.get("quote_count") or 0 for r in bucket),
                "first_created_at": created_ats[0].isoformat() if created_ats else None,
                "last_created_at": created_ats[-1].isoformat() if created_ats else None,
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
