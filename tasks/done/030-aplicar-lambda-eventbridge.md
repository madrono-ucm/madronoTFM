---
id: 30
slug: aplicar-lambda-eventbridge
title: Aplicar el despliegue de Lambda + EventBridge Scheduler (terraform apply)
status: done
force: false
allow_infra_apply: true
branch: task/030-aplicar-lambda-eventbridge
pr_number: 77
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/77
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-14T15:41:31+00:00'
updated_at: '2026-08-14T21:36:40.669257+00:00'
started_at: '2026-08-14T21:28:51.843301+00:00'
submitted_at: '2026-08-14T21:34:37.149565+00:00'
merged_at: '2026-08-14T21:36:23Z'
---

## Contexto

La tarea 029 dejó escrito y revisado (`doc/029-terraform-lambda-eventbridge-plan.md`)
el plan de despliegue de las 14 Lambdas programadas + sus schedules de
EventBridge Scheduler. Esta tarea lo aplica. **A diferencia de las tareas 014/015,
aquí `force` es `false` deliberadamente**: esto pone a producción 14 tareas
programadas que empezarán a ejecutarse solas y a generar coste (mínimo, pero
real, y continuo) en cuanto se apliquen — conviene que un humano fusione el PR a
mano tras revisar el resultado, no que se fusione solo.

**Excepción de alcance** (`allow_infra_apply: true`): tienes permiso para ejecutar
`terraform apply` sobre lo ya escrito y planificado en la tarea 029, y nada más.

## Objetivo

Aplicar el Terraform de la tarea 029 y verificar que las 14 Lambdas y sus
schedules quedan operativos.

## Alcance concreto

1. `terraform plan` de nuevo como comprobación de que nada ha cambiado desde la
   027 (mismo criterio que la tarea 015: si difiere, para y documenta en vez de
   aplicar).
2. Si coincide: `terraform apply -auto-approve`.
3. Verifica con `aws` CLI directo (no solo la salida de Terraform): las 14
   funciones Lambda existen (`aws lambda get-function`), y sus schedules están
   `ENABLED` (`aws scheduler get-schedule`).
4. Invoca **manualmente una vez** una o dos de las Lambdas de menor riesgo (p.ej.
   la de calendario/referencia si la hubiera, o la de menor frecuencia) con
   `aws lambda invoke` para confirmar que escriben de verdad en el bucket Bronze
   real — no esperes al primer disparo programado para descubrir un error de
   permisos o de código.
5. Copia en `doc/030-aplicar-lambda-eventbridge.md`: el resultado del `apply`, la
   verificación de las 14 Lambdas/schedules, y el resultado de la invocación
   manual de prueba (incluyendo si escribió correctamente en Bronze).

## Restricciones

- NO modifiques ningún fichero `.tf`.
- NO ejecutes `terraform destroy`.
- Si la invocación manual de prueba fallara, documenta el error exacto — no
  seas la que soluciona el problema aplicando cambios de código adicionales fuera
  del alcance de esta tarea; eso sería una tarea de seguimiento.

## Criterios de aceptación

- Las 14 Lambdas y sus schedules existen y están activos en AWS, verificado con
  `aws` CLI.
- Al menos una invocación manual de prueba confirma una escritura real en el
  bucket Bronze.
- `doc/030-aplicar-lambda-eventbridge.md` documenta el resultado completo.
