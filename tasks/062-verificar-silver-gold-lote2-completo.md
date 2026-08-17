---
id: 62
slug: verificar-silver-gold-lote2-completo
title: "Verificar Bronze→Silver→Gold de extremo a extremo para el segundo lote (8 datasets)"
status: pending
force: false
allow_infra_apply: true
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

La tarea 061 aplicó la infraestructura de Glue para el segundo lote de 8
datasets (`ruido`, `aforos_peatones_bicicletas`, `cartelera_cines_estrenos`,
`agenda_eventos`, `bluesky_menciones`, `aemet_prevision_avisos`,
`cams_calidad_aire`, `afluencia_lugares`) y confirmó con un job de sanidad
por dataset que arrancan sin errores de plataforma. Esta tarea completa la
verificación real: una carga manual y puntual (sigue sin querer producción
continua todavía — eso es la tarea 064) para cada uno, confirmando que
Bronze→Silver→Gold produce lo esperado.

La infraestructura ya está aplicada (tarea 061) — esta tarea no debería
necesitar `terraform apply` salvo que encuentres algo que corregir.

**`force: false` deliberado**: quiero revisar los resultados reales antes de
decidir programar esto en producción (tarea 064).

## Objetivo

Para cada uno de los 8 datasets, lanzar el job Bronze→Silver contra el lote
más reciente ya presente en Bronze, y el job Silver→Gold correspondiente
(recuerda que `aemet_prevision_avisos` tiene dos pares de jobs, previsión y
avisos, si así se implementó), y verificar que el resultado es el esperado.

## Alcance concreto

1. Para cada dataset: `aws glue start-job-run` del job Bronze→Silver,
   espera a que termine, y confirma en S3 que Silver contiene los registros
   esperados (esquema correcto, puerta de calidad aplicada) y que el informe
   de Great Expectations se escribió correctamente.
2. Lanza el job Silver→Gold correspondiente y confirma que Gold tiene la
   agregación esperada (compara a mano al menos un grupo de agregación
   contra los registros Silver de origen, por dataset) — usa como
   referencia la salida real que ya se generó localmente contra los
   fixtures (ver conversación/commit de las tareas 053-060) para saber qué
   forma debe tener el resultado.
3. Documenta en `doc/062-verificar-silver-gold-lote2-completo.md`, por
   dataset: si la carga completó sin error, cuánto tardó, cuántos registros
   entraron/salieron de cada etapa, y cualquier discrepancia con lo
   esperado.
4. Si algún dataset falla por un problema real de código, documenta el
   error exacto — no intentes depurarlo más allá de un intento razonable,
   sería una tarea de seguimiento.
5. Si el coste/tiempo de alguna ejecución resulta sorprendentemente alto,
   documéntalo (relevante para decidir la cadencia de la tarea 064).

## Restricciones

- NO crees ningún trigger/schedule de Glue — eso es la tarea 064.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni el primer lote de 6 datasets.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/062-...md`, aunque algún dataset siga fallando — prioriza dejar
  documentados los datasets que sí completaste antes de quedarte sin
  presupuesto, en vez de arriesgarte a terminar sin nada comiteado.

## Criterios de aceptación

- Cada uno de los 8 datasets tiene al menos una ejecución real y verificada
  de Bronze→Silver→Gold, documentada con los resultados reales (o, si
  alguno falla, el error exacto documentado).
- `doc/062-verificar-silver-gold-lote2-completo.md` documenta el resultado
  detallado, dataset por dataset.
- Hay un commit real con estos cambios.
