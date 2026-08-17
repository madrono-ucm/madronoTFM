---
id: 57
slug: silver-gold-bluesky-menciones
title: 'Silver/Gold: menciones de Bluesky (siguiendo el patrón de la tarea 041)'
status: done
force: true
allow_infra_apply: false
branch: task/057-silver-gold-bluesky-menciones
pr_number: 104
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/104
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-16T14:45:00+00:00'
updated_at: '2026-08-17T19:44:06.895170+00:00'
started_at: '2026-08-17T19:41:53.376433+00:00'
submitted_at: '2026-08-17T19:42:59.184632+00:00'
merged_at: '2026-08-17T19:43:03Z'
---

## Contexto

Continúa la extensión del patrón Bronze→Silver→Gold de la tarea 041 (lee
`procesamiento/README.md` antes de empezar) a `bluesky_menciones`
(`ingesta/capturas/bluesky_menciones_madrid.py`, dos modos — on-demand por
búsqueda de lugar y por distrito/barrio cada hora, con un campo `mode` — ver
la sección correspondiente de `ingesta/README.md`).

**Diferencia relevante frente a los datasets numéricos ya extendidos**: son
publicaciones de texto libre (contenido, autor, timestamp, lugar/distrito
buscado), no una medida numérica. No hay ninguna puerta de calidad de
"rango plausible" aquí — la puerta de calidad debe centrarse en integridad
estructural (campos clave presentes) y descartar contenido vacío o
duplicados exactos. **La agregación de Gold ya está decidida: conteo de
menciones por `(lugar_o_distrito, mode, fecha)`** — no dediques tiempo a
evaluar alternativas, implementa esta directamente.

**Un intento anterior de esta tarea agotó el presupuesto ($6, ~11.7M
tokens, ~13 min) sin comitear nada** (tras varios reintentos previos por
límite de sesión, ya resueltos) — mismo patrón que le pasó a la tarea 055
(cartelera de cines), probablemente por deliberar demasiado el diseño de la
agregación en vez de implementar directamente. Por eso esta vez la decisión
ya viene tomada (ver arriba) y el alcance de red se acota explícitamente
abajo.

## Objetivo

Crear `procesamiento/silver_gold/bluesky_menciones/` con la misma estructura
de subpaquete que `procesamiento/silver_gold/trafico/` (sin `geo.py`):

- `transform.py`: puerta de calidad — campos clave no nulos (`mode`,
  contenido del post, `measured_at`/timestamp de la publicación, lugar o
  distrito asociado), descarta registros sin contenido o duplicados exactos.
- `aggregate.py`: agregación Silver→Gold por `(lugar_o_distrito, mode,
  fecha)` — conteo de menciones (ver arriba, decisión ya tomada).
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas.
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue. **Para el informe de Great Expectations, escribe directamente a
  S3 vía `boto3` (`s3_client.put_object(...)`), NO uses
  `sc.parallelize(...).saveAsTextFile(...)`** — ese patrón causó un bug real
  de producción en la tarea 051 (incompatible con el runtime de Glue).
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/bluesky_menciones_madrid_sample.json`, cubriendo
  ambos `mode`, sin `pyspark`/Great Expectations instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/bluesky_menciones/*`, `silver/bluesky_menciones/*`,
  `gold/bluesky_menciones_*/*` con el nombre que decidas, catálogo
  Silver/Gold) — **sin aplicar**.

## Restricciones

- Alcance: solo este dataset.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.
- No intentes ningún análisis de sentimiento/NLP sobre el contenido de los
  posts — está fuera de alcance de esta tarea, es puramente estructuración
  Bronze→Silver→Gold.
- **Usa el fixture existente `ingesta/capturas/samples/
  bluesky_menciones_madrid_sample.json` tal cual, sin volver a consultar la
  API de Bluesky** — esta tarea es sobre `procesamiento/`, no sobre mejorar
  la captura.
- No dediques tiempo a evaluar alternativas de diseño para la agregación de
  Gold — ya está decidida arriba.

## Criterios de aceptación

- `procesamiento/silver_gold/bluesky_menciones/` completo, con tests en
  verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado, incluyendo la justificación del
  criterio de agregación elegido.
