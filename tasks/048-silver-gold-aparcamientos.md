---
id: 48
slug: silver-gold-aparcamientos
title: 'Silver/Gold: aparcamientos rotacionales (siguiendo el patrón de la tarea 041)'
status: in_progress
force: true
allow_infra_apply: false
branch: task/048-silver-gold-aparcamientos
pr_number: null
pr_url: null
attempts: 4
next_retry_at: '2026-08-16T02:43:23.969502+00:00'
last_error: You've hit your session limit · resets 5am (UTC)
created_at: '2026-08-16T09:30:00+00:00'
updated_at: '2026-08-16T02:44:10.022561+00:00'
started_at: '2026-08-16T01:12:54.221061+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Continúa la extensión del patrón Bronze→Silver→Gold de la tarea 041 (lee
`procesamiento/README.md` antes de empezar) a `aparcamientos` (ocupación de
aparcamientos rotacionales, `ingesta/capturas/aparcamientos_madrid.py`, ver
`doc/005-...md` y la sección correspondiente de `ingesta/README.md`).

**Diferencias relevantes frente a tráfico**: `location` ya viene en WGS84
(no hace falta `geo.py`); y `measured_at`/`free_spaces`/`total_spaces` pueden
venir a `null` cuando un aparcamiento concreto no comparte ocupación en
tiempo real (documentado en doc/005) — la puerta de calidad debe decidir
explícitamente si esos registros pasan a Silver con los campos numéricos a
`null`, o si se descartan; documenta la decisión.

## Objetivo

Crear `procesamiento/silver_gold/aparcamientos/` con la misma estructura que
`procesamiento/silver_gold/trafico/` (salvo `geo.py`):

- `transform.py`: puerta de calidad — campos clave no nulos (`parking_id`),
  si `free_spaces`/`total_spaces` no son `null`, `0 <= free_spaces <=
  total_spaces`; criterio explícito para el caso de ocupación no disponible
  (ver arriba).
- `aggregate.py`: agregación Silver→Gold por `(parking_id, fecha, hora)` —
  plazas libres medias en esa hora y una ratio de ocupación
  (`free_spaces / total_spaces`) cuando ambos estén disponibles.
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas.
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue.
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/aparcamientos_madrid_sample.json`, incluyendo al
  menos un registro con ocupación no disponible (`null`), sin
  `pyspark`/Great Expectations instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/aparcamientos/*`, `silver/aparcamientos/*`,
  `gold/aparcamientos_por_parking_hora/*`, catálogo Silver/Gold) — **sin
  aplicar**.

## Restricciones

- Alcance: solo este dataset.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.

## Criterios de aceptación

- `procesamiento/silver_gold/aparcamientos/` completo, con tests en verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado.
