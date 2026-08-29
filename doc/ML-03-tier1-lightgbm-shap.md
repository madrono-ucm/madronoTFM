# ML-03 — Tier 1: forecasters LightGBM multi-horizonte + SHAP

## Qué se creó

- `modelado/models/gbt.py` — `LGBMRegressor` por `(target, horizonte)` con
  regularización fuerte (`num_leaves=31`, `min_child_samples=50`, subsample
  0.8, `reg_lambda=1`) y `early_stopping(50)` sobre val — apropiado para la
  ventana corta del proyecto. `columnas_features()` incluye `value` (lectura
  actual, `known_at = t`) + lags + rolling + calendario, excluye
  `entity_id`/`ts`/`target_h*`. `entrenar_clasificador_episodio()`:
  `LGBMClassifier` sobre `target_h{h} >= umbral`.
- `modelado/models/shap_explain.py` — `TreeExplainer`, `mean(|SHAP|)` por
  feature; figura de barras (matplotlib, opcional).
- `modelado/training/train_gbt.py` — entry point: panel → split (`ML_02`) →
  LightGBM por horizonte → compara con la **mejor** línea base → SHAP →
  artefactos en `modelado/evaluation/artifacts/`.

`lightgbm 4.7.0` / `shap 0.52.0` / `matplotlib 3.11.1` (wheels binarios,
Python 3.14). 19 tests de `modelado/` en verde (+3 de `test_ml03.py`).

## Resultados reales — LightGBM vs líneas base (test = últimos 3 días)

### `calidad_aire` (µg/m³, scope `all`, 123 entidades)

| h | modelo | n | MAE | RMSE | skill vs mejor baseline |
|---|---|---|---|---|---|
| 1 | **lightgbm** | 7611 | **2.46** | 4.96 | **+0.29** |
| 1 | persistencia | 7611 | 2.74 | 5.90 | 0.00 |
| 3 | **lightgbm** | 7089 | **3.88** | 7.40 | **+0.58** |
| 3 | persistencia | 7089 | 5.31 | 11.43 | 0.00 |
| 6 | **lightgbm** | 6358 | **4.57** | 8.31 | **+0.68** |
| 6 | seasonal_naive | 6358 | 7.24 | 14.58 | 0.00 |

### `trafico` (`avg_service_level`, scope `grafo-lugares`, 1813 puntos)

| h | modelo | n | MAE | RMSE | skill vs mejor baseline |
|---|---|---|---|---|---|
| 1 | **lightgbm** | 124151 | **0.083** | 0.182 | **+0.38** |
| 1 | climatología | 124151 | 0.108 | 0.230 | 0.00 |
| 3 | **lightgbm** | 120460 | **0.090** | 0.196 | **+0.63** |
| 6 | **lightgbm** | 115046 | **0.091** | 0.199 | **+0.78** |
| 6 | climatología | 115046 | 0.223 | 0.425 | 0.00 |

**En los dos targets LightGBM bate a la mejor línea base en todos los
horizontes, y la ventaja crece con el horizonte**: la línea base se degrada
(la persistencia pierde el 50 % de skill de h1 a h6) mientras el modelo se
mantiene plano (MAE de tráfico ~0.09 en h1/h3/h6).

## Explicabilidad — SHAP (h6)

| | `calidad_aire` | `trafico` |
|---|---|---|
| 1º | `value_roll24h_mean` (media móvil 24 h) — domina | `value_roll24h_mean` — domina |
| 2º | `value` (lectura actual) | `hora` / `hora_sin` (patrón diario) |
| 3º | `value_roll3h_mean`, `hora_cos`, lags | `value_roll24h_std`, `value` |

Coherente e interpretable: a 6 h vista el **nivel medio del último día** es
el predictor clave en ambos, más la **hora del día** (fuerte en tráfico por
la periodicidad hora punta / valle). Figuras en
`modelado/evaluation/artifacts/shap_<target>_h*.png`.

## Pendiente

- Clasificador de "episodio": necesita umbrales por contaminante
  (OMS: NO2 ~200 µg/m³ 1 h, PM2.5 ~25 µg/m³ 24 h) — el `entity_id`
  `station__pollutant` mezcla escalas, así que el umbral único no aplica.
  Se hace en `ML_08` con umbrales por contaminante / percentil de tráfico.
- Enriquecer el panel con meteo y previsión AEMET (`ML_01` lo dejó de
  esqueleto) — debería subir más el skill.
- MLflow (`ML_04`): `train_gbt.py` deja los artefactos en disco; falta
  loguear runs.
