---
kind: ml
title: "MLflow — tracking de experimentos + model registry"
owner: Filippos (interactive)
status: done
depends_on: [ML_02]
created_at: "2026-08-28"
---

> **Estado 29/8: ✅ HECHO.** `modelado/registry/mlflow_setup.py`
> (`configurar` / `log_run` / `marcar_champion`) + `train_gbt.py --mlflow`.
> Backend por defecto **`sqlite:///modelado/mlflow.db`** (MLflow ≥3 dejó el
> backend de fichero en mantenimiento; el registry exige base de datos).
> Artefactos en `modelado/mlartifacts/`. Migrable a un servidor MLflow vía
> `MLFLOW_TRACKING_URI` sin tocar código. Verificado end-to-end: 6 runs en
> el experimento `tier1`, 6 modelos registrados
> (`madrono-{calidad_aire,trafico}-h{1,3,6}` v1) con alias `@champion`.
> `mlflow>=2.16,<4` en requirements. 20 tests en verde (+1 `test_ml04.py`).
> Writeup en `doc/ML-04-mlflow-tracking-registry.md`.

## Objetivo

El gobierno del ciclo de vida del modelo que pide la memoria (§5.4/§5.5:
MLflow). Coste 0: MLflow con backend local de fichero + artefactos en S3, o
un servidor MLflow mínimo en la EC2 del demonio si se decide.

## Alcance

- `modelado/registry/mlflow_setup.py`: fija `MLFLOW_TRACKING_URI` (por
  defecto `file:./mlruns`, opción S3 `s3://madrono-tfm-dev-gold-.../mlflow/`)
  y el `experiment` por target.
- `log_run(params, metrics, model, artifacts, tags)`: helper que envuelve
  `mlflow.start_run` — params (features usadas, ventana, horizonte,
  hiperparámetros), metrics (el `dict` de `ML_02`), el modelo (`mlflow.
  lightgbm` / `mlflow.pytorch`), y artefactos (figuras SHAP, tabla
  comparativa).
- **Model registry**: registrar el mejor modelo por target como
  `madrono-<target>-<horizonte>` con stage (`Staging`/`Production`).
- Reconvertir `modelado/training/train_gbt.py` (`ML_03`) para que loguee vía
  este helper.

## Criterios de aceptación

- `train_gbt.py` produce runs visibles en `mlflow ui` (o listables con
  `mlflow.search_runs`) con params + metrics + modelo + artefactos.
- Al menos un modelo por target registrado en el registry con una versión y
  un stage.
- `doc/` con el `MLFLOW_TRACKING_URI` elegido y por qué (coste 0).

## Restricciones

- `mlflow` a `modelado/requirements.txt`.
- Si se usa un servidor en la EC2: documentarlo en `infra/OPERACION.md`, sin
  exponerlo públicamente.
