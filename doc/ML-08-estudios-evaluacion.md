# ML-08 — Cuadernos de evaluación §7 (baseline vs GBT vs GNN + explicabilidad)

## Qué se creó

- **`modelado/evaluation/estudios/estudio_comparacion.py`** — funciones
  puras (sin credenciales, sin entrenar): `tabla_comparacion` consolida las
  salidas de `train_gbt` y `train_stgnn` en una fila por
  `(target, familia, horizonte)` con MAE/RMSE/skill; `resumen_explicabilidad`
  junta SHAP top-k (Tier 1) + aristas top-k (Tier 2); `figura_skill` dibuja
  las barras de skill por horizonte y modelo.
- **`modelado/evaluation/estudios/run_all.py`** — orquesta contra los
  paneles reales: re-entrena Tier 1 (`entrenar_todo`) y Tier 2
  (`train_stgnn.entrenar`), consolida y escribe a
  `modelado/evaluation/artifacts/estudios/` (`comparacion_<t>.csv`,
  `comparacion_todos.csv`, `explicabilidad_<t>.json`, `skill_<t>.png`).
  `--mlflow` loguea un run por estudio con `tags.study=comparacion` /
  `explicabilidad`.
- **`modelado/tests/test_ml08.py`** — 4 tests (familias/orden de la tabla,
  solo-GBT, resumen de explicabilidad, la figura no rompe).

`python -m pytest modelado/ -q` → **39 passed**.

## Decisión 8 — ablaciones §7.3 **descartadas para esta entrega**

`NEXT_STEPS.md` §5.7 (resuelta 29/8): las ablaciones 3 (fusión multi-señal
vs fuente única) y 4 ("solo sustrato europeo común") **no se hacen** por
tiempo (~2.5 semanas a la entrega). Está documentado como decisión
explícita en `VIC_05`, no omitido. `run_all.py` solo produce los estudios
1 y 2, que son los que la memoria §7.1–§7.3 necesita.

## Estudio 1 — comparación (test = últimos 3 días, split de `ML_02`)

### `calidad_aire` (µg/m³)

| h | familia | n | MAE | RMSE | skill vs referencia |
|---|---|---|---|---|---|
| 1 | baseline | 7611 | 2.74 | 5.90 | 0.00 |
| 1 | **lightgbm** | 7611 | **2.46** | 4.96 | **+0.29** |
| 1 | stgnn | 3359 | 4.93 | 7.37 | −0.51 |
| 3 | baseline | 7089 | 5.31 | 11.43 | 0.00 |
| 3 | **lightgbm** | 7089 | **3.88** | 7.40 | **+0.58** |
| 3 | stgnn | 3255 | 5.14 | 8.63 | +0.48 |
| 6 | baseline | 6358 | 7.24 | 14.58 | 0.00 |
| 6 | **lightgbm** | 6358 | **4.57** | 8.31 | **+0.68** |
| 6 | stgnn | 3088 | 6.35 | 11.24 | +0.55 |

### `trafico` (`avg_service_level`)

| h | familia | n | MAE | RMSE | skill vs referencia |
|---|---|---|---|---|---|
| 1 | baseline | 321 624 | 0.096 | 0.220 | 0.00 |
| 1 | **lightgbm** | 321 624 | **0.075** | 0.175 | **+0.37** |
| 1 | stgnn* | 124 653 | 0.097 | 0.184 | +0.39 |
| 3 | **lightgbm** | 311 579 | **0.081** | 0.188 | **+0.61** |
| 3 | stgnn* | 121 070 | 0.100 | 0.194 | +0.64 |
| 6 | **lightgbm** | 297 124 | **0.081** | 0.189 | **+0.76** |
| 6 | stgnn* | 115 726 | 0.101 | 0.196 | +0.79 |

\* STGNN de tráfico: `scope=grafo-lugares` (1798 nodos) y referencia =
persistencia; el resto de filas usan el panel completo y la mejor línea
base de `ML_02`. No re-entrenado en cada corrida (~40 min CPU); número de
`doc/ML-05`. `run_all.py --con-gnn-trafico` lo regenera.

**Lectura.** LightGBM es el mejor en MAE puntual en los dos targets y todos
los horizontes. El STGNN pierde con la persistencia a 1 h en calidad del
aire (esperado: a 1 h la persistencia es dificilísima de batir) pero aporta
a 3–6 h; en tráfico bate a la persistencia en todos los horizontes. El
margen de ambos modelos sobre la línea base **crece con el horizonte** (la
línea base se degrada, el modelo se mantiene plano). El valor del STGNN es
la fusión sobre el grafo y la explicabilidad por aristas, no ganar en MAE.

## Estudio 2 — explicabilidad

### SHAP (Tier 1, `mean|SHAP|`)

| target | h1 | h3 | h6 |
|---|---|---|---|
| `calidad_aire` | `value` ≫ `value_roll24h_mean` | `value_roll24h_mean` > `value` | `value_roll24h_mean` domina |
| `trafico` | `value_roll24h_mean` domina | `value_roll24h_mean` + `hora`/`hora_sin` | `value_roll24h_mean` + `hora` |

A 1 h la lectura actual manda; según crece el horizonte pasa a mandar la
**media móvil de 24 h** (nivel del último día) y, en tráfico, la **hora del
día** (periodicidad punta/valle). JSON completo por horizonte en
`explicabilidad_<target>.json`.

### Importancia de aristas (Tier 2, `d(loss)/d(edge_weight)`)

- `calidad_aire`: la predicción de **O₃ en `28079035`** depende sobre todo
  de su vecina **O₃ `28079049`** (~10× la siguiente), luego de los canales
  NOx/NO₂/NO de esa misma estación (química troposférica O₃↔NOx).
- `trafico`: el punto **`5412`** está dominado por el vecino **`5768`**
  (~46 vs ~1e-5 el resto) — un tramo cuyo estado fija el contiguo.

## Criterios de aceptación

- [x] Estudios 1 y 2 completos con datos reales (`comparacion_*.csv`,
  `explicabilidad_*.json`, `skill_*.png`).
- [x] Ablaciones 3 y 4 recortadas (decisión 8) — anotado aquí y en
  `VIC_05`.
- [x] Reproducible: `python -m modelado.evaluation.estudios.run_all`
  regenera todo.
- [x] Cada estudio loguea un run MLflow con `tags.study=`.

## Pendiente / lo retoman otros tickets

- `ML_09` — la tool del asistente consume estos modelos vía ONNX (`ML_07`).
- `ML_10` — backtest incremental según crece el histórico; puede reusar
  `run_all.py` como base del informe periódico.
