---
kind: ml
title: "Tier 1 — forecasters LightGBM multi-horizonte + clasificadores de episodio + SHAP"
owner: Filippos (interactive)
status: pending
depends_on: [ML_02]
created_at: "2026-08-28"
---

## Objetivo

Los primeros modelos reales, fuertes y explicables. Referencia contra la que
se mide el GNN (`ML_05`).

## Alcance

### `modelado/models/gbt.py`

- `LightGBM` (o `xgboost` si LightGBM da problemas en el entorno), un modelo
  por `(target, horizonte)` — targets: **calidad del aire** (NO2, PM2.5, O3
  por estación), **congestión** (`avg_service_level`/`avg_load_ratio` por
  punto), **afluencia derivada** (nivel numérico por `:Lugar`, de la tabla
  Gold de `FIL_06`); horizontes 1/3/6 h.
- Entrada: el panel de `ML_01`. Split temporal de `ML_02`.
- `entrenar(panel, target, horizonte) -> modelo` + `predecir`.

### Clasificador de episodio

- Un `LGBMClassifier` por target sobre "el target cruza el umbral en `t+h`"
  (umbrales OMS / percentil, definidos en `ML_02`).

### `modelado/models/shap_explain.py`

- SHAP `TreeExplainer` sobre el modelo entrenado: importancia global (top-N
  features) + un par de explicaciones locales de ejemplo. Guardar como
  figura/JSON en `modelado/evaluation/artifacts/`.

### `modelado/training/train_gbt.py`

- Entry point: entrena los modelos, evalúa con `ML_02` metrics, imprime la
  tabla comparativa **baseline vs LightGBM** por horizonte/tipo de nodo.
- Loguea en MLflow si `ML_04` ya está (si no, deja los artefactos en disco y
  se re-loguea después).

## Criterios de aceptación

- Tabla real (en el `doc/`) baseline vs LightGBM por horizonte para al menos
  calidad del aire y congestión: MAE, RMSE, skill score.
- SHAP: figura de importancia global commiteada + comentario de qué features
  pesan (se espera: lags recientes, hora, meteo).
- Tests: `gbt.py` entrena y predice sobre una fixture pequeña sintética sin
  tocar Athena; formas y columnas correctas.

## Restricciones

- Con ~2-4 semanas de datos: regularización fuerte, `num_leaves` bajo,
  `early_stopping` sobre val. Documentar que la ventana es corta (§7.4).
- `random_state` fijo; entrenamientos reproducibles.
- `lightgbm`/`shap` a `modelado/requirements.txt`.
