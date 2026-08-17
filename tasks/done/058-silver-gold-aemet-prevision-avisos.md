---
id: 58
slug: silver-gold-aemet-prevision-avisos
title: 'Silver/Gold: previsión y avisos AEMET (siguiendo el patrón de la tarea 041)'
status: done
force: true
allow_infra_apply: false
branch: task/058-silver-gold-aemet-prevision-avisos
pr_number: 105
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/105
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-16T14:45:00+00:00'
updated_at: '2026-08-17T19:59:53.220570+00:00'
started_at: '2026-08-17T19:45:09.779825+00:00'
submitted_at: '2026-08-17T19:58:46.765797+00:00'
merged_at: '2026-08-17T19:58:50Z'
---

## Contexto

Continúa la extensión del patrón Bronze→Silver→Gold de la tarea 041 (lee
`procesamiento/README.md` antes de empezar) a `aemet_prevision_avisos`
(`ingesta/capturas/aemet_prevision_avisos.py`, ver `doc/018-...md` y la
sección correspondiente de `ingesta/README.md`). AEMET ya tiene una API key
real en SSM (fijada fuera de este pipeline en una sesión anterior) — el
productor ya no está bloqueado en producción, aunque en esta EC2 de
desarrollo puede seguir devolviendo `is_mock: true` si la clave no está
disponible como variable de entorno local.

**Diferencia relevante frente a los datasets de medida ya extendidos**: esto
es una **previsión** (varios valores futuros por día, no una medida del
instante actual) más avisos meteorológicos activos — dos formas de dato
distintas dentro del mismo productor. La puerta de calidad y la agregación
de Gold deben tratarlas por separado; no fuerces un único esquema de
agregación para ambas.

## Objetivo

Crear `procesamiento/silver_gold/aemet_prevision_avisos/` con la misma
estructura de subpaquete que `procesamiento/silver_gold/trafico/`:

- `transform.py`: puerta de calidad — separada para previsión (campos clave
  no nulos, fecha de validez futura respecto a `ingested_at`, rangos
  plausibles de temperatura/probabilidad de precipitación) y para avisos
  (campos clave no nulos, nivel de aviso dentro de los valores válidos de
  AEMET — amarillo/naranja/rojo).
- `aggregate.py`: agregación Silver→Gold ya decidida, no dediques tiempo a
  evaluar alternativas — para previsión, por `(municipio_o_zona,
  leadtime_día)`: valores medios/máximos previstos para ese horizonte; para
  avisos, por `(zona, fecha, nivel)`: conteo de avisos activos. Implementa
  directamente.
- `ge_suite.py`: mismas expectativas que `transform.validate_record`,
  declarativas.
- `glue_bronze_to_silver.py` / `glue_silver_to_gold.py`: entry points reales
  de Glue. **Para el informe de Great Expectations, escribe directamente a
  S3 vía `boto3` (`s3_client.put_object(...)`), NO uses
  `sc.parallelize(...).saveAsTextFile(...)`** — ese patrón causó un bug real
  de producción en la tarea 051 (incompatible con el runtime de Glue).
- Tests en `procesamiento/tests/` con un fixture basado en
  `ingesta/capturas/samples/aemet_prevision_avisos_sample.json`, cubriendo
  previsión y avisos, sin `pyspark`/Great Expectations instalados.
- Bloque en `infra/terraform/glue.tf` (job de Glue x2, rol IAM acotado por
  prefijo `bronze/aemet_prevision_avisos/*`,
  `silver/aemet_prevision_avisos/*`, `gold/aemet_prevision_avisos_*/*` con
  el nombre que decidas, catálogo Silver/Gold) — **sin aplicar**.

## Restricciones

- Alcance: solo este dataset.
- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales.
- NO instales `pyspark`/`great_expectations` en esta EC2.
- Si al regenerar la muestra local sigue devolviendo `is_mock: true` por no
  tener `AEMET_API_KEY` disponible en esta EC2, documenta que es por eso
  (mismo criterio que las tareas 038/045) y sigue adelante con el fixture
  disponible.
- No dediques tiempo a evaluar alternativas de diseño para la agregación de
  Gold — ya está decidida arriba. Las tareas 055 y 057 agotaron el
  presupuesto ($6, sin comitear nada) precisamente por deliberar demasiado
  este tipo de decisión en datasets no numéricos — no repitas ese patrón.

## Criterios de aceptación

- `procesamiento/silver_gold/aemet_prevision_avisos/` completo, con tests en
  verde.
- `infra/terraform/glue.tf` extendido, `terraform validate` limpio, sin
  aplicar.
- `procesamiento/README.md` actualizado, incluyendo la justificación de los
  criterios de calidad/agregación elegidos para previsión y para avisos.
