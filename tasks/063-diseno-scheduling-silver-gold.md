---
id: 63
slug: diseno-scheduling-silver-gold
title: "Diseñar y escribir (sin aplicar) el scheduling de Silver/Gold para los 14 datasets"
status: pending
force: true
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-17T21:50:00+00:00"
updated_at: "2026-08-17T21:50:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

Con las tareas 051/052 (lote 1, 6 datasets) y 061/062 (lote 2, 8 datasets)
verificadas contra AWS real, los 14 datasets de Silver/Gold funcionan con
carga manual puntual. Hasta ahora, deliberadamente, ninguna se ha programado
— esta tarea diseña ese scheduling (sin aplicarlo todavía, mismo patrón que
`doc/029-terraform-lambda-eventbridge-plan.md` hizo para Lambda antes de
aplicarlo en la tarea 030).

Bronze ya recibe datos reales de forma continua vía Lambda + EventBridge
Scheduler (`infra/terraform/lambda.tf`, `local.schedules`) con distintas
cadencias por dataset — revísalas antes de diseñar la cadencia de
Silver/Gold, que debe ser coherente con ellas (no tiene sentido procesar
Silver/Gold más rápido de lo que llega Bronze, pero tampoco hace falta
procesarlo tan seguido como llega Bronze si el objetivo es análisis por
hora/día).

## Objetivo

Diseñar la cadencia de Silver/Gold por dataset y el mecanismo de
orquestación, y escribir el Terraform correspondiente — sin aplicar.

## Decisiones ya tomadas (no las reabras, para evitar repetir el patrón de
las tareas 055/057, que agotaron presupuesto deliberando diseño en vez de
implementar)

- **Cadencia por grupo** (no cadencia individual por dataset, salvo que algo
  aquí resulte claramente incorrecto al revisarlo — en ese caso documenta
  por qué te desvías):
  - **Grupo "casi tiempo real"** (Bronze llega cada 5-15 min): `trafico`,
    `transporte_publico_emt`, `bicimad`, `aparcamientos`, `calidad_aire`,
    `meteorologia` → Silver/Gold **cada hora**, en el minuto 10 (deja tiempo
    a que el Bronze de esa hora ya esté escrito).
  - **Grupo "diario"** (Bronze llega 1x/día o más espaciado, o el propio
    dataset es un agregado diario como `ruido`): `ruido`,
    `cartelera_cines_estrenos`, `agenda_eventos`, `bluesky_menciones`,
    `aemet_prevision_avisos`, `cams_calidad_aire`, `afluencia_lugares`,
    `aforos_peatones_bicicletas` → Silver/Gold **1x/día**, a las 08:00 hora
    de Madrid (después de que el Bronze programado más tardío de cada uno ya
    haya corrido ese día — confírmalo por dataset contra
    `local.schedules` de `lambda.tf` y ajusta la hora si alguno la
    necesitara más tarde).
- **Mecanismo de orquestación: `aws_glue_trigger` nativo de Glue**, no Step
  Functions ni EventBridge Scheduler invocando Glue vía API — mismo
  principio de coste/complejidad mínima que el resto del proyecto (Glue ya
  tiene disparadores nativos, no hace falta una capa de orquestación
  adicional). Dos triggers por dataset: uno `SCHEDULED` (cron, la cadencia
  de arriba) que lanza el job Bronze→Silver, y uno `CONDITIONAL` encadenado
  (dispara el job Silver→Gold solo si el Bronze→Silver anterior terminó con
  éxito) — así Silver→Gold nunca corre sobre un Silver a medias o corrupto.

## Alcance concreto

1. Revisa `local.schedules` en `infra/terraform/lambda.tf` para los 14
   datasets y confirma/ajusta la hora de la cadencia diaria si alguno
   necesita una hora distinta a las 08:00 por llegar su Bronze más tarde.
2. Añade a `infra/terraform/glue.tf` (o un fichero nuevo,
   `infra/terraform/glue_scheduling.tf`, si prefieres separarlo — decide y
   documenta) un bloque `aws_glue_trigger` por dataset: uno `SCHEDULED` +
   uno `CONDITIONAL` encadenado, para los 14 datasets (recuerda que
   `aemet_prevision_avisos` tiene dos pares de jobs — decide si comparten
   cadencia o necesitan triggers independientes, y documenta por qué).
3. `terraform validate` limpio (`terraform init -backend=false`).
4. Documenta en `procesamiento/README.md` (nueva sección) la cadencia
   elegida por dataset y el mecanismo de triggers, con una tabla como la que
   ya existe en `ingesta/README.md` para los schedules de Bronze.

## Restricciones

- NO ejecutes `terraform apply` ni ningún comando `aws` con efectos reales
  — esta tarea es solo diseño y código, como la 041 con el piloto.
- No reabras las decisiones de cadencia/mecanismo ya tomadas arriba salvo
  que encuentres una razón concreta y la documentes — el objetivo es
  implementar rápido, no rediseñar.
- No toques los jobs de Glue en sí (`aws_glue_job`) ni el código de
  `procesamiento/` — esta tarea es solo sobre disparadores.

## Criterios de aceptación

- `infra/terraform/glue.tf` (o el fichero nuevo que decidas) tiene los 14
  bloques de `aws_glue_trigger` (SCHEDULED + CONDITIONAL encadenado),
  `terraform validate` limpio, sin aplicar.
- `procesamiento/README.md` documenta la cadencia por dataset y el
  mecanismo elegido.
