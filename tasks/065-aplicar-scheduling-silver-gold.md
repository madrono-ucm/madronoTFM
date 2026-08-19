---
id: 65
slug: aplicar-scheduling-silver-gold
title: Aplicar el scheduling de Silver/Gold en producción y verificar un disparo real
status: failed
force: false
allow_infra_apply: true
branch: task/065-aplicar-scheduling-silver-gold
pr_number: null
pr_url: null
attempts: 1
next_retry_at: null
last_error: 'ens":14450204,"cacheCreationInputTokens":146361,"webSearchRequests":0,"costUSD":6.033850200000002,"contextWindow":1000000,"maxOutputTokens":64000,"canonicalModel":"claude-sonnet-5","provider":"firstParty"}},"permission_denials":[],"terminal_reason":"budget_exhausted","fast_mode_state":"off","fast_mode_disabled_reason":"sdk_opt_in_required","subtype":"error_max_budget_usd","errors":["Reached
  maximum budget ($6)"],"type":"result","duration_ms":970980,"uuid":"f088ab77-6b2b-4fa9-915b-09e4e622c4c9"}

  '
created_at: '2026-08-17T21:50:00+00:00'
updated_at: '2026-08-19T23:43:06.844607+00:00'
started_at: '2026-08-19T23:26:52.080408+00:00'
submitted_at: null
merged_at: null
---

## Contexto

La tarea 064 escribió (sin aplicar) los `aws_glue_trigger` que programan
Silver/Gold para los 14 datasets. Esta tarea los aplica en AWS real —
**a partir de este `apply`, Silver/Gold pasa de carga manual puntual a
producción continua automática**, igual que en su día la tarea 030 hizo
arrancar la ingesta continua en Bronze.

**`force: false` deliberado**: es el punto real de arranque de producción
continua para esta capa — quiero revisar la verificación antes de fusionar,
mismo criterio que las tareas 030/033/039.

**Excepción de alcance** (`allow_infra_apply: true`): permiso para
`terraform apply` de los triggers y para observar/verificar ejecuciones
reales (incluye esperar a un disparo automático si el tiempo de la tarea lo
permite, o invocar el trigger manualmente vía `aws glue start-trigger` para
no depender de esperar a la hora programada).

## Objetivo

Aplicar los triggers y confirmar con al menos una ejecución real
(automática o forzada manualmente) que la cadena `SCHEDULED` (Bronze→Silver)
→ `CONDITIONAL` (Silver→Gold) funciona de extremo a extremo sin intervención
humana.

## Alcance concreto

1. `terraform plan`: confirma que el único cambio son los 14 (o más, según
   cómo se implementó AEMET) bloques de `aws_glue_trigger` nuevos — nada
   más.
2. `terraform apply`.
3. Para al menos 3 datasets representativos (uno del grupo "casi tiempo
   real", uno del grupo "diario", y `aemet_prevision_avisos` por su
   estructura de dos pares), fuerza el disparo con `aws glue start-trigger`
   sobre el trigger `SCHEDULED` correspondiente (no hace falta esperar a la
   hora programada) y confirma:
   - Que el job Bronze→Silver se ejecuta y termina con éxito.
   - Que el trigger `CONDITIONAL` dispara automáticamente el job
     Silver→Gold al terminar el anterior, sin que tú lo lances a mano.
   - Que Gold contiene el resultado esperado.
4. Para el resto de datasets, confirma al menos que el trigger `SCHEDULED`
   quedó correctamente creado y habilitado (`aws glue get-trigger`), aunque
   no fuerces su disparo — documenta cuáles verificaste de extremo a extremo
   y cuáles solo confirmaste como creados.
5. Documenta en `doc/065-aplicar-scheduling-silver-gold.md` el resultado
   detallado de los 3 disparos forzados, y la lista de los 14 triggers
   confirmados como creados/habilitados.

## Restricciones

- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni la ingesta Bronze.
- Si algún trigger se comporta de forma inesperada (no encadena, dispara
  dos veces, etc.), documenta el problema exacto — no intentes depurarlo
  más allá de un intento razonable, sería una tarea de seguimiento.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/065-...md`, aunque no hayas podido verificar los 14 de extremo a
  extremo.

## Criterios de aceptación

- Los `aws_glue_trigger` de los 14 datasets están aplicados y habilitados en
  AWS real.
- Al menos 3 datasets representativos tienen una cadena
  SCHEDULED→CONDITIONAL verificada de extremo a extremo con un disparo real
  (forzado o automático).
- `doc/065-aplicar-scheduling-silver-gold.md` documenta el resultado.
- Hay un commit real con estos cambios.
