---
kind: fil
title: "Observabilidad: alertado de fallos de Glue + chequeo de frescura de Gold"
owner: Filippos (interactive)
status: pending
allow_infra_apply: true
created_at: "2026-08-30"
depends_on: []
---

## Contexto

Los incidentes `FIL_09` (37/48 jobs de Glue en `LAUNCH ERROR` 28 h) y
`FIL_11` (Gold de ruido/avisos congelado escribiendo 0 filas) se
encontraron por **QA manual / suerte**, no por ninguna alarma. Un job de
Glue puede dar `SUCCEEDED` con 0 filas indefinidamente sin que nada lo
señale. Es el hueco de operabilidad más visible del build.

## Objetivo

Dos señales, mínimas pero reales:

1. **Fallos de Glue** → alarma CloudWatch sobre la métrica
   `glue.driver.aggregate.numFailedTasks` / estado `FAILED` de los job runs
   (o un EventBridge rule sobre `Glue Job State Change` → SNS).
2. **Frescura de Gold** → un chequeo que, por cada tabla Gold, compara
   `max(date)` / `max(processed_at)` con "ahora" y avisa si el desfase supera
   un umbral por dataset (horario vs diario vs fuente congelada como
   `aforos`). Detecta el fallo silencioso de `FIL_11` sin depender del
   estado del job.

## Alcance

1. `herramientas/salud/frescura_gold.py` — script (mismo estilo que
   `herramientas/costes/`): consulta Athena, umbral por dataset, salida
   tabla + código de salida ≠ 0 si algo está estancado. Con tests
   (`FakeAthenaClient`).
2. `infra/terraform/`: `aws_cloudwatch_event_rule` sobre `Glue Job State
   Change` (estados `FAILED`/`TIMEOUT`) + `aws_sns_topic` +
   `aws_sns_topic_subscription` (email, dirección por `var`). Coste ~0.
3. **El pipeline está congelado** (`pipeline_enabled=false`): el chequeo de
   frescura se valida contra el estado actual (debe reportar todo estancado
   *a propósito* salvo lo que no crece) y se documenta cómo se comportaría
   en producción. La alarma de Glue se aplica pero no disparará hasta
   reanudar.

## Criterios de aceptación

- `frescura_gold.py` corre contra Athena real y clasifica correctamente cada
  tabla (fresca / estancada-esperado / estancada-anómalo).
- Regla EventBridge + SNS aplicadas (`terraform apply -target`), suscripción
  confirmada.
- `doc/FIL-16-...md` con el diseño y una nota en `infra/OPERACION.md`.

## Restricciones

- Sin dashboards (queda para §7.5). Email/SNS es suficiente.
- `terraform apply` sólo tras revisión humana (mismo criterio que 098/100).
