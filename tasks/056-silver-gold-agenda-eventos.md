---
id: 56
slug: silver-gold-agenda-eventos
title: "Silver/Gold: agenda de eventos culturales (siguiendo el patrón de la tarea 041)"
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
`procesamiento/README.md` antes de empezar) a `agenda_eventos`
(`ingesta/capturas/agenda_eventos_madrid.py`, dos fuentes combinadas —
`agenda_eventos_madrid_municipal` y `agenda_turismo_esmadrid`, con un campo
`source` para distinguirlas — ver la sección correspondiente de
`ingesta/README.md`).

**Diferencia relevante frente a los datasets numéricos ya extendidos**: es
un catálogo de eventos (título, ubicación, fecha/hora de celebración,
categoría, fuente), no una serie temporal de medidas. La agregación de Gold
debe reflejar esa naturaleza (p.ej. número de eventos por barrio/distrito y
día, o por categoría y día) — decide con criterio propio y documenta.

## Objetivo

Crear `procesamiento/silver_gold/agenda_eventos/` con la misma estructura de
subpaquete que `procesamiento/silver_gold/trafico/` (sin `geo.py` salvo que
la fuente entregue coordenadas en un sistema distinto a WGS84 — confírmalo):

- `transform.py`: puerta de calidad — campos clave no nulos (título,
  fecha/hora del evento, `source`), descarta eventos sin fecha de
  celebración parseable.
- `aggregate.py`: agregación Silver→Gold razonable para un catálogo de
  eventos (ver arriba) — documenta la decisión en
  `procesamiento/README.md`. Si decides agregar por zona geográfica,
  recuerda que la tarea 041 documentó por qué cruzar con
  `barrios_distritos_madrid` (point-in-polygon) queda para la tarea 043
  (grafo Neo4j) — no lo reintentes aquí ad-hoc.
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas.
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue. **Para el informe de Great Expectations, escribe directamente a
  S3 vía `boto3` (`s3_client.put_object(...)`), NO uses
  `sc.parallelize(...).saveAsTextFile(...)`** — ese patrón causó un bug real
  de producción en la tarea 051 (incompatible con el runtime de Glue).
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/agenda_eventos_madrid_sample.json`, cubriendo
  ambas fuentes (`source`), sin `pyspark`/Great Expectations instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/agenda_eventos/*`, `silver/agenda_eventos/*`,
  `gold/agenda_eventos_*/*` con el nombre que decidas, catálogo
  Silver/Gold) — **sin aplicar**.

## Restricciones

- Alcance: solo este dataset.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.

## Criterios de aceptación

- `procesamiento/silver_gold/agenda_eventos/` completo, con tests en verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado, incluyendo la justificación del
  criterio de agregación elegido.
