---
id: 59
slug: silver-gold-cams-calidad-aire
title: 'Silver/Gold: previsión de calidad del aire CAMS (siguiendo el patrón de la
  tarea 041)'
status: in_review
force: true
allow_infra_apply: false
branch: task/059-silver-gold-cams-calidad-aire
pr_number: 106
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/106
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-16T14:45:00+00:00'
updated_at: '2026-08-17T20:10:14.791282+00:00'
started_at: '2026-08-17T20:00:55.715188+00:00'
submitted_at: '2026-08-17T20:10:14.791137+00:00'
merged_at: null
---

## Contexto

Continúa la extensión del patrón Bronze→Silver→Gold de la tarea 041 (lee
`procesamiento/README.md` antes de empezar) a `cams_calidad_aire`
(`ingesta/capturas/cams_calidad_aire_madrid.py`, ver `doc/019-...md` y
`doc/045-arreglo-parseo-fecha-cams.md` — el productor ya tiene credenciales
y licencia reales en producción, y el bug de parseo de fechas NetCDF ya está
arreglado). En esta EC2 de desarrollo puede seguir devolviendo `is_mock:
true` si `CAMS_ADS_API_KEY` no está disponible como variable de entorno
local.

**Diferencia relevante frente a los datasets de medida ya extendidos**: es
una previsión horaria por contaminante en una rejilla espacial (no una
medida puntual del instante actual, ver `doc/045` para el detalle de
`leadtime_hour`/`forecast_issued_at`). La puerta de calidad y la agregación
de Gold deben razonar sobre esa forma de dato (previsión con horizonte),
como ya se hizo para AEMET (tarea 058) — probablemente conviene diseñar
ambas tareas con un criterio similar para previsión, ya que comparten
naturaleza.

## Objetivo

Crear `procesamiento/silver_gold/cams_calidad_aire/` con la misma estructura
de subpaquete que `procesamiento/silver_gold/trafico/` (sin `geo.py`, ya
viene en WGS84 según `doc/045`):

- `transform.py`: puerta de calidad — campos clave no nulos (`pollutant`,
  `valid_datetime`/`leadtime_hour`, `forecast_issued_at`, valor), rango
  plausible por contaminante (mismo criterio que `calidad_aire`, tarea 049,
  pero para previsión en vez de medida real).
- `aggregate.py`: agregación Silver→Gold ya decidida, no dediques tiempo a
  evaluar alternativas — por `(pollutant, fecha_validez)` (el día que
  predicen, no el horizonte de antelación): valor medio/máximo previsto ese
  día para ese contaminante. Implementa directamente.
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas.
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue. **Para el informe de Great Expectations, escribe directamente a
  S3 vía `boto3` (`s3_client.put_object(...)`), NO uses
  `sc.parallelize(...).saveAsTextFile(...)`** — ese patrón causó un bug real
  de producción en la tarea 051 (incompatible con el runtime de Glue).
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/cams_calidad_aire_madrid_sample.json`, sin
  `pyspark`/Great Expectations instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/cams_calidad_aire/*`, `silver/cams_calidad_aire/*`,
  `gold/cams_calidad_aire_*/*` con el nombre que decidas, catálogo
  Silver/Gold) — **sin aplicar**.

## Restricciones

- Alcance: solo este dataset.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.
- Si al regenerar la muestra local sigue devolviendo `is_mock: true` por no
  tener `CAMS_ADS_API_KEY` disponible en esta EC2, documenta que es por eso
  y sigue adelante con el fixture disponible.
- No dediques tiempo a evaluar alternativas de diseño para la agregación de
  Gold — ya está decidida arriba. Las tareas 055 y 057 agotaron el
  presupuesto ($6, sin comitear nada) precisamente por deliberar demasiado
  este tipo de decisión en datasets no numéricos — no repitas ese patrón.

## Criterios de aceptación

- `procesamiento/silver_gold/cams_calidad_aire/` completo, con tests en
  verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado, incluyendo la justificación del
  criterio de agregación elegido.
