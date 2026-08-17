"""Transformación Bronze -> Silver del dataset `bluesky_menciones` (menciones
públicas de lugares/distritos de Madrid en Bluesky, ver
`ingesta/capturas/bluesky_menciones_madrid.py`).

Lógica en **Python puro** (solo `stdlib`), mismo motivo que el resto de
datasets del patrón (ver `procesamiento/README.md`, sección "Por qué Python
puro para la lógica, y PySpark solo en el job de Glue"): así se puede probar
con `unittest` en esta EC2 de desarrollo, sin Spark ni Great Expectations
instalados.

Cada registro Bronze se procesa en dos pasos (ver `bronze_to_silver` más
abajo para el porqué no son estrictamente independientes en este dataset):

1. `validate_record(record)`: puerta de calidad -- una lista de motivos de
   rechazo (vacía si el registro es válido). Un registro con algún motivo NO
   debe llegar a Silver.
2. `to_silver_record(record, processed_at)`: solo se llama sobre registros
   que ya pasaron la puerta de calidad.

Las mismas comprobaciones están descritas como expectations declarativas de
Great Expectations en `ge_suite.py` -- ver `trafico/ge_suite.py` para el
razonamiento completo de por qué existen dos representaciones de la misma
regla.

## Sin `geo.py`: no hay ninguna coordenada en este dataset

`normalize_post` (`ingesta/capturas/bluesky_menciones_madrid.py`) descarta a
propósito todo el bloque `author` del post (privacidad, ver docstring de ese
módulo) y Bluesky no publica la ubicación geográfica de un post -- no hace
falta ningún `geo.py` ni columna `location`.

## Diferencia real frente al resto del patrón: texto libre, no una medida numérica

Los nueve datasets ya extendidos son series temporales de una magnitud
numérica o catálogos de hechos discretos con una clave natural fuerte
(`showtime_id`, `event_id`). Este dataset son publicaciones de texto libre
(contenido, lugar/distrito buscado, marca de tiempo de la publicación) --
no hay ninguna magnitud que tenga un "rango plausible": la puerta de calidad
se centra en integridad estructural (campos clave presentes) y en descartar
contenido vacío o duplicado, tal como pide el enunciado de esta tarea, en
vez de en rangos de valores.

## Dos `mode`, ambos válidos en Silver (a diferencia de `cartelera_cines_estrenos`)

`ingesta/capturas/bluesky_menciones_madrid.py` produce dos formas de
registro bajo el mismo esquema normalizado, distinguidas por `mode`:
`"bajo_demanda"` (búsqueda puntual de un lugar, pensada para el asistente
conversacional) y `"distrito_sweep"` (barrido general por distrito +
términos de evento, pensado para un productor programado cada hora). A
diferencia de `cartelera_cines_estrenos` (que rechazaba por completo uno de
los dos tipos de registro que mezclaba Bronze, ver ese `transform.py`), aquí
**ambos modos son datos legítimos de este dataset** -- el enunciado de la
tarea 057 los describe como parte del mismo `bluesky_menciones`, con `mode`
como campo a conservar, no a filtrar. `validate_record` solo exige que
`mode` esté presente y sea uno de los dos valores conocidos; `mode` pasa a
formar parte de la clave de agregación en `aggregate.py` ("separado por
mode", tal como pide el enunciado).

## `match_term`: el campo "lugar o distrito asociado" que pide el enunciado

`match_term` es el lugar (modo `bajo_demanda`) o el distrito/término de
evento (modo `distrito_sweep`, con el prefijo `"eventos:"` para los términos
genéricos -- ver `search_district_sweep` en el módulo de ingesta) que
produjo el resultado de búsqueda. Es el campo que el enunciado pide
explícitamente como "lugar o distrito asociado" en la puerta de calidad, y
la dimensión geográfica/temática de la agregación de Gold -- Bluesky no
publica ninguna coordenada real del post, así que `match_term` es la única
señal de "dónde" que tiene este dataset.

## Puerta de calidad: contenido vacío y duplicados exactos

El enunciado pide explícitamente descartar "contenido vacío" y "duplicados
exactos". `text` vacío o solo espacios en blanco se rechaza en
`validate_record` (`"text_missing_or_empty"`) -- comprobación por registro,
igual que el resto de campos clave.

Los **duplicados exactos**, en cambio, no se pueden detectar mirando un
único registro: hace falta comparar contra los demás registros del mismo
lote. `ingesta/capturas/bluesky_menciones_madrid.py` ya anticipó este
problema y añadió `post_hash` (SHA-256 truncado del texto) precisamente como
"clave de deduplicación barata entre términos de búsqueda solapados" (ver su
docstring, sección "Privacidad") -- un mismo post real puede aparecer varias
veces en un mismo lote Bronze porque coincide con más de un término de
búsqueda (p.ej. un post sobre un concierto en Malasaña puede coincidir con
la búsqueda del distrito "Chamberí" -- que menciona el evento -- y con el
término de evento "concierto" del mismo barrido). Por eso `bronze_to_silver`
(no `validate_record`, que solo ve un registro a la vez) descarta, dentro
del mismo lote, cualquier registro cuyo `post_hash` ya se haya visto antes
en ese lote, con el motivo `"duplicate_exact_content"`, conservando la
primera ocurrencia en el orden del lote. Esto es una desviación deliberada
del resto del patrón (donde `validate_record` basta porque cada regla es
puramente por registro) -- documentada aquí para que una tarea futura que
toque este módulo no la confunda con un descuido.

Nótese que esto **no** deduplica entre lotes/ejecuciones distintas (una
reingesta del mismo post en un barrido posterior sí produce una fila Silver
adicional) -- igual que el resto del patrón, esa deduplicación entre
reingestas la hace `aggregate.py` contando `post_hash` distintos
(`mentions_count` frente a `samples_count`), no la puerta de calidad.

## `created_at`/`indexed_at`: timestamps de Bluesky en formato `Z` (UTC), no `+02:00`

A diferencia del resto de timestamps de este patrón (generados por
`ingesta/capturas/bronze.py:now_madrid()`, siempre con offset explícito tipo
`+02:00`/`+01:00`), `created_at`/`indexed_at` los genera la propia API de
Bluesky en formato `...Z` (UTC, sufijo `Z` en vez de `+00:00`). Esto importa
porque **AWS Glue 4.0 ejecuta Python 3.10** (`infra/terraform/variables.tf`,
`glue_version`), y `datetime.fromisoformat` solo entiende el sufijo `Z`
directamente desde Python 3.11 -- en Python 3.10 lanzaría `ValueError` y
`_parse_iso` rechazaría por error el 100% de los registros reales. Por eso
`_parse_iso` normaliza `Z` a `+00:00` antes de parsear, en vez de llamar a
`datetime.fromisoformat` tal cual (lo que sí bastaba en el resto del
patrón, donde todos los timestamps ya traían un offset explícito). Esta
misma función se reutiliza para `captured_at` (que sí trae offset explícito
de `now_madrid()`), donde la normalización de `Z` no tiene efecto.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

SCHEMA_VERSION = 1

MODE_SEARCH_PLACE = "bajo_demanda"
MODE_DISTRICT_SWEEP = "distrito_sweep"
VALID_MODES = {MODE_SEARCH_PLACE, MODE_DISTRICT_SWEEP}


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parsea un timestamp ISO-8601, aceptando el sufijo `Z` (ver docstring del módulo)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def validate_record(record: dict) -> "list[str]":
    """Devuelve los motivos por los que `record` NO debe llegar a Silver.

    Lista vacía == registro válido (a falta de la comprobación de duplicado
    exacto, que se hace a nivel de lote en `bronze_to_silver`, no aquí -- ver
    docstring del módulo). Cada motivo es una cadena corta y estable, útil
    como métrica: cuántos registros caen por cada regla.
    """
    reasons: "list[str]" = []

    if record.get("mode") not in VALID_MODES:
        reasons.append("mode_missing_or_invalid")

    if not (record.get("match_term") or "").strip():
        reasons.append("match_term_missing")

    if not (record.get("text") or "").strip():
        reasons.append("text_missing_or_empty")

    if not record.get("post_hash"):
        reasons.append("post_hash_missing")

    created_at = _parse_iso(record.get("created_at"))
    if created_at is None:
        reasons.append("created_at_missing_or_unparseable")
    elif created_at.tzinfo is None:
        reasons.append("created_at_not_timezone_aware")

    captured_at = _parse_iso(record.get("captured_at"))
    if captured_at is None:
        reasons.append("captured_at_missing_or_unparseable")
    elif captured_at.tzinfo is None:
        reasons.append("captured_at_not_timezone_aware")

    return reasons


def to_silver_record(record: dict, processed_at: datetime) -> dict:
    """Normaliza un registro Bronze ya validado (`validate_record` == []).

    No vuelve a validar: se asume que el llamador ya filtró los registros
    que no pasan la puerta de calidad (ver `bronze_to_silver` más abajo, o
    el job de Glue). Renombra `captured_at` a `ingested_at`, mismo nombre de
    campo que usa el resto del patrón para el instante de captura.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "source": record.get("source"),
        "mode": record.get("mode"),
        "match_term": record.get("match_term"),
        "post_hash": record.get("post_hash"),
        "text": record.get("text"),
        "lang": record.get("lang"),
        "created_at": record.get("created_at"),
        "indexed_at": record.get("indexed_at"),
        "like_count": record.get("like_count"),
        "repost_count": record.get("repost_count"),
        "reply_count": record.get("reply_count"),
        "quote_count": record.get("quote_count"),
        "ingested_at": record.get("captured_at"),
        "processed_at": processed_at.isoformat(),
    }


