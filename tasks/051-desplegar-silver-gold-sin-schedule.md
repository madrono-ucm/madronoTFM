---
id: 51
slug: desplegar-silver-gold-sin-schedule
title: Desplegar Glue Silver/Gold en AWS (sin schedule) y verificar con una carga
  puntual
status: in_progress
force: false
allow_infra_apply: true
branch: task/051-desplegar-silver-gold-sin-schedule
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-16T09:30:00+00:00'
updated_at: '2026-08-16T07:54:03.695858+00:00'
started_at: '2026-08-16T07:54:03.695802+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Las tareas 041 y 046-050 escribieron (sin aplicar) el código y el Terraform de
Glue para 6 datasets: `trafico` (piloto) y `transporte_publico_emt`,
`bicimad`, `aparcamientos`, `calidad_aire`, `meteorologia`. Ninguno se ha
ejecutado nunca contra AWS real — ni siquiera el piloto de tráfico, cuyo
`ge_suite.py`/entry points de Glue quedaron **sin verificar por ejecución
real** (doc/041, sección "Qué no se ha podido ejecutar en este entorno") por
no poder instalar `pyspark`/Great Expectations en esta EC2.

Esta tarea despliega esa infraestructura por primera vez, pero
**deliberadamente sin dejar nada programado**: el objetivo ahora es
verificar que el código funciona de verdad contra Glue real (el primer smoke
test real de `pyspark`+GX de todo el proyecto), no empezar a cargar Silver/
Gold en producción de forma continua — eso es una decisión posterior,
después de revisar los resultados de esta carga puntual.

**`force: false` deliberado**: quiero revisar el resultado de la primera
ejecución real de Glue/Great Expectations (coste, tiempo, calidad del dato)
antes de fusionar.

**Excepción de alcance** (`allow_infra_apply: true`): permiso para
`terraform apply` de los recursos de `infra/terraform/glue.tf` y para lanzar
manualmente los Glue jobs (`aws glue start-job-run`).

## Objetivo

Aplicar la infraestructura de Glue para los 6 datasets y ejecutar, para cada
uno, **una única carga manual** Bronze→Silver→Gold contra un lote real ya
existente en Bronze, verificando que el resultado en Silver/Gold es el
esperado (esquema correcto, puerta de calidad aplicada, agregación
correcta).

## Alcance concreto

1. `terraform plan` sobre `infra/terraform/glue.tf`: confirma qué se va a
   crear (jobs de Glue, roles IAM, bases/tablas de catálogo) — no debe
   incluir ningún trigger/schedule de Glue (`aws_glue_trigger` con tipo
   `SCHEDULED`) ni ningún `aws_scheduler_schedule`; si el Terraform escrito
   en las tareas anteriores incluyera alguno por error, elimínalo antes de
   aplicar.
2. `terraform apply` (solo los recursos de `glue.tf`, no toques nada de
   `lambda.tf`/`ingesta`).
3. Para cada uno de los 6 datasets, lanza manualmente (`aws glue
   start-job-run`) el job Bronze→Silver contra el lote más reciente ya
   presente en el bucket Bronze real (`s3://madrono-tfm-dev-bronze-
   222234418587/<dataset>/...`), espera a que termine
   (`aws glue get-job-run`), y confirma en S3 que:
   - Silver contiene los registros esperados (número razonable, esquema
     correcto, ningún campo que debería haberse filtrado por la puerta de
     calidad).
   - El informe de Great Expectations se escribió correctamente.
4. Lanza el job Silver→Gold correspondiente contra lo que acabas de escribir
   en Silver, y confirma que Gold tiene la agregación esperada (compara a
   mano al menos un grupo `(id, fecha, hora)` contra los registros Silver de
   origen).
5. Documenta en `doc/051-desplegar-silver-gold-sin-schedule.md`, por
   dataset: si la carga completó sin error, cuánto tardó, cuántos registros
   entraron/salieron de cada etapa, y cualquier discrepancia entre lo
   esperado (según el código/tests de la tarea correspondiente) y lo real —
   incluye capturas de los valores reales, no solo "funcionó".
6. Si algún job falla por un problema real de código (no de credenciales
   IAM/permisos), documenta el error exacto — no intentes depurarlo ni
   arreglarlo aquí, sería una tarea de seguimiento (mismo criterio que la
   tarea 033 con Lambda).

## Restricciones

- NO crees ningún trigger/schedule para estos jobs de Glue — la ejecución de
  esta tarea es manual y puntual, a propósito.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni ningún recurso de la fase de
  ingesta — esta tarea es solo sobre `glue.tf`.
- Si el coste/tiempo de alguna ejecución de Glue resulta sorprendentemente
  alto, documéntalo explícitamente (es información relevante para decidir si
  programar esto en producción más adelante).

## Criterios de aceptación

- Los recursos de `infra/terraform/glue.tf` para los 6 datasets están
  aplicados en AWS real, sin ningún trigger/schedule.
- Cada uno de los 6 datasets tiene al menos una ejecución real y verificada
  de Bronze→Silver→Gold, documentada con los resultados reales obtenidos.
- `doc/051-desplegar-silver-gold-sin-schedule.md` documenta el resultado
  detallado, dataset por dataset, y cualquier discrepancia o problema
  encontrado.
