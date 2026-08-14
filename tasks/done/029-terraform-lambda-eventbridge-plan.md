---
id: 29
slug: terraform-lambda-eventbridge-plan
title: 'Terraform: Lambda + EventBridge Scheduler para los productores (plan, sin
  aplicar)'
status: done
force: true
allow_infra_apply: true
branch: task/029-terraform-lambda-eventbridge-plan
pr_number: 76
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/76
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-14T15:41:31+00:00'
updated_at: '2026-08-14T21:27:49.214563+00:00'
started_at: '2026-08-14T21:16:55.600286+00:00'
submitted_at: '2026-08-14T21:26:41.728763+00:00'
merged_at: '2026-08-14T21:26:45Z'
---

## Contexto

Quinto paso hacia producción, tras la 025 (BronzeWriter+S3) y los lotes 026-028
(`lambda_handler` por productor, repartidos en 3 tareas más pequeñas tras un
primer intento único que agotó presupuesto). Esta tarea escribe el Terraform que
despliega cada productor como una función Lambda con su propio schedule de
EventBridge Scheduler, y genera el `plan` — **sin aplicarlo**, igual que el patrón
ya usado en la tarea 014: el `apply` es la tarea 030, creada aparte tras revisar
este plan.

**Excepción de alcance** (`allow_infra_apply: true`): tienes permiso para ejecutar
`terraform init`/`plan` (y los comandos `aws`/`terraform` de solo lectura que
necesites para investigar, p.ej. verificar el rol de ingesta existente) contra la
infraestructura real. **NO ejecutes `terraform apply` en esta tarea.**

## Cadencias (ya decididas, no las reinventes)

| Productor (dataset) | Schedule |
|---|---|
| trafico | `rate(5 minutes)` |
| emt_llegadas / transporte público | `rate(5 minutes)` |
| bicimad | `rate(5 minutes)` |
| aparcamientos | `rate(15 minutes)` |
| calidad_aire | minutos 15/35/55 de cada hora (`cron` con lista de minutos) |
| meteorologia | minutos 15/35/55 de cada hora |
| ruido | 1x/día laborables, p.ej. 07:00 hora de Madrid |
| afluencia (patrón típico) | 1x/semana, p.ej. lunes 06:00 hora de Madrid |
| aforos_peatones_bicicletas | 1x/mes, p.ej. día 1 a las 06:00 hora de Madrid |
| bluesky (barrido por distrito) | `rate(1 hour)` |
| agenda_eventos | 1x/día, p.ej. 06:00 hora de Madrid |
| aemet_avisos | 4 schedules, uno por ventana real de AEMET: ~08:00, ~11:00, ~18:00 y 23:50, hora de Madrid |
| aemet_prevision | 2x/día, p.ej. 07:00 y 14:00 hora de Madrid |
| cams (previsión aire UE) | 2 schedules en **UTC**: ~07:15 y ~09:00 (tras las tandas reales de CAMS a las 06:45/08:30 UTC) |
| cartelera_cines (estrenos) | 1x/día, p.ej. 08:00 hora de Madrid |

Usa `ScheduleExpressionTimezone = "Europe/Madrid"` en EventBridge Scheduler para
todo lo anclado a hora peninsular (evita convertir a mano y lidiar con el cambio de
hora); usa UTC explícito solo para CAMS, que está documentado en UTC.

## Objetivo

Escribir el Terraform (en `infra/terraform/`, ampliando lo ya existente, no un
proyecto aparte) que despliega una `aws_lambda_function` + un
`aws_scheduler_schedule` por cada fila de la tabla, y generar su `plan`.

## Alcance concreto

1. Diseña el empaquetado de cada Lambda (código de `ingesta/` + dependencias de
   `ingesta/requirements.txt`; `boto3` no hace falta empaquetarlo, ya está en el
   runtime de Lambda). Un único paquete compartido reutilizado por todas las
   funciones es razonable (mismo código base, distinto `handler` por función) —
   decide con criterio y documenta.
2. Define en Terraform un `locals` o `variable` de tipo mapa con una entrada por
   fila de la tabla (nombre, handler, expresión de schedule, timezone), y usa
   `for_each` sobre ese mapa para crear las `aws_lambda_function` +
   `aws_scheduler_schedule` — no repitas 14 bloques de recurso casi idénticos a
   mano.
3. Amplía el rol de ingesta existente (`aws_iam_role.ingestion` de `main.tf`, tarea
   001/015) con los permisos de CloudWatch Logs que toda Lambda necesita
   (`logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`, acotado a
   sus propios log groups) — no le añadas nada más allá de eso y de lo que ya
   tenía (escritura en Bronze).
4. Crea el rol IAM que EventBridge Scheduler necesita para invocar cada Lambda
   (`scheduler.amazonaws.com` como principal, permiso `lambda:InvokeFunction`
   acotado a las funciones de esta tarea) — es un rol distinto del de ejecución de
   la Lambda.
5. `terraform init` + `terraform plan` (reutiliza el backend ya existente de la
   tarea 014/015, mismo bucket de estado). Copia la salida completa del plan en
   `doc/029-terraform-lambda-eventbridge-plan.md`, igual que hizo la tarea 014.
6. NO ejecutes `terraform apply`.

## Restricciones

- NO ejecutes `terraform apply`. Si el plan no es el esperado (recursos de más o
  de menos), documenta la diferencia en vez de forzarlo.
- NO modifiques los recursos ya aplicados del lakehouse (buckets, rol de ingesta
  existente) más allá de añadirle la policy de CloudWatch Logs descrita arriba.
- No captures secretos (API keys de AEMET/CAMS/EMT) en el código Terraform ni en
  el plan documentado — deben inyectarse a las Lambdas como variables de entorno
  gestionadas fuera de git (Terraform puede referenciarlas vía SSM Parameter Store
  o Secrets Manager en vez de hardcodearlas en `.tf`; decide y documenta, sin
  escribir ningún valor real en ningún fichero commiteado).

## Criterios de aceptación

- Terraform para las 14 funciones Lambda + sus schedules, vía `for_each` sobre una
  tabla parametrizada, escrito y con `plan` limpio (sin errores).
- `doc/029-terraform-lambda-eventbridge-plan.md` contiene la salida completa del
  plan y confirma que no se ha aplicado nada.
- Ninguna credencial real aparece en ningún fichero commiteado.
