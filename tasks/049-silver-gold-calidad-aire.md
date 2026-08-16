---
id: 49
slug: silver-gold-calidad-aire
title: "Silver/Gold: calidad del aire (siguiendo el patrón de la tarea 041)"
status: pending
force: true
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-16T09:30:00+00:00"
updated_at: "2026-08-16T09:30:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

Continúa la extensión del patrón Bronze→Silver→Gold de la tarea 041 (lee
`procesamiento/README.md` antes de empezar) a `calidad_aire` (lecturas de la
red de estaciones de calidad del aire, `ingesta/capturas/
calidad_aire_madrid.py`, ver `doc/006-...md` y la sección correspondiente de
`ingesta/README.md`).

**Diferencia relevante frente a tráfico**: la fuente entrega coordenadas de
estación ya en WGS84 vía el CSV de metadatos — **no hace falta ningún
`geo.py`/reproyección**. Cada registro va etiquetado por contaminante
(`pollutant`) con su propia unidad — la puerta de calidad debe validar rango
por contaminante (los rangos plausibles no son los mismos para NO2 que para
PM10 u O3; usa la tabla de magnitudes del Anexo II documentada en doc/006
como referencia de unidades, y criterio propio razonable para los rangos).

## Objetivo

Crear `procesamiento/silver_gold/calidad_aire/` con la misma estructura que
`procesamiento/silver_gold/trafico/` (salvo `geo.py`):

- `transform.py`: puerta de calidad — campos clave no nulos (`station_id`,
  `pollutant`, `measured_at`, `value`), rango plausible por contaminante,
  descarta lecturas marcadas como no válidas por la fuente (código `"N"` en
  `V01`..`V24`, ya debería reflejarse en cómo `ingesta/` normaliza este
  campo — confírmalo).
- `aggregate.py`: agregación Silver→Gold por `(station_id, pollutant, fecha,
  hora)` — valor medio/máximo/mínimo en esa hora.
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas.
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue.
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/calidad_aire_madrid_sample.json`, cubriendo al
  menos dos contaminantes distintos, sin `pyspark`/Great Expectations
  instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/calidad_aire/*`, `silver/calidad_aire/*`,
  `gold/calidad_aire_por_estacion_contaminante_hora/*`, catálogo
  Silver/Gold) — **sin aplicar**.

## Restricciones

- Alcance: solo este dataset.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.

## Criterios de aceptación

- `procesamiento/silver_gold/calidad_aire/` completo, con tests en verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado.
