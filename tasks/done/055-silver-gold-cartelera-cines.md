---
id: 55
slug: silver-gold-cartelera-cines
title: 'Silver/Gold: cartelera de cines (siguiendo el patrón de la tarea 041)'
status: done
force: true
allow_infra_apply: false
branch: task/055-silver-gold-cartelera-cines
pr_number: 102
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/102
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-16T14:45:00+00:00'
updated_at: '2026-08-16T19:54:09.706770+00:00'
started_at: '2026-08-16T19:51:45.232220+00:00'
submitted_at: '2026-08-16T19:53:03.463984+00:00'
merged_at: '2026-08-16T19:53:06Z'
---

## Contexto

Continúa la extensión del patrón Bronze→Silver→Gold de la tarea 041 (lee
`procesamiento/README.md` antes de empezar) a `cartelera_cines_estrenos`
(cartelera y horarios de cines, `ingesta/capturas/cartelera_cines_madrid.py`,
ver la sección correspondiente de `ingesta/README.md`), ya verificado
funcionando en producción (doc/033).

**Diferencia relevante frente a los datasets ya extendidos (046-050,
053-054)**: esta fuente no es una serie temporal de medidas (no tiene un
`value` numérico por hora), sino un **catálogo de sesiones/proyecciones**
(película, cine, horario). La agregación de Gold debe reflejar esa
naturaleza distinta, no el patrón `(id, fecha, hora)` de medida-numérica de
los datasets anteriores — **usa "número de sesiones por película y día" como
agregación de Gold, sin dar más vueltas a alternativas**: es una decisión ya
tomada, documenta brevemente por qué encaja, no reabras el diseño.

**Un primer intento de esta tarea agotó el presupuesto ($6, ~11.3M tokens,
~13 min) sin comitear nada** — probablemente por dedicar demasiado tiempo a
deliberar el diseño de la agregación de Gold en vez de implementar. Por eso
esta vez la decisión ya viene tomada (ver arriba) y el alcance de red se
acota explícitamente abajo.

## Objetivo

Crear `procesamiento/silver_gold/cartelera_cines_estrenos/` con la misma
estructura de subpaquete que `procesamiento/silver_gold/trafico/` (sin
`geo.py`, no aplica):

- `transform.py`: puerta de calidad — campos clave no nulos (título de la
  película, cine, horario de sesión), descarta registros incompletos o con
  fechas de sesión ya pasadas respecto a `ingested_at` si el dato lo
  permitiera.
- `aggregate.py`: agregación Silver→Gold por `(película, fecha)` — número de
  sesiones ese día, cines distintos que la proyectan (ver arriba, decisión ya
  tomada). Documenta brevemente en `procesamiento/README.md`.
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas.
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue. **Para el informe de Great Expectations, escribe directamente a
  S3 vía `boto3` (`s3_client.put_object(...)`), NO uses
  `sc.parallelize(...).saveAsTextFile(...)`** — ese patrón causó un bug real
  de producción en la tarea 051 (incompatible con el runtime de Glue).
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/cartelera_cines_madrid_sample.json`, sin
  `pyspark`/Great Expectations instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/cartelera_cines_estrenos/*`,
  `silver/cartelera_cines_estrenos/*`, `gold/cartelera_cines_estrenos_*/*`
  con el nombre que decidas para la tabla Gold, catálogo Silver/Gold) —
  **sin aplicar**.

## Restricciones

- Alcance: solo este dataset.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.
- **Usa el fixture existente `ingesta/capturas/samples/
  cartelera_cines_madrid_sample.json` tal cual, sin volver a scrapear las
  webs de cines** — esta tarea es sobre `procesamiento/`, no sobre mejorar la
  captura; no hace falta ningún dato nuevo de red.
- No dediques tiempo a evaluar alternativas de diseño para la agregación de
  Gold — ya está decidida arriba.

## Criterios de aceptación

- `procesamiento/silver_gold/cartelera_cines_estrenos/` completo, con tests
  en verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado, incluyendo la justificación del
  criterio de agregación elegido para este dataset.
