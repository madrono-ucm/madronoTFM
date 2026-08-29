"""MLflow: tracking de experimentos + model registry (ML_04). Coste 0 —
backend local **SQLite** (`modelado/mlflow.db`) por defecto, con los
artefactos en `modelado/mlartifacts/`. MLflow >=3 puso el backend de
fichero (`./mlruns`) en modo mantenimiento y exige una base de datos;
SQLite lo cumple sin infraestructura. `MLFLOW_TRACKING_URI` lo cambia
(p. ej. un servidor MLflow en la EC2 del demonio con backend Postgres +
artefactos en S3).
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_URI = f"sqlite:///{(_ROOT / 'mlflow.db').as_posix()}"
_DEFAULT_ARTIFACTS = (_ROOT / "mlartifacts").as_posix()


def configurar(experiment: str, *, tracking_uri: str | None = None) -> str:
    """Fija el tracking URI y el experimento. Devuelve el URI en uso."""
    import mlflow

    uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI") or _DEFAULT_URI
    mlflow.set_tracking_uri(uri)
    if uri.startswith("sqlite:"):
        Path(_DEFAULT_ARTIFACTS).mkdir(parents=True, exist_ok=True)
        try:
            mlflow.set_experiment(experiment)
        except Exception:  # noqa: BLE001 -- experimento nuevo: crear con location de artefactos
            mlflow.create_experiment(experiment, artifact_location=f"file:{_DEFAULT_ARTIFACTS}")
            mlflow.set_experiment(experiment)
    else:
        mlflow.set_experiment(experiment)
    return uri


def log_run(
    *,
    run_name: str,
    params: dict,
    metrics: dict,
    tags: dict | None = None,
    model=None,
    model_flavor: str = "lightgbm",
    artifacts: "list[str] | None" = None,
    registered_name: str | None = None,
) -> str:
    """Un run de MLflow con params + metrics + tags + (opcional) el modelo y
    ficheros de artefacto. Si `registered_name`, registra el modelo en el
    Model Registry. Devuelve el `run_id`.
    """
    import mlflow

    # métricas no finitas rompen `log_metrics`; se filtran y se anotan.
    import math

    limpio = {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float)) and math.isfinite(v)}
    descartadas = sorted(set(metrics) - set(limpio))

    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params(params)
        mlflow.log_metrics(limpio)
        mlflow.set_tags({**(tags or {}), **({"metricas_no_finitas": ",".join(descartadas)} if descartadas else {})})
        for a in artifacts or []:
            if Path(a).exists():
                mlflow.log_artifact(a)
        if model is not None:
            flavor = getattr(mlflow, model_flavor)
            info = flavor.log_model(model, name="model")
            if registered_name:
                mv = mlflow.register_model(info.model_uri, registered_name)
                # `@champion` a la versión recién registrada. `ML_10`
                # (reentrenamiento) solo lo mueve si la nueva supera a la
                # vigente; aquí, primera versión, siempre.
                try:
                    mlflow.MlflowClient().set_registered_model_alias(
                        registered_name, "champion", mv.version
                    )
                except Exception:  # noqa: BLE001
                    pass
        return run.info.run_id


def marcar_champion(registered_name: str, version: str) -> None:
    """Alias `@champion` a una versión del modelo registrado (MLflow 3.x usa
    aliases en vez de stages `Production`/`Staging`)."""
    import mlflow

    mlflow.MlflowClient().set_registered_model_alias(registered_name, "champion", version)
