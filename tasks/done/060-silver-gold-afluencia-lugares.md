---
id: 60
slug: silver-gold-afluencia-lugares
title: 'Silver/Gold: afluencia de lugares (siguiendo el patrón de la tarea 041)'
status: done
force: true
allow_infra_apply: false
branch: task/060-silver-gold-afluencia-lugares
pr_number: 107
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/107
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-16T14:45:00+00:00'
updated_at: '2026-08-17T20:24:51.241793+00:00'
started_at: '2026-08-17T20:12:24.695098+00:00'
submitted_at: '2026-08-17T20:23:43.811351+00:00'
merged_at: '2026-08-17T20:23:48Z'
---

## Contexto

Continúa la extensión del patrón Bronze→Silver→Gold de la tarea 041 (lee
`procesamiento/README.md` antes de empezar) a `afluencia_lugares`
(`ingesta/capturas/afluencia_lugares_madrid.py`, ver `doc/012-...md`). A
diferencia del resto de datasets ya extendidos, este **sigue bloqueado**:
no hay `GOOGLE_MAPS_API_KEY` real todavía (único origen de datos del
proyecto sin credenciales), así que tanto la muestra local como cualquier
dato en Bronze seguirán siendo `is_mock: true` hasta que se obtenga esa
clave. Esto no impide escribir el código de esta tarea (mismo criterio que
la tarea 012 en su día: verificar la lógica contra el fixture mock, dejar el
código listo para funcionar tal cual el día que haya clave real).

**Diferencia relevante frente a los datasets de medida ya extendidos**: cada
registro trae `live_pct` (afluencia en vivo, puede ser `null`) y
`typical_by_hour` (patrón habitual por día de la semana, 24 valores por
día) — dos formas de dato con presencia opcional dentro del mismo registro.

## Objetivo

Crear `procesamiento/silver_gold/afluencia_lugares/` con la misma estructura
de subpaquete que `procesamiento/silver_gold/trafico/` (sin `geo.py`, ya
viene en WGS84):

- `transform.py`: puerta de calidad — campos clave no nulos (`place_id` o
  equivalente, nombre del lugar), `live_pct` entre 0-100 cuando no sea
  `null`, cada valor de `typical_by_hour` entre 0-100 cuando esté presente;
  no descartes registros solo por tener `live_pct` a `null` (es un valor
  válido documentado en la tarea 012, no un error).
- `aggregate.py`: agregación Silver→Gold ya decidida, no dediques tiempo a
  evaluar alternativas — por `(place_id, fecha, hora)`: `live_pct` medio
  cuando esté disponible, junto con el valor de `typical_by_hour`
  correspondiente a ese día de la semana/hora tomado del mismo registro.
  Implementa directamente.
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas.
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue. **Para el informe de Great Expectations, escribe directamente a
  S3 vía `boto3` (`s3_client.put_object(...)`), NO uses
  `sc.parallelize(...).saveAsTextFile(...)`** — ese patrón causó un bug real
  de producción en la tarea 051 (incompatible con el runtime de Glue).
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/afluencia_lugares_madrid_sample.json` (los 5
  registros mock existentes, incluido el de Plaza Mayor con
  `live_pct`/`typical_by_hour` a `null`), sin `pyspark`/Great Expectations
  instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/afluencia_lugares/*`, `silver/afluencia_lugares/*`,
  `gold/afluencia_lugares_*/*` con el nombre que decidas, catálogo
  Silver/Gold) — **sin aplicar**.

## Restricciones

- Alcance: solo este dataset.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.
- No intentes obtener ni configurar `GOOGLE_MAPS_API_KEY` — sigue fuera de
  alcance de esta tarea (ver `doc/012-...md`).
- No dediques tiempo a evaluar alternativas de diseño para la agregación de
  Gold — ya está decidida arriba. Las tareas 055 y 057 agotaron el
  presupuesto ($6, sin comitear nada) precisamente por deliberar demasiado
  este tipo de decisión en datasets no numéricos — no repitas ese patrón.

## Criterios de aceptación

- `procesamiento/silver_gold/afluencia_lugares/` completo, con tests en
  verde, verificado contra el fixture mock existente.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado.
