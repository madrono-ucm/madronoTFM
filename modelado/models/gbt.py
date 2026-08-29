"""Tier 1 (`ML_03`): forecasters LightGBM multi-horizonte + clasificador de
"episodio". Sobre el panel de `ML_01`, con el split temporal de `ML_02`.

Un modelo por `(target, horizonte)`. Con la ventana corta del proyecto
(~3-4 semanas) se usa regularización fuerte y `early_stopping` sobre val.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_NO_FEATURE = {"entity_id", "ts"}

# Defaults conservadores para pocas semanas de datos (ver `ML_03`).
PARAMS_REG = {
    "objective": "regression_l1",
    "n_estimators": 600,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}
PARAMS_CLF = {**PARAMS_REG, "objective": "binary"}


def columnas_features(panel: pd.DataFrame) -> "list[str]":
    """Todas las numéricas del panel salvo `entity_id`/`ts` y las `target_h*`.
    `value` (lectura actual, `known_at = t`) SÍ entra -- es el predictor más
    fuerte."""
    return [
        c
        for c in panel.columns
        if c not in _NO_FEATURE
        and not c.startswith("target_h")
        and pd.api.types.is_numeric_dtype(panel[c])
    ]


def _xy(df: pd.DataFrame, horizon: int, feature_cols: "list[str]"):
    col = f"target_h{horizon}"
    sub = df.dropna(subset=[col])
    return sub[feature_cols], sub[col], sub[["entity_id", "ts"]]


def entrenar(
    train: pd.DataFrame,
    val: pd.DataFrame,
    *,
    horizon: int,
    feature_cols: "list[str] | None" = None,
    params: "dict | None" = None,
):
    from lightgbm import LGBMRegressor, early_stopping, log_evaluation

    feature_cols = feature_cols or columnas_features(train)
    Xtr, ytr, _ = _xy(train, horizon, feature_cols)
    Xva, yva, _ = _xy(val, horizon, feature_cols)
    model = LGBMRegressor(**{**PARAMS_REG, **(params or {})})
    model.fit(
        Xtr, ytr,
        eval_set=[(Xva, yva)] if len(Xva) else None,
        callbacks=[early_stopping(50, verbose=False), log_evaluation(0)] if len(Xva) else None,
    )
    return model, feature_cols


def entrenar_clasificador_episodio(
    train: pd.DataFrame,
    val: pd.DataFrame,
    *,
    horizon: int,
    umbral: float,
    feature_cols: "list[str] | None" = None,
):
    from lightgbm import LGBMClassifier, early_stopping

    feature_cols = feature_cols or columnas_features(train)
    Xtr, ytr, _ = _xy(train, horizon, feature_cols)
    Xva, yva, _ = _xy(val, horizon, feature_cols)
    ytr_bin = (ytr >= umbral).astype("int8")
    yva_bin = (yva >= umbral).astype("int8")
    model = LGBMClassifier(**PARAMS_CLF)
    model.fit(
        Xtr, ytr_bin,
        eval_set=[(Xva, yva_bin)] if len(Xva) else None,
        callbacks=[early_stopping(50, verbose=False)] if len(Xva) else None,
    )
    return model, feature_cols


def predecir(model, panel: pd.DataFrame, *, horizon: int, feature_cols: "list[str]") -> pd.DataFrame:
    """`entity_id/ts/y_true/y_pred` para las filas del panel con `target_h{h}`
    no nulo -- listo para `evaluation/metrics.py`."""
    X, y, ids = _xy(panel, horizon, feature_cols)
    out = ids.copy()
    out["y_true"] = y.to_numpy()
    pred = model.predict(X)
    # LGBMClassifier -> probabilidad de episodio; LGBMRegressor -> valor
    if hasattr(model, "predict_proba"):
        pred = model.predict_proba(X)[:, 1]
    out["y_pred"] = np.asarray(pred)
    return out
