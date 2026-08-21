---
id: 68
slug: athena-partition-projection
title: Arreglar el descubrimiento de particiones en Athena (Partition Projection)
status: in_progress
force: false
allow_infra_apply: true
branch: task/068-athena-partition-projection
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-21T09:00:00+00:00'
updated_at: '2026-08-21T20:16:38.455047+00:00'
started_at: '2026-08-21T20:16:38.455024+00:00'
submitted_at: null
merged_at: null
---

## Contexto

La tarea 066 desplegó Athena y confirmó con una consulta real un bug
silencioso: los jobs de Glue escriben Silver/Gold con `DataFrame.write`
plano de Spark (`partitionBy(...).parquet(path)`), no a través de un sink
del catálogo, así que **escribir una partición nueva en S3 no la registra
en el catálogo de Glue** — cualquier consulta devuelve `0` filas o un
resultado incompleto hasta que alguien ejecuta `MSCK REPAIR TABLE` a mano
(confirmado en vivo: `SELECT COUNT(*) FROM trafico` pasó de `0` a
`6.186.491` tras el repair). Con Silver/Gold en producción continua desde
la tarea 065 (particiones nuevas cada hora o cada día), este problema se
repite solo constantemente — bloquea en silencio cualquier cosa que
consulte estos datos, incluido el futuro asistente.

`doc/066-consulta-athena-silver-gold.md` (sección "Hallazgo confirmado...")
ya evaluó dos alternativas y recomendó la primera:

**Decisión ya tomada (no la reabras)**: usar **Athena Partition
Projection** (`parameters` en cada `aws_glue_catalog_table`, con
`projection.enabled = "true"` y un `projection.<key>.type`/`.range`/
`.format` por cada clave de partición) en vez de `MSCK REPAIR TABLE`
periódico — Athena calcula las rutas S3 posibles en tiempo de consulta, sin
depender del metastore ni de ningún paso extra tras cada job.

**`force: false` deliberado**: cambia cómo Athena resuelve todas las
consultas de producción — quiero revisar que sigue devolviendo lo mismo que
antes (con los datos ya reparados a mano) antes de fusionar.

## Objetivo

Configurar Partition Projection en las 28 tablas del catálogo (`_silver` y
`_gold` de los 14 datasets) y confirmar con consultas reales que ya no hace
falta `MSCK REPAIR TABLE` para ver datos nuevos.

## Alcance concreto

1. Para cada uno de los 28 `aws_glue_catalog_table` en `infra/terraform/glue.tf`,
   añade a su bloque `parameters` (y a `storage_descriptor.location` si
   Partition Projection lo requiere con `${...}` — revísalo en la
   documentación de AWS) las claves de proyección según las claves de
   partición reales de esa tabla:
   - Claves `fecha` (todas las tablas): `projection.fecha.type = "date"`,
     `projection.fecha.range = "2026-08-01,NOW+1DAY"`,
     `projection.fecha.format = "yyyy-MM-dd"`,
     `projection.fecha.interval = "1"`, `projection.fecha.interval.unit = "DAYS"`.
   - Claves `hora` (solo las tablas Silver que particionan por hora —
     revisa cuáles, no asumas que todas la tienen):
     `projection.hora.type = "integer"`, `projection.hora.range = "0,23"`,
     `projection.hora.digits = "2"`.
   - Si alguna tabla usa un nombre de partición distinto (revísalo, no
     asumas — p.ej. `fecha_validez` en CAMS), aplica el mismo patrón con el
     nombre real.
   - Añade también `projection.enabled = "true"` y
     `storage.location.template` (la plantilla de ruta S3 con `${fecha}`/
     `${hora}` sustituibles) según pida Partition Projection.
2. `terraform plan`/`apply` acotado con `-target` a los 28
   `aws_glue_catalog_table` únicamente (sigue el patrón ya documentado en
   `doc/065-aplicar-scheduling-silver-gold.md`/`doc/066-...md` para no
   arrastrar la deriva no relacionada de Kafka/`procesamiento/` a este
   apply).
3. Verifica repitiendo (sin `MSCK REPAIR TABLE` esta vez) al menos 3 de las
   5 consultas que ya ejecutó la tarea 066 (`silver.trafico`,
   `gold.trafico_por_punto_hora`, `silver.ruido`) y confirma que el
   resultado es igual o mayor al que dio la 066 (mayor es normal y
   esperado: ha seguido llegando producción real desde entonces).
4. Documenta en `doc/068-athena-partition-projection.md` la configuración
   aplicada por tabla y el resultado de la reverificación (antes/después,
   con los números reales).

## Restricciones

- NO ejecutes `terraform apply` sin `-target` — el repo tiene código sin
  aplicar (Kafka) que no debe desplegarse como efecto colateral.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni el código de
  `procesamiento/silver_gold/` — esta tarea es solo sobre el catálogo de
  Glue.
- No reabras la decisión de usar Partition Projection frente a la
  alternativa de `MSCK REPAIR` periódico — ya está tomada arriba.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/068-...md`, aunque alguna tabla necesite un ajuste distinto al
  patrón general de arriba — documenta la excepción, no la fuerces a
  encajar en el patrón si no encaja.

## Criterios de aceptación

- Las 28 tablas del catálogo tienen Partition Projection configurado y
  aplicado en AWS real.
- Al menos 3 consultas reales confirman datos visibles sin ejecutar
  `MSCK REPAIR TABLE`.
- `doc/068-athena-partition-projection.md` documenta la configuración y el
  resultado.
- Hay un commit real con estos cambios.
