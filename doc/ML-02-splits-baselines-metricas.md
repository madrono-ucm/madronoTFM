# ML-02 — Splits temporales, líneas base, módulo de métricas

El arnés de evaluación que compartirán Tier 1 (`ML_03`) y Tier 2 (`ML_05`).

## Qué se creó

- `modelado/datasets/splits.py` — `temporal_split(panel, test_days=3,
  val_days=2)` → `(train, val, test)` por `ts` global, sin solape. Test =
  últimos 3 días (la ventana del proyecto es corta, `NEXT_STEPS.md` §4).
  `es_split_sin_fuga()` verifica `train < val < test`.
- `modelado/models/baselines.py` — sobre el panel de `ML_01`, devuelven
  `entity_id/ts/y_true/y_pred`:
  - `persistence`: `ŷ(t+h) = y(t)`.
  - `seasonal_naive`: `ŷ(t+h) = y(t+h-24)` (misma hora del día anterior).
  - `hourly_climatology`: media histórica de `value` por `(entity, hora,
    finde)` de `t+h`, estimada en train; fallback a media de la entidad y
    global.
- `modelado/evaluation/metrics.py` — puro numpy: `mae`, `rmse`, `mape` (con
  guarda), `skill_score` (`1 - MSE_modelo/MSE_ref`), `_pr_auc` sin sklearn.
  `evaluar_regresion()` y `evaluar_episodio()` devuelven un `dict` plano
  para `mlflow.log_metrics`.
- `modelado/evaluation/run_baselines.py` — entry point: panel Parquet →
  split → 3 baselines × horizontes → tabla de métricas (skill vs
  persistencia, sobre el índice común).

16 tests en verde (`test_ml02.py` + los 8 de `panel.py`).

## Resultados reales — el suelo que Tier 1/2 tienen que superar (28-29/8)

### `calidad_aire` (µg/m³, `all`, 123 entidades, test = últimos 3 días)

| h | baseline | n | MAE | RMSE | skill vs persistencia |
|---|---|---|---|---|---|
| 1 | persistencia | 7611 | **2.74** | 5.90 | 0.00 |
| 1 | seasonal_naive | 4869 | 6.59 | 12.77 | −7.82 |
| 1 | climatología | 7611 | 8.46 | 14.13 | −4.73 |
| 3 | persistencia | 7089 | 5.31 | 11.43 | 0.00 |
| 6 | persistencia | 6358 | 7.24 | 14.58 | 0.00 |
| 6 | seasonal_naive | 4832 | 6.56 | 12.71 | **+0.16** |

Persistencia domina a corto plazo (el aire está muy autocorrelacionado hora
a hora); a 6 h, `seasonal_naive` ya la supera ligeramente.

### `trafico` (`avg_service_level`, scope `grafo-lugares`, 1813 puntos)

| h | baseline | n | MAE | RMSE | skill vs persistencia |
|---|---|---|---|---|---|
| 1 | persistencia | 124151 | 0.108 | 0.230 | 0.00 |
| 1 | climatología | 124151 | **0.099** | 0.217 | **+0.11** |
| 3 | climatología | 120460 | 0.097 | 0.215 | **+0.55** |
| 6 | climatología | 115046 | 0.097 | 0.215 | **+0.74** |

El tráfico tiene un patrón diario fuerte → climatología y `seasonal_naive`
baten con holgura a la persistencia a medio plazo.

## Nota

Cada baseline puntúa el subconjunto de filas que puede predecir
(`seasonal_naive` pierde las primeras 21 h de cada serie). El skill score se
calcula sobre el **índice común** con la persistencia. `ML_08` alineará los
tres modelos + Tier 1/2 sobre el mismo conjunto para la tabla final de §7.
