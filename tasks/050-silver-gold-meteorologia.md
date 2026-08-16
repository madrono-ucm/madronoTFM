---
id: 50
slug: silver-gold-meteorologia
title: 'Silver/Gold: meteorología (siguiendo el patrón de la tarea 041)'
status: in_progress
force: true
allow_infra_apply: false
branch: task/050-silver-gold-meteorologia
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-16T09:30:00+00:00'
updated_at: '2026-08-16T07:40:54.202908+00:00'
started_at: '2026-08-16T07:40:54.202884+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Continúa la extensión del patrón Bronze→Silver→Gold de la tarea 041 (lee
`procesamiento/README.md` antes de empezar) a `meteorologia` (lecturas de la
red de estaciones meteorológicas, `ingesta/capturas/meteorologia_madrid.py`,
ver `doc/008-...md` y la sección correspondiente de `ingesta/README.md`).

**Diferencia relevante frente a tráfico**: mismo backend/formato que
`calidad_aire` (registro por estación+magnitud+hora) — **no hace falta
ningún `geo.py`/reproyección**. No todas las estaciones miden todas las
magnitudes (temperatura, humedad, viento, presión, radiación,
precipitación) — la puerta de calidad debe validar rango por magnitud, no un
único rango genérico.

## Objetivo

Crear `procesamiento/silver_gold/meteorologia/` con la misma estructura que
`procesamiento/silver_gold/trafico/` (salvo `geo.py`):

- `transform.py`: puerta de calidad — campos clave no nulos (`station_id`,
  `magnitude`/campo equivalente, `measured_at`, `value`), rango plausible
  por magnitud (p.ej. temperatura entre -20 y 50ºC, humedad 0-100%, etc. —
  usa criterio razonable y documenta), descarta lecturas no válidas según el
  código de validación de la fuente.
- `aggregate.py`: agregación Silver→Gold por `(station_id, magnitude, fecha,
  hora)` — valor medio/máximo/mínimo en esa hora.
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas.
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue.
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/meteorologia_madrid_sample.json`, cubriendo al
  menos dos magnitudes distintas, sin `pyspark`/Great Expectations
  instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/meteorologia/*`, `silver/meteorologia/*`,
  `gold/meteorologia_por_estacion_magnitud_hora/*`, catálogo Silver/Gold) —
  **sin aplicar**.

## Restricciones

- Alcance: solo este dataset.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.

## Criterios de aceptación

- `procesamiento/silver_gold/meteorologia/` completo, con tests en verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado.
