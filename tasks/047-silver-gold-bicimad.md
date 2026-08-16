---
id: 47
slug: silver-gold-bicimad
title: 'Silver/Gold: BiciMAD (siguiendo el patrón de la tarea 041)'
status: in_review
force: true
allow_infra_apply: false
branch: task/047-silver-gold-bicimad
pr_number: 94
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/94
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-16T09:30:00+00:00'
updated_at: '2026-08-16T01:10:45.072620+00:00'
started_at: '2026-08-16T01:02:39.682695+00:00'
submitted_at: '2026-08-16T01:10:45.072446+00:00'
merged_at: null
---

## Contexto

Continúa la extensión del patrón Bronze→Silver→Gold de la tarea 041 (lee
`procesamiento/README.md` antes de empezar) a `bicimad` (estado de las
estaciones de BiciMAD, `ingesta/capturas/bicimad.py`, ver `doc/004-...md` y
la sección correspondiente de `ingesta/README.md`).

**Diferencia relevante frente a tráfico**: `location` ya viene en WGS84
(`lat`/`lon` estándar) — **no hace falta ningún `geo.py`/reproyección**.

## Objetivo

Crear `procesamiento/silver_gold/bicimad/` con la misma estructura que
`procesamiento/silver_gold/trafico/` (salvo `geo.py`):

- `transform.py`: puerta de calidad — campos clave no nulos (`station_id`,
  `measured_at`), `bikes_available + bikes_disabled <= docks_total`,
  `docks_available + docks_disabled <= docks_total` (o el criterio de
  consistencia que decidas y documentes si la fuente real no siempre lo
  cumple exactamente), descarta estaciones con `is_installed = false`.
- `aggregate.py`: agregación Silver→Gold por `(station_id, fecha, hora)` —
  bicis/anclajes disponibles medios en esa hora y una ratio de ocupación
  (`bikes_available / docks_total`).
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas (mismo criterio que la tarea 041).
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue, mismo patrón que los de tráfico.
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/bicimad_sample.json`, cubriendo la puerta de
  calidad y la agregación, sin `pyspark`/Great Expectations instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/bicimad/*`, `silver/bicimad/*`,
  `gold/bicimad_por_estacion_hora/*`, catálogo Silver/Gold) — **sin
  aplicar** (`terraform validate` con `-backend=false` es suficiente).

## Restricciones

- Alcance: solo este dataset. No toques otros subpaquetes de
  `procesamiento/silver_gold/`.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.

## Criterios de aceptación

- `procesamiento/silver_gold/bicimad/` completo, con tests en verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado.
