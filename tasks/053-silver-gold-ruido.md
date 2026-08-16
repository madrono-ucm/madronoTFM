---
id: 53
slug: silver-gold-ruido
title: 'Silver/Gold: contaminación acústica (siguiendo el patrón de la tarea 041)'
status: in_progress
force: true
allow_infra_apply: false
branch: task/053-silver-gold-ruido
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-16T14:45:00+00:00'
updated_at: '2026-08-16T16:22:05.560707+00:00'
started_at: '2026-08-16T16:22:05.560683+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Continúa la extensión del patrón Bronze→Silver→Gold de la tarea 041 (lee
`procesamiento/README.md` antes de empezar) a `ruido` (contaminación
acústica diaria, `ingesta/capturas/ruido_madrid.py`, ver la sección
correspondiente de `ingesta/README.md`).

**Diferencia relevante frente a tráfico y frente al resto de datasets ya
extendidos (046-050)**: esta fuente no es horaria, sino **diaria por
estación y periodo** (`diurno`, `vespertino`, `nocturno`, `total`) — LAeq y
percentiles L1/L10/L50/L90/L99. La clave de agregación de Gold para este
dataset debe reflejar esa granularidad real (por `fecha`, no por
`fecha`+`hora`), no copiar mecánicamente el patrón `(id, fecha, hora)` de
los datasets horarios.

## Objetivo

Crear `procesamiento/silver_gold/ruido/` con la misma estructura que
`procesamiento/silver_gold/trafico/` (sin `geo.py` si la fuente ya da
coordenadas en WGS84 — confírmalo):

- `transform.py`: puerta de calidad — campos clave no nulos (`station_id`,
  `periodo`, `fecha`, `laeq` o el campo equivalente), rango plausible de
  decibelios (p.ej. 20-120 dB), descarta periodos sin dato.
- `aggregate.py`: agregación Silver→Gold por `(station_id, periodo, fecha)`
  — dado que la fuente ya es un agregado diario, decide con criterio propio
  qué aporta Gold aquí (p.ej. una media móvil de varios días, o
  simplemente el paso a través normalizado si no hay nada más que agregar a
  esta granularidad — documenta la decisión, no fuerces una agregación
  horaria que la fuente no soporta).
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas.
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue. **Para el informe de Great Expectations, escribe directamente a
  S3 vía `boto3` (`s3_client.put_object(...)`), NO uses
  `sc.parallelize(...).saveAsTextFile(...)`** — ese patrón causó un bug real
  de producción en la tarea 051 (`ClassNotFoundException:
  org.apache.hadoop.mapred.DirectOutputCommitter`, incompatible con el
  runtime de Glue); no lo repitas aquí.
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/ruido_madrid_sample.json`, sin `pyspark`/Great
  Expectations instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/ruido/*`, `silver/ruido/*`,
  `gold/ruido_por_estacion_periodo_fecha/*`, catálogo Silver/Gold) — **sin
  aplicar**.

## Restricciones

- Alcance: solo este dataset.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.

## Criterios de aceptación

- `procesamiento/silver_gold/ruido/` completo, con tests en verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado.
