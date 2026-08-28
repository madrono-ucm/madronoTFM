---
kind: ml
title: "Tier 4 — reentrenamiento nocturno programado + backtest incremental"
owner: Filippos (interactive)
status: pending
depends_on: [ML_04]
created_at: "2026-08-28"
---

## Objetivo

Los datos crecen ~1 día cada día hasta la entrega (17/9). Reentrenar de
forma programada y hacer un backtest incremental convierte eso en una
historia de resultados para §7 ("el modelo mejora según se acumulan datos").

## Alcance

- **Reentrenamiento nocturno**: un job programado (EventBridge Scheduler ->
  Lambda, o un agente cloud programado con `/schedule`, o un `cron` en la
  EC2 del demonio) que 1x/día: regenera el panel (`ML_01`), reentrena los
  modelos (`ML_03`/`ML_05`), evalúa (`ML_02`), loguea el run en MLflow
  (`ML_04`) y promueve a `Production` si supera al modelo vigente.
- **Backtest incremental** (`modelado/evaluation/backtest.py`): rolling
  origin — para cada día D desde el arranque de datos, entrena con [inicio,
  D-3d], evalúa en [D-3d, D], registra la métrica. Produce la curva
  "skill score vs fecha".

## Criterios de aceptación

- El job de reentrenamiento corre de verdad al menos una noche y deja un run
  nuevo en MLflow.
- `backtest.py` produce la curva de skill score a lo largo del tiempo (CSV +
  PNG) para al menos calidad del aire.
- `doc/` con el mecanismo elegido para la programación y por qué (coste 0).

## Restricciones

- `allow_infra_apply` solo si el mecanismo elegido es EventBridge/Lambda
  (crear ese recurso); si es `/schedule` o cron en EC2, no toca Terraform.
- No dejar nada corriendo en bucle en disco local (guardrail de
  `tasks/README.md`).
