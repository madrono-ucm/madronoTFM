# `modelado/` — pista de modelado del TFM

El elemento central del TFM (memoria §3.2: *"modelar la ciudad como un grafo
y entrenar modelos predictivos de afluencia, congestión y calidad del
aire"*). Análogo de `ingesta/`/`procesamiento/`/`grafo/`/`asistente/` para
la fase de ML. Tickets en `tasks/ML_*.md` (`tasks/ML_00_README.md` para el
índice y el diseño completo).

## Realidad de datos (importante)

La ingesta en continuo arrancó el **2026-08-14** (ver `NEXT_STEPS.md` §4):
a la entrega hay **~3-4 semanas** de histórico horario. Los modelos son una
**demostración de metodología** con holdout temporal (últimos 3 días), no
una estimación de rendimiento en régimen estacional. La ventana corta es una
limitación explícita de la memoria §7.4. Los estudios de ablación de §7.3
(fusión multi-señal vs fuente única; "solo sustrato europeo común") sí son
viables con esta ventana.

## Estructura

| Dir | Contenido | Ticket |
|---|---|---|
| `features/` | Feature store: Athena → panel horario por estación, **sin fuga temporal** | `ML_01` |
| `datasets/` | Splits temporales, windowing de secuencia, snapshots de grafo | `ML_02`, `ML_05` |
| `models/` | `baselines.py`, `gbt.py` (LightGBM), `stgnn.py` (GNN) | `ML_02`/`03`/`05` |
| `training/` | Entry points de entrenamiento (config-driven, logean a MLflow) | `ML_03`+ |
| `evaluation/` | `metrics.py`, `drift.py` (Evidently), `backtest.py`, `estudios/` (§7) | `ML_02`/`06`/`08`/`10` |
| `registry/` | MLflow tracking + model registry | `ML_04` |
| `export/` | ONNX export + `CONTRATO.md` de entrada/salida + test de paridad | `ML_07` |

## Anti-fuga temporal (regla de oro)

Cada feature lleva su `known_at` (instante en que su valor es conocido). En
el panel de la hora `t` solo entran features con `known_at <= t`:

- **Lags / rolling** del target → `shift(+k)` (pasado).
- **Target a horizonte `h`** (la etiqueta) → `shift(-h)` (futuro).
- **Calendario** (hora, día, festivo) → conocido siempre.
- **Meteo observada** en `t` → conocida en `t`.
- **Previsión AEMET** → conocida antes (feature exógena de futuro conocido).
- **Vecinos de grafo** → mismos criterios aplicados a la serie del vecino.

## Feature store

`features/build.py` es el entry point:

```bash
python -m modelado.features.build --target calidad_aire --desde 2026-08-15 --hasta 2026-08-27 --out modelado/_data/panel_calidad_aire.parquet
```

Lee Gold vía Athena (`features/athena.py`), construye el panel con las
funciones puras de `features/panel.py` (testables sin credenciales) y lo
escribe como Parquet. Targets soportados: `calidad_aire`
(`avg_value` por estación/contaminante), `trafico`
(`avg_service_level` por punto), `afluencia`
(nivel numérico por `:Lugar`, de la tabla Gold de `FIL_06`).

Credenciales: `AWS_PROFILE=madrono` (`eu-west-1`), Neo4j en SSM — ver
`infra/OPERACION.md`.

## Entrenamiento

```bash
# Tier 1 — LightGBM multi-horizonte + SHAP (ML_03), loguea en MLflow (ML_04)
python -m modelado.training.train_gbt --panel modelado/_data/panel_calidad_aire.parquet --nombre calidad_aire --mlflow tier1

# Tier 2 — GNN espacio-temporal + importancia de aristas (ML_05)
python -m modelado.training.train_stgnn --panel modelado/_data/panel_calidad_aire_grafo.parquet --nombre calidad_aire --mlflow tier2
```

`train_stgnn` deriva el grafo de las coordenadas del panel (k-NN gaussiano)
salvo que se le pase `--aristas-json` con las `PROXIMO_A` reales exportadas
de Neo4j. MLflow: backend SQLite local (`modelado/mlflow.db`), `mlflow ui
--backend-store-uri sqlite:///modelado/mlflow.db` para la interfaz.
