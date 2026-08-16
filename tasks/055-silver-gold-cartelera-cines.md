---
id: 55
slug: silver-gold-cartelera-cines
title: "Silver/Gold: cartelera de cines (siguiendo el patrón de la tarea 041)"
status: pending
force: true
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-16T14:45:00+00:00"
updated_at: "2026-08-16T14:45:00+00:00"
started_at: null
submitted_at: null
merged_at: null
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
naturaleza distinta — decide con criterio propio (p.ej. número de sesiones
por película/día, o por cine/día) y documenta por qué, en vez de forzar el
patrón `(id, fecha, hora)` de medida-numérica de los datasets anteriores.

## Objetivo

Crear `procesamiento/silver_gold/cartelera_cines_estrenos/` con la misma
estructura de subpaquete que `procesamiento/silver_gold/trafico/` (sin
`geo.py`, no aplica):

- `transform.py`: puerta de calidad — campos clave no nulos (título de la
  película, cine, horario de sesión), descarta registros incompletos o con
  fechas de sesión ya pasadas respecto a `ingested_at` si el dato lo
  permitiera.
- `aggregate.py`: agregación Silver→Gold razonable para un catálogo de
  sesiones (ver arriba) — documenta la decisión en
  `procesamiento/README.md`.
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

## Criterios de aceptación

- `procesamiento/silver_gold/cartelera_cines_estrenos/` completo, con tests
  en verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado, incluyendo la justificación del
  criterio de agregación elegido para este dataset.
