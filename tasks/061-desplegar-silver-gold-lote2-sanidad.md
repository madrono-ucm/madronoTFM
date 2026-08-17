---
id: 61
slug: desplegar-silver-gold-lote2-sanidad
title: Desplegar Glue Silver/Gold para el segundo lote (8 datasets) y verificar con
  un job de sanidad
status: in_progress
force: false
allow_infra_apply: true
branch: task/061-desplegar-silver-gold-lote2-sanidad
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-17T21:50:00+00:00'
updated_at: '2026-08-17T22:49:08.477673+00:00'
started_at: '2026-08-17T22:49:08.477649+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Las tareas 053-060 escribieron (sin aplicar) el código y el Terraform de
Glue para 8 datasets más: `ruido`, `aforos_peatones_bicicletas`,
`cartelera_cines_estrenos`, `agenda_eventos`, `bluesky_menciones`,
`aemet_prevision_avisos`, `cams_calidad_aire`, `afluencia_lugares`. Ninguno
se ha aplicado nunca contra AWS real. El primer lote de 6 (`trafico`,
`transporte_publico_emt`, `bicimad`, `aparcamientos`, `calidad_aire`,
`meteorologia`) ya está desplegado y verificado (tareas 051/052).

**Aprendizaje de la tarea 051 (dos intentos fallidos sin commit)**: aplicar
toda la infraestructura y lanzar la matriz completa de verificación en una
sola tarea agotó el tiempo/turnos disponibles antes de comitear nada, dos
veces seguidas. Por eso esta tarea, igual que la 051 reducida, se limita a
**aplicar + un único job de sanidad por dataset** (no la matriz completa
Bronze→Silver→Gold de los 8 × 2 etapas) — la verificación completa es la
tarea 062, deliberadamente separada.

**`force: false` deliberado**: quiero revisar el resultado antes de
fusionar.

**Excepción de alcance** (`allow_infra_apply: true`): permiso para
`terraform apply` de los recursos de `infra/terraform/glue.tf` para estos 8
datasets y para lanzar manualmente los Glue jobs (`aws glue start-job-run`).

## Objetivo

Aplicar la infraestructura de Glue para los 8 datasets y lanzar, para cada
uno, **un único job de sanidad** (Bronze→Silver) que confirme que el código
arranca y corre sin errores de plataforma (no hace falta validar el
resultado exhaustivamente todavía, eso es la 062).

## Alcance concreto

1. `terraform plan` sobre `infra/terraform/glue.tf`: confirma qué se va a
   crear para estos 8 datasets (jobs de Glue, roles IAM, tablas de catálogo)
   — no debe incluir ningún trigger/schedule de Glue todavía (eso es la
   tarea 064, posterior y deliberadamente separada). Si algo de lo escrito
   en 053-060 incluyera un trigger por error, elimínalo antes de aplicar.
2. `terraform apply`.
3. Para cada uno de los 8 datasets, lanza `aws glue start-job-run` del job
   Bronze→Silver contra el lote más reciente ya presente en Bronze real
   (`s3://madrono-tfm-dev-bronze-222234418587/<dataset>/...`), espera a que
   termine, y confirma que no falla por un problema de plataforma (import
   error, tipo de dato no serializable al escribir el DataFrame de Spark —
   presta atención especial a los campos de tipo lista/array como
   `language_versions`, `phenomena`, `langs`, que no existían en el primer
   lote y podrían necesitar un tratamiento distinto en Spark).
4. Si algún job falla por un bug de código real (no de permisos/
   credenciales), arréglalo — mismo criterio que la tarea 051 con
   `saveAsTextFile`. Si el arreglo es sistemático (afecta a varios
   datasets), corrígelo en todos los que aplique, no solo en el primero que
   encuentres.
5. Documenta en `doc/061-desplegar-silver-gold-lote2-sanidad.md` el
   resultado del job de sanidad por dataset (éxito, o el error exacto si
   sigue fallando tras un intento razonable de arreglo).

## Restricciones

- NO lances la matriz completa de verificación (Bronze→Silver→Gold × 8
  datasets) — eso es la tarea 062.
- NO crees ningún trigger/schedule de Glue — eso es la tarea 064.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni el primer lote de 6 datasets ya
  desplegado.
- **Antes de terminar, confirma que dejas un commit real** (código +
  `doc/061-...md`) aunque algún dataset siga fallando — un resultado
  parcial documentado es mucho más útil que terminar sin commitear nada
  (el motivo por el que la tarea 051 tuvo que reintentarse dos veces).

## Criterios de aceptación

- Los recursos de `infra/terraform/glue.tf` para los 8 datasets están
  aplicados en AWS real, sin ningún trigger/schedule.
- Cada uno de los 8 datasets tiene al menos un job de sanidad ejecutado,
  documentado (éxito o error exacto).
- `doc/061-desplegar-silver-gold-lote2-sanidad.md` documenta el resultado.
- Hay un commit real con estos cambios.
