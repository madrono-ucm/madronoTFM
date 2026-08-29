---
kind: vikt
title: "Memoria §8 Anexo — reproducibilidad del pipeline de modelado"
owner: Pista Memoria — documentación (interactivo)
status: pending
depends_on: [VIKT_01]
created_at: "2026-08-29"
---

## Objetivo

Un anexo corto que permita **regenerar cada tabla y figura de §7** y
entender el layout de `modelado/`, para que la memoria sea reproducible
(criterio de TFM y de la propia §7.2 "arnés común de `modelado/`").

## Contenido (Anexo C — Reproducibilidad del modelado)

- **Layout**: `modelado/` (`features/` feature store, `datasets/` splits +
  snapshots de grafo, `models/` baselines/gbt/stgnn, `training/` entry
  points, `evaluation/` métricas/drift/backtest/estudios, `registry/`
  MLflow, `export/` ONNX) y `asistente/modelos/*.onnx` (copia vendida).
- **Entorno**: Python 3.14, dependencias con
  `pip install -r modelado/requirements.txt` (en 3.14, `--only-binary
  :all:`); LightGBM necesita `libgomp1` en Linux.
- **Un comando por artefacto**:
  - Panel (`ML_01`): `python -m modelado.features.build --target … --desde …
    --hasta … --out …` (necesita `AWS_PROFILE=madrono`).
  - Tier 1 + SHAP + MLflow (`ML_03`/`ML_04`):
    `python -m modelado.training.train_gbt --panel … --nombre … --mlflow tier1`.
  - Tier 2 STGNN (`ML_05`):
    `python -m modelado.training.train_stgnn --panel …_grafo.parquet --nombre … --mlflow tier2`.
  - Estudios §7 (`ML_08`): `python -m modelado.evaluation.estudios.run_all --mlflow estudios`.
  - Deriva (`ML_06`): `python -m modelado.evaluation.drift --panel … --target …`.
  - Backtest incremental (`ML_10`): `python -m modelado.evaluation.backtest --panel … --target …`.
  - Export ONNX + paridad (`ML_07`):
    `python -m modelado.export.to_onnx --modelo madrono-calidad_aire-h6 --panel … --nombre calidad_aire_h6`.
  - Reentrenamiento nocturno (`ML_10`): `python -m modelado.training.retrain_nightly`
    (+ la línea de `cron` de `infra/OPERACION.md`).
- **MLflow**: `mlflow ui --backend-store-uri sqlite:///modelado/mlflow.db`.
- **Nota**: los `.onnx` grandes y los `mlruns/` no se versionan (regenerables);
  sí los CSV/JSON de `modelado/evaluation/artifacts/` que respaldan §7.

## Fuente técnica

`modelado/README.md`, `modelado/requirements.txt`, `infra/OPERACION.md`,
todos los `doc/ML-*`, el informe de `VIKT_01`.

## Criterios de aceptación

- El anexo lista un comando por cada tabla/figura de §7 y por cada modelo
  registrado.
- Coherente con `modelado/README.md` (no lo contradice).
- `.docx` con estilos/numeración intactos; el anexo va bajo §8.

## Restricciones

- Coordinar el turno del `.docx`. `git pull` antes.
