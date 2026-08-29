---
kind: ml
title: "Splits temporales + líneas base + módulo de métricas (arnés de evaluación)"
owner: Filippos (interactive)
status: done
depends_on: [ML_01]
created_at: "2026-08-28"
---

> **Estado 29/8: ✅ HECHO.** `modelado/datasets/splits.py`, `models/baselines.py` (persistencia / seasonal_naive / climatología horaria), `evaluation/metrics.py` (MAE/RMSE/MAPE/skill_score/PR-AUC sin sklearn), `evaluation/run_baselines.py`. 16 tests. Suelo medido contra los paneles reales -- ver `doc/ML-02`.

## Objetivo

El arnés de evaluación que compartirán Tier 1 (`ML_03`) y Tier 2 (`ML_05`):
cómo se parten los datos, contra qué se compara, y con qué métricas.

## Alcance

### `modelado/datasets/`

- `splits.py`: split **temporal** (nunca aleatorio) — train = todo menos los
  últimos N días; val = los 2 días previos al test; test = últimos 3 días.
  Parametrizable. Función pura sobre el panel de `ML_01`.
- `windowing.py`: para modelos de secuencia, ventana deslizante de L horas
  de historia → horizonte h (1/3/6). Para el GNN, construir el "snapshot"
  del grafo por hora (features de nodo alineadas a `ts`).

### `modelado/models/baselines.py`

- **Persistencia**: `ŷ(t+h) = y(t)`.
- **Climatología horaria**: media del target por `(estación, hora-del-día,
  día-laborable?)` sobre el train.
- **Seasonal-naive**: `ŷ(t+h) = y(t+h-24)`.
Puras, sin dependencias pesadas.

### `modelado/evaluation/metrics.py`

- Regresión: MAE, RMSE, MAPE (con guardas), **skill score vs persistencia**
  (`1 - MSE_modelo/MSE_persistencia`), desglosado por **horizonte** y por
  **tipo de nodo** (estación de tráfico / de calidad del aire / :Lugar).
- Clasificación de "episodio" (target cruza un umbral — OMS para NO2/PM2.5,
  percentil alto de `avg_load_ratio` para tráfico): precisión, recall,
  F1, **PR-AUC**.
- `evaluar(y_true, y_pred, ...) -> dict` con todo lo anterior, listo para
  loguear en MLflow (`ML_04`).

## Criterios de aceptación

- Ejecutar las 3 líneas base contra el panel real de `ML_01` (calidad del
  aire y tráfico) y anotar sus métricas en el `doc/` — son el suelo que
  Tier 1/2 tienen que superar.
- Tests de `splits`/`baselines`/`metrics` en verde con fixtures.
- Ningún split usa información del futuro (test comprobado en un test).

## Restricciones

- Determinista: `random_state` fijo donde aplique.
- Las métricas viven en un módulo puro (sin MLflow ni sklearn pesado si se
  puede evitar) para poder testearlas sin infra.
