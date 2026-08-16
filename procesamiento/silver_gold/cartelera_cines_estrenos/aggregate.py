"""Agregación Silver -> Gold del dataset `cartelera_cines_estrenos`: número
de sesiones por película, cine y día.

## Por qué no el patrón `(id, fecha, hora)` del resto de datasets

Los ocho datasets anteriores del patrón (`trafico`, `transporte_publico_emt`,
`bicimad`, `aparcamientos`, `calidad_aire`, `meteorologia`, `ruido`,
`aforos_peatones_bicicletas`) son series temporales de una magnitud numérica
(intensidad, ocupación, un contaminante, LAeq...) medida repetidamente en el
tiempo: agregar por hora tiene sentido porque hay muchas lecturas por hora
que promediar/sumar. Silver de este dataset, en cambio, es un **catálogo de
sesiones de cine**: cada fila ya es un hecho discreto y único (una sesión
concreta, identificada por `showtime_id`), no una medida repetida. No hay
ninguna magnitud numérica que promediar -- lo único que tiene sentido contar
es **cuántas sesiones hay**, agrupadas por las dimensiones que interesan a
un consumidor de este catálogo: qué película, en qué cine, qué día.

## Clave de agregación: `(movie_url, cinema_id, fecha)`

Se agrupa por película + cine + día (no por hora: el enunciado sugería
"número de sesiones por película/día, o por cine/día" como agregación de
día completo, no de franja horaria -- una cartelera se consulta típicamente
"qué ponen hoy", no "qué ponen a las 17h"). Incluir **ambas** dimensiones
(película y cine) en la clave, en vez de solo una, dijo el enunciado como
alternativa ("p.ej. ... o ..."); se decidió incluir las dos a la vez porque
así un consumidor de Gold puede obtener cualquiera de las dos vistas sin
perder información:

- "¿Cuántas sesiones tiene la película X hoy (en todos los cines)?" ->
  sumar `sessions_count` de todas las filas con ese `movie_url` y `date`.
- "¿Cuántas sesiones hay hoy en el cine Y (de cualquier película)?" ->
  sumar `sessions_count` de todas las filas con ese `cinema_id` y `date`.

Perder cualquiera de las dos dimensiones en la propia agregación de Gold
haría irreversible la otra vista (no se puede recuperar el desglose por cine
a partir de un total ya sumado por película, y viceversa) -- mismo criterio
que ya aplicaron `calidad_aire`/`meteorologia` al incluir la etiqueta
(`pollutant`/`magnitude`) en su clave de tres componentes en vez de agregar
solo por estación y hora.

Se usa `movie_url` (no `movie_title`) como identificador de la película: es
la clave estable que ya usa la fuente (URL de la ficha en SensaCine), más
fiable que el título como texto libre (dos películas distintas podrían, en
teoría, compartir título; el mismo título de la misma película nunca cambia
de URL). `movie_title` se conserva en Gold solo para legibilidad.

## `sessions_count` (sesiones distintas) vs. `samples_count` (filas Silver)

Igual que el resto del patrón, `samples_count` es el número de filas Silver
en el bucket (incluye reingestas: la misma sesión capturada en dos barridos
de cartelera distintos produce dos filas Silver con el mismo
`showtime_id`). `sessions_count` es la magnitud principal de este dataset:
el número de `showtime_id` **distintos** en el bucket -- la reingesta de la
misma sesión no debe contarse dos veces como si fueran dos proyecciones
distintas. En el caso normal (cada sesión capturada una sola vez)
`samples_count == sessions_count`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def aggregate_silver_to_gold(records: "list[dict]", processed_at: datetime) -> "list[dict]":
    """Agrega registros Silver de `cartelera_cines_estrenos` por película, cine y día."""
    buckets: "dict[tuple[str, str, str], list[dict]]" = {}

    for record in records:
        showtime_datetime = _parse_iso(record.get("showtime_datetime"))
        movie_url = record.get("movie_url")
        cinema_id = record.get("cinema_id")
        if showtime_datetime is None or not movie_url or not cinema_id:
            continue
        key = (movie_url, cinema_id, showtime_datetime.date().isoformat())
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (movie_url, cinema_id, date_str), bucket in sorted(buckets.items()):
        showtimes = sorted(
            t for t in (_parse_iso(r.get("showtime_datetime")) for r in bucket) if t is not None
        )
        distinct_showtime_ids = {r.get("showtime_id") for r in bucket if r.get("showtime_id")}
        language_versions = sorted({r.get("language_version") for r in bucket if r.get("language_version")})
        first = bucket[0]

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "movie_title": first.get("movie_title"),
                "movie_url": movie_url,
                "cinema_id": cinema_id,
                "chain": first.get("chain"),
                "cinema_name": first.get("cinema_name"),
                "address": first.get("address"),
                "postal_code": first.get("postal_code"),
                "locality": first.get("locality"),
                "date": date_str,
                "samples_count": len(bucket),
                "sessions_count": len(distinct_showtime_ids),
                "first_showtime_datetime": showtimes[0].isoformat() if showtimes else None,
                "last_showtime_datetime": showtimes[-1].isoformat() if showtimes else None,
                "language_versions": language_versions,
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
