---
id: 73
slug: limpieza-duplicados-bicimad-lanzar
title: 'URGENTE: lanzar la reconstrucción deduplicada de bicimad (sin esperar a que
  termine)'
status: failed
force: true
allow_infra_apply: true
branch: task/073-limpieza-duplicados-bicimad-lanzar
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: claude finalizó sin crear ningún commit
created_at: '2026-08-22T21:40:00+00:00'
updated_at: '2026-08-22T23:00:23.653968+00:00'
started_at: '2026-08-22T22:53:43.317331+00:00'
submitted_at: null
merged_at: null
---

## Contexto

**Cuatro intentos previos de limpiar los duplicados de `bicimad` han
terminado sin comitear nada**, cada uno dejando el dato en un estado
intermedio distinto (fechas borradas sin reconstruir, compactación sin
deduplicar de verdad). Sospecha fundamentada: la tarea combinaba borrar S3,
lanzar un job de Glue de varios minutos, **esperar a que termine dentro de
la misma sesión**, verificar con Athena y documentar — demasiado para una
sola sesión cuando además hay que esperar activamente a AWS. Esta tarea
**se divide en dos**: esta primera solo prepara y lanza la reconstrucción,
sin esperar a que termine; la 074 la verifica y la completa.

`trafico` (Silver + Gold) ya está arreglado y verificado — no lo toques.
`bicimad` sigue masivamente duplicado (última comprobación: un registro con
`n=6752` repeticiones, y solo 4 de las ~14 fechas de Bronze presentes en
Silver tras los intentos previos, con huecos).

**Por qué hace falta un job nuevo, no basta con relanzar el de producción**:
tras la tarea 072, `glue_bronze_to_silver.py`/`glue_silver_to_gold.py` de
`bicimad` calculan internamente **una única hora/partición concreta** a
procesar (la anterior a la ejecución) — no aceptan un `--bronze_path`/
`--silver_path` que apunte a "todo el histórico". Para una reconstrucción
completa hace falta un script aparte, de un solo uso.

**`force: true`** (a diferencia del resto de esta serie): esta tarea solo
prepara y lanza, no toca ningún dato todavía de forma irreversible más allá
de lo que ya se va a rehacer — el borrado real y la verificación quedan en
la 074, que si es `force: false`.

## Objetivo

Preparar y lanzar, sin esperar a que termine, la reconstrucción deduplicada
de Silver de `bicimad`.

## Alcance concreto

1. Escribe `procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`: un
   script de Glue de un solo uso (documenta claramente en su docstring que
   NO es parte del pipeline de producción incremental) que:
   - Lee **todo** `s3://madrono-tfm-dev-bronze-222234418587/bicimad/` de una
     vez (sin acotar a una partición).
   - Aplica la misma normalización que ya usa `glue_bronze_to_silver.py`
     (reutiliza sus funciones si es sencillo, no la reimplementes).
   - Aplica `.dropDuplicates(["station_id", "measured_at"])` antes de
     escribir.
   - Escribe a Silver con `mode("overwrite")` (no `append` — el prefijo ya
     se habrá borrado antes de lanzar este job, ver paso 3).
2. Añade a `infra/terraform/glue.tf` un `aws_glue_job` nuevo
   (`bicimad_silver_backfill_dedup` o similar) que apunte a este script,
   reutilizando el mismo rol IAM/artefacto de librería/worker config que ya
   usa `bicimad_bronze_to_silver` — sin trigger ni schedule, se lanza a
   mano.
3. `terraform apply` acotado con `-target` a este único recurso nuevo (y su
   `aws_s3_object` de script si aplica) — mismo cuidado que el resto de la
   serie con el artefacto compartido de `procesamiento/` (revisa
   `doc/072-...md`).
4. Borra con `aws s3 rm --recursive` **todo** el contenido de
   `s3://madrono-tfm-dev-silver-222234418587/bicimad/`.
5. Lanza el job nuevo con `aws glue start-job-run` — **anota el `JobRunId`
   que devuelve, no esperes a que termine, no hagas `get-job-run` en
   bucle**.
6. Documenta en `doc/073-limpieza-duplicados-bicimad-lanzar.md`: el
   resumen de los cuatro intentos previos (una tabla corta), qué escribiste
   y aplicaste en esta sesión, y **el `JobRunId` exacto** para que la tarea
   074 lo recoja.

## Restricciones

- Alcance: solo preparar y lanzar — **no esperes a que el job termine, no
  verifiques el resultado, no toques Gold todavía**, eso es la 074.
- NO toques `trafico` — ya está cerrado.
- NO toques Bronze.
- NO reviertas ni toques el arreglo de lectura incremental de la tarea 072
  ni sus triggers ni los jobs de producción existentes.
- **Antes de terminar, confirma que dejas un commit real** con el
  `JobRunId` documentado — sin esto, la 074 no puede continuar.

## Criterios de aceptación

- `glue_backfill_dedup.py` escrito, con `dropDuplicates` sobre la clave
  correcta.
- El job de Glue nuevo aplicado en AWS real y lanzado.
- `doc/073-limpieza-duplicados-bicimad-lanzar.md` documenta el `JobRunId`
  exacto y el resumen de intentos previos.
- Hay un commit real con estos cambios.
