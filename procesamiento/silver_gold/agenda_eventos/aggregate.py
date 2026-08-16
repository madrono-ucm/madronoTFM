"""Agregación Silver -> Gold del dataset `agenda_eventos`: número de eventos
por categoría, distrito y día de celebración.

## Por qué no el patrón `(id, fecha, hora)` del resto de datasets

Igual que `cartelera_cines_estrenos` (tarea 055), esta fuente no es una
serie temporal de una magnitud numérica medida repetidamente -- es un
**catálogo de eventos**: cada fila de Silver ya es un hecho discreto y único
(un evento concreto, identificado por `event_id`), no una medida que tenga
sentido promediar/sumar como magnitud. Lo único que aporta valor agregar es
**cuántos eventos hay**, agrupados por las dimensiones que interesan a un
consumidor de esta agenda.

## Clave de agregación: `(category, district, fecha)`

El enunciado sugería "por barrio/distrito y día, o por categoría y día"
como alternativas -- mismo criterio que ya aplicó `cartelera_cines_estrenos`
al recibir dos alternativas ("por película/día, o por cine/día"): se
incluyen **ambas** dimensiones en la misma clave, no solo una, para que un
consumidor de Gold pueda obtener cualquiera de las dos vistas sumando
`events_count` por la dimensión que le interese, sin perder información en
la propia agregación:

- "¿Cuántos eventos de música hay hoy (en cualquier distrito)?" -> sumar
  `events_count` de todas las filas con esa `category` y `date`.
- "¿Cuántos eventos hay hoy en Centro (de cualquier categoría)?" -> sumar
  `events_count` de todas las filas con ese `district` y `date`.

Se usa `district`, no `neighborhood` (barrio): la agenda de esMadrid nunca
publica ni distrito ni barrio (ver `transform.py`), así que cualquier
granularidad geográfica más fina que distrito fragmentaría aún más una
dimensión que ya es parcial por una de las dos fuentes, sin ganancia real
para un consumidor de Gold. Igual que la tarea 041 documentó para `trafico`,
cruzar `lat`/`lon` con `barrios_distritos_madrid` (point-in-polygon) para
rellenar el distrito que falta en esMadrid queda fuera de alcance -- es
exactamente el tipo de relación espacial que la tarea 043 (grafo Neo4j) va
a modelar de forma explícita y reutilizable; el `district` que sí se usa
aquí viene directamente resuelto por el propio catálogo municipal de
datos.madrid.es, no de una heurística ad-hoc.

`category`/`district` ausentes (`null` en Silver, ver `transform.py`) se
agrupan bajo el sentinela `"__sin_categoria__"`/`"__sin_distrito__"`
respectivamente, en vez de descartar esos eventos de la agregación --
mismo criterio que `aparcamientos.aggregate` con `fecha=__sin_medida__`
(tarea 048): un evento sin categoría o sin distrito conocido sigue siendo
un evento real y contable, no un dato corrupto. La combinación
`(source=agenda_turismo_esmadrid, district=__sin_distrito__)` es, de hecho,
la cobertura *esperada* al 100% de esa fuente -- no una anomalía a corregir.

`fecha` se deriva de `start_datetime` (el día en que el evento **empieza**,
no el día en que se capturó -- mismo criterio que `cartelera_cines_estrenos`
usó con `showtime_datetime`: la pregunta natural de una agenda es "qué hay
tal día", no "cuándo se consultó la fuente"). Para eventos de varios días
(p.ej. una exposición de meses) solo se cuenta en el día de inicio, no en
cada día del rango -- misma simplificación deliberada que ya aplicó
`ingesta/capturas/agenda_eventos_madrid.py` al no expandir la recurrencia
completa de esMadrid (ver docstring de ese módulo, "Simplificación
deliberada"); expandir un evento a una fila de Gold por cada día que dura
excede el alcance de esta agregación y no lo pedía el enunciado.

## `events_count` (eventos distintos) vs. `samples_count` (filas Silver)

Igual que el resto del patrón, `samples_count` es el número de filas Silver
en el bucket (incluye reingestas: el mismo evento capturado en dos barridos
de la agenda produce dos filas Silver con el mismo `event_id`).
`events_count` es la magnitud principal de este dataset: el número de
`event_id` **distintos** -- la reingesta del mismo evento no debe contarse
dos veces. `free_events_count` (eventos distintos con `free = true`) se
añade porque es una pregunta habitual de un consumidor de una agenda
cultural ("¿cuántos eventos gratuitos hay hoy en tal distrito/categoría?")
que Silver ya permite responder sin releer datos crudos. `sources` (lista
ordenada de `source` distintos presentes en el bucket) deja explícito de
qué fuente(s) proviene cada fila de Gold, útil sobre todo para distinguir
`__sin_distrito__` "porque esMadrid no publica distrito" de
"__sin_distrito__` porque faltó ese dato en un evento municipal concreto".
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1

UNKNOWN_CATEGORY = "__sin_categoria__"
UNKNOWN_DISTRICT = "__sin_distrito__"


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def aggregate_silver_to_gold(records: "list[dict]", processed_at: datetime) -> "list[dict]":
    """Agrega registros Silver de `agenda_eventos` por categoría, distrito y día."""
    buckets: "dict[tuple[str, str, str], list[dict]]" = {}

    for record in records:
        start_datetime = _parse_iso(record.get("start_datetime"))
        if start_datetime is None:
            continue
        category = record.get("category") or UNKNOWN_CATEGORY
        district = record.get("district") or UNKNOWN_DISTRICT
        key = (category, district, start_datetime.date().isoformat())
        buckets.setdefault(key, []).append(record)

    gold_records = []
    for (category, district, date_str), bucket in sorted(buckets.items()):
        starts = sorted(
            t for t in (_parse_iso(r.get("start_datetime")) for r in bucket) if t is not None
        )
        distinct_event_ids = {r.get("event_id") for r in bucket if r.get("event_id")}
        free_event_ids = {
            r.get("event_id") for r in bucket if r.get("event_id") and r.get("free") is True
        }
        sources = sorted({r.get("source") for r in bucket if r.get("source")})

        gold_records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "category": category,
                "district": district,
                "date": date_str,
                "samples_count": len(bucket),
                "events_count": len(distinct_event_ids),
                "free_events_count": len(free_event_ids),
                "sources": sources,
                "first_start_datetime": starts[0].isoformat() if starts else None,
                "last_start_datetime": starts[-1].isoformat() if starts else None,
                "processed_at": processed_at.isoformat(),
            }
        )

    return gold_records