def bronze_to_silver(records: "list[dict]", processed_at: datetime) -> "tuple[list[dict], list[dict]]":
    """Aplica la puerta de calidad y transforma los registros que la pasan.

    A diferencia del resto del patrón, no se limita a llamar a
    `validate_record` por registro: también descarta duplicados exactos
    dentro del mismo lote por `post_hash` (ver docstring del módulo,
    "Puerta de calidad: contenido vacío y duplicados exactos"), conservando
    la primera ocurrencia.

    Devuelve `(silver_records, rejected)`: `rejected` es una lista de
    `{"record": <original>, "reasons": [...]}`, útil para observabilidad --
    el job de Glue solo escribe `silver_records` en el bucket Silver;
    `rejected` se queda en los logs del job, mismo criterio que el resto de
    datasets del patrón.
    """
    silver_records = []
    rejected = []
    seen_post_hashes: "set[str]" = set()

    for record in records:
        reasons = validate_record(record)
        if not reasons:
            post_hash = record.get("post_hash")
            if post_hash in seen_post_hashes:
                reasons = ["duplicate_exact_content"]
            else:
                seen_post_hashes.add(post_hash)

        if reasons:
            rejected.append({"record": record, "reasons": reasons})
        else:
            silver_records.append(to_silver_record(record, processed_at))

    return silver_records, rejected
