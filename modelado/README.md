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

## Prerrequisito de sistema: `libgomp1`

`lightgbm` (Tier 1, `ML_03`) enlaza en tiempo de importación contra
`libgomp.so.1`, el runtime de OpenMP. En una EC2/imagen que no lo traiga
preinstalado, `import lightgbm` (y por tanto cualquier test que lo importe,
p. ej. `modelado/tests/test_ml03.py`) falla con:

```
OSError: libgomp.so.1: cannot open shared object file: No such file or directory
```

No es un bug de código ni una regresión: es una dependencia de sistema
ausente. Se instala con:

```bash
sudo apt-get install -y libgomp1
```

La CI (`.github/workflows/ci.yml`) ya instala este paquete antes de
`pip install -r modelado/requirements.txt` de forma defensiva (ver
`doc/103-modelado-ci-y-dependencia-sistema-libgomp.md`). Si trabajas en una
EC2 nueva de forma interactiva, instálalo a mano antes de correr
`pytest modelado/` para no perder tiempo diagnosticando este mismo error.

## `torch` es SOLO CPU (`FIL_23`)

`stgnn.py` (`ML_05`) usa `torch` **sin GPU**. `modelado/requirements.txt`
lleva `--extra-index-url https://download.pytorch.org/whl/cpu`, así que un
`pip install -r modelado/requirements.txt` normal ya trae el wheel
`torch==X.Y.Z+cpu` (~760 MB) en vez del build CUDA por defecto de PyPI
(~4.5 GB de `nvidia-*`/`triton` que no sirven sin GPU y que además fallan al
importar sin el toolkit CUDA del sistema).

Si tu `pip` es antiguo y aun así instala `nvidia-*`, hazlo en dos pasos:

```bash
pip install --index-url https://download.pytorch.org/whl/cpu 'torch>=2.2,<3'
pip install -r modelado/requirements.txt        # ya encuentra torch satisfecho
```

Comprobación: `python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
→ `...+cpu False`, y `site-packages/` sin carpetas `nvidia/`/`triton/`.

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
funciones puras de `features/panel.py` + `features/exogenas.py` (testables
sin credenciales) y lo escribe como Parquet. Targets soportados:
`calidad_aire` (`avg_value` por estación/contaminante), `trafico`
(`avg_service_level` por punto), `afluencia` (nivel numérico por `:Lugar`,
de la tabla Gold de `FIL_06`).

Enriquecedores (por defecto activos; `doc/ML-01` para el detalle):

- **Meteo observada** (`--sin-meteo` para desactivar): 5 columnas `meteo_*`
  de `meteorologia_por_estacion_magnitud_hora`, uniendo cada sensor a la
  estación meteo más cercana que reporta cada magnitud. `known_at = t`.
- **Previsión AEMET** (`--sin-prevision`): 6 columnas `prev_*` de la Silver
  `aemet_prevision` — la previsión del día tomada de la última elaboración
  de un día anterior ("la de ayer para hoy"). Feature exógena de futuro
  conocido, `known_at < t`.
- **Festivos**: `--festivos` (por defecto la muestra commiteada del
  calendario laboral de Madrid, año 2026 completo).
- **Vecinos de grafo** (`--con-vecinos`): necesita Neo4j.

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
