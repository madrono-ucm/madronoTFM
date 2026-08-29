# ML-04 — MLflow: tracking de experimentos + model registry

## Qué se creó

- `modelado/registry/mlflow_setup.py`
  - `configurar(experiment, *, tracking_uri=None)` — fija el
    `MLFLOW_TRACKING_URI` y el experimento; devuelve el URI en uso.
    Prioridad: argumento → `MLFLOW_TRACKING_URI` del entorno → por defecto
    `sqlite:///modelado/mlflow.db`. Para backend SQLite crea el experimento
    con `artifact_location = file:modelado/mlartifacts/` (MLflow no lo
    infiere solo con backend de base de datos).
  - `log_run(*, run_name, params, metrics, tags, model, model_flavor,
    artifacts, registered_name)` — un `mlflow.start_run` con params +
    metrics + tags + artefactos + (opcional) el modelo. Filtra métricas no
    finitas (`nan`/`inf` rompen `log_metrics`) y las deja anotadas en el
    tag `metricas_no_finitas`. Si `registered_name`, hace
    `mlflow.register_model` y pone el alias `@champion` en la versión
    recién creada.
  - `marcar_champion(registered_name, version)` — mueve el alias
    `@champion`. MLflow 3.x sustituye los stages `Production`/`Staging` por
    aliases; `ML_10` (reentrenamiento) lo usará para promover solo si la
    nueva versión bate a la vigente.
- `modelado/training/train_gbt.py` — `entrenar_todo(..., mlflow_experiment=)`
  y flag `--mlflow <experimento>`. Cada `(target, horizonte)` loguea un run
  (hiperparámetros de `gbt.PARAMS_REG`, tamaños de train/test, métricas
  `gbt_*` y `baseline_*` de `ML_02`, tags `tier`/`baseline_ganadora`, la
  figura SHAP como artefacto y el modelo LightGBM) y registra
  `madrono-<target>-h<h>`.

`mlflow 3.15.2` (wheel binario, Python 3.14). `mlflow>=2.16,<4` en
`modelado/requirements.txt`. 20 tests de `modelado/` en verde (+1 de
`test_ml04.py`: params/metrics registrados, no finitos filtrados y
anotados).

## `MLFLOW_TRACKING_URI` elegido — y por qué

**`sqlite:///modelado/mlflow.db`** con artefactos en
`modelado/mlartifacts/`. Coste 0, sin infraestructura.

MLflow ≥3 puso el *backend de fichero* (`./mlruns`) en modo mantenimiento y
recomienda una base de datos; el registry solo funciona con backend de base
de datos. SQLite lo cumple sin levantar un servidor. `mlflow ui
--backend-store-uri sqlite:///modelado/mlflow.db` abre la interfaz sobre el
mismo fichero.

Migración futura sin tocar código: `export MLFLOW_TRACKING_URI=...` a un
servidor MLflow en la EC2 del demonio (Postgres + artefactos en
`s3://madrono-tfm-dev-gold-.../mlflow/`). `modelado/mlflow.db`,
`modelado/mlartifacts/` y `modelado/mlruns/` están en `.gitignore`.

## Verificación real

`python -m modelado.training.train_gbt --panel …/panel_trafico_grafo.parquet
--nombre trafico --mlflow tier1` + ídem `calidad_aire`:

- **6 runs** en el experimento `tier1` (`mlflow.search_runs` los lista) con
  params + metrics + modelo + figura SHAP.
- **6 modelos registrados**, cada uno con versión 1 y alias `@champion`:

  | modelo registrado | versión | alias |
  |---|---|---|
  | `madrono-calidad_aire-h1` | 1 | `@champion` |
  | `madrono-calidad_aire-h3` | 1 | `@champion` |
  | `madrono-calidad_aire-h6` | 1 | `@champion` |
  | `madrono-trafico-h1` | 1 | `@champion` |
  | `madrono-trafico-h3` | 1 | `@champion` |
  | `madrono-trafico-h6` | 1 | `@champion` |

- `mlflow.<flavor>.load_model("models:/madrono-trafico-h6@champion")`
  recupera el modelo por alias — el patrón que consumirá `ML_07` (export
  ONNX) y `ML_09` (tool del asistente).

## Criterios de aceptación

- [x] `train_gbt.py` produce runs listables (`mlflow.search_runs`) con
  params + metrics + modelo + artefactos.
- [x] ≥1 modelo por target en el registry con versión y promoción
  (`@champion`).
- [x] `doc/` con el `MLFLOW_TRACKING_URI` elegido y el porqué (coste 0).
- [x] `mlflow` en `modelado/requirements.txt`.

## Pendiente / lo retoman otros tickets

- `ML_10` — reentrenamiento nocturno: `marcar_champion` solo si la nueva
  versión bate a la vigente en el backtest incremental.
- `ML_07` — carga por alias `models:/<nombre>@champion` → ONNX.
- Servidor MLflow en la EC2 (opcional): documentar en `infra/OPERACION.md`
  si se decide levantarlo.
