---
kind: fil
title: "Observabilidad: alertado de fallos de Glue + chequeo de frescura de Gold"
owner: Filippos (interactive)
status: done
allow_infra_apply: true
created_at: "2026-08-30"
resolved_at: "2026-08-30"
depends_on: []
---

## Resolución (2026-08-30)

1. **Frescura de Gold** — `herramientas/salud/frescura_gold.py` +
   `tests/test_frescura_gold.py` (11). Por cada tabla Gold: `max(date)` /
   `max(processed_at)` vs ahora, umbral por cadencia (horaria 30 h, diaria
   50 h, ruido 192 h por su retraso de publicación —`FIL_11`—, `aforos`
   descontinuada). Datasets con partición al futuro (agenda, cartelera,
   avisos, previsión) usan `processed_at`. Exit 1 en modo producción si algo
   estancado; `--pipeline-congelado` (auto desde `PIPELINE_ENABLED=false`) →
   exit 0 salvo anomalía real. **Verificado en vivo contra Athena real**
   (2026-08-30): 14/15 frescas + ruido fresca + `aforos` descontinuada_ok,
   0 alertarían en producción (la ingesta se congeló ese día).
2. **Fallos de Glue** — `infra/terraform/observabilidad.tf`: EventBridge
   (`Glue Job State Change` FAILED/TIMEOUT/ERROR) → SNS (con
   `input_transformer` a email legible) → suscripción email opcional
   (`var.alertas_email`). `terraform validate` + `fmt -check` en verde.
   **Diseñado, sin `terraform apply`** (pipeline congelado → no dispararía;
   la suscripción email necesita confirmación manual): patrón de
   `glue_scheduling.tf`. Pasos de `apply -target` en `doc/FIL-16-...md`.
3. `doc/FIL-16-...md`, `herramientas/salud/README.md`, nota en
   `infra/OPERACION.md`.

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
