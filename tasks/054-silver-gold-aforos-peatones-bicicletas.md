---
id: 54
slug: silver-gold-aforos-peatones-bicicletas
title: 'Silver/Gold: aforos de peatones y bicicletas (siguiendo el patrón de la tarea
  041)'
status: in_progress
force: true
allow_infra_apply: false
branch: task/054-silver-gold-aforos-peatones-bicicletas
pr_number: null
pr_url: null
attempts: 5
next_retry_at: '2026-08-16T19:19:00+00:00'
last_error: You've hit your session limit · resets 7pm (UTC)
created_at: '2026-08-16T14:45:00+00:00'
updated_at: '2026-08-16T19:19:48.535094+00:00'
started_at: '2026-08-16T16:35:25.983318+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Continúa la extensión del patrón Bronze→Silver→Gold de la tarea 041 (lee
`procesamiento/README.md` antes de empezar) a `aforos_peatones_bicicletas`
(conteos horarios de peatones y bicicletas, `ingesta/capturas/
aforos_peatones_bicicletas_madrid.py`, ver la sección correspondiente de
`ingesta/README.md`). La tarea 040 ya arregló el timeout de su Lambda en
producción — este dataset ya fluye a Bronze con normalidad.

## Objetivo

Crear `procesamiento/silver_gold/aforos_peatones_bicicletas/` con la misma
estructura que `procesamiento/silver_gold/trafico/` (confirma si hace falta
`geo.py`; si la fuente ya da coordenadas en WGS84, no hace falta):

- `transform.py`: puerta de calidad — campos clave no nulos (`station_id`,
  `mode` (`peatones`/`bicicletas`), `measured_at`, conteo), conteo no
  negativo, descarta estaciones/horas sin dato.
- `aggregate.py`: agregación Silver→Gold por `(station_id, mode, fecha,
  hora)` — conteo total/medio en esa hora.
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas.
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue. **Para el informe de Great Expectations, escribe directamente a
  S3 vía `boto3` (`s3_client.put_object(...)`), NO uses
  `sc.parallelize(...).saveAsTextFile(...)`** — ese patrón causó un bug real
  de producción en la tarea 051 (incompatible con el runtime de Glue).
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/aforos_peatones_bicicletas_madrid_sample.json`,
  sin `pyspark`/Great Expectations instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/aforos_peatones_bicicletas/*`,
  `silver/aforos_peatones_bicicletas/*`,
  `gold/aforos_peatones_bicicletas_por_estacion_modo_hora/*`, catálogo
  Silver/Gold) — **sin aplicar**.

## Restricciones

- Alcance: solo este dataset.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.

## Criterios de aceptación

- `procesamiento/silver_gold/aforos_peatones_bicicletas/` completo, con
  tests en verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado.
