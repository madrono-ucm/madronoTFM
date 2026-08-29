"""Líneas base (ML_02): el suelo que Tier 1 (`ML_03`) y Tier 2 (`ML_05`)
tienen que superar. Puras (numpy/pandas), sobre el panel de `ML_01`.

Todas devuelven un `DataFrame` con `entity_id`, `ts`, `y_true`
(`target_h{h}` del panel) e `y_pred`, listo para `evaluation/metrics.py`.
"""

from __future__ import annotations

import pandas as pd


def _base(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    col = f"target_h{horizon}"
    return panel[["entity_id", "ts", "value", col]].rename(columns={col: "y_true"}).copy()


def persistence(panel: pd.DataFrame, *, horizon: int) -> pd.DataFrame:
    """`ŷ(t+h) = y(t)`."""
    out = _base(panel, horizon)
    out["y_pred"] = out["value"]
    return out.drop(columns="value").dropna(subset=["y_true", "y_pred"])


def seasonal_naive(panel: pd.DataFrame, *, horizon: int) -> pd.DataFrame:
    """`ŷ(t+h) = y(t+h-24)` -- el valor a la misma hora del día anterior."""
    out = _base(panel, horizon)
    serie = (
        panel.drop_duplicates(["entity_id", "ts"]).set_index(["entity_id", "ts"])["value"]
    )
    horas_atras = 24 - horizon  # h in {1,3,6} -> 23/21/18
    claves = list(zip(out["entity_id"], pd.to_datetime(out["ts"]) - pd.Timedelta(hours=horas_atras)))
    out["y_pred"] = serie.reindex(claves).to_numpy()
    return out.drop(columns="value").dropna(subset=["y_true", "y_pred"])


def hourly_climatology(
    train: pd.DataFrame, panel: pd.DataFrame, *, horizon: int, value_col: str = "value"
) -> pd.DataFrame:
    """`ŷ(t+h)` = media histórica de `value` para `(entity_id, hora-del-día,
    finde?)` de `t+h`, estimada sobre `train`. Si no hay dato para esa
    combinación, cae a la media de la entidad, y luego a la media global."""
    tr = train.copy()
    tr["ts"] = pd.to_datetime(tr["ts"])
    tr["_hora"] = tr["ts"].dt.hour
    tr["_finde"] = (tr["ts"].dt.dayofweek >= 5).astype("int8")
    por_hora = tr.groupby(["entity_id", "_hora", "_finde"])[value_col].mean()
    por_entidad = tr.groupby("entity_id")[value_col].mean()
    global_ = float(tr[value_col].mean())

    out = _base(panel, horizon)
    ts_fut = pd.to_datetime(out["ts"]) + pd.Timedelta(hours=horizon)
    hora_fut = ts_fut.dt.hour
    finde_fut = (ts_fut.dt.dayofweek >= 5).astype("int8")
    claves = list(zip(out["entity_id"], hora_fut, finde_fut))
    pred = por_hora.reindex(claves).to_numpy()
    pred = pd.Series(pred, index=out.index)
    pred = pred.fillna(out["entity_id"].map(por_entidad)).fillna(global_)
    out["y_pred"] = pred.to_numpy()
    return out.drop(columns="value").dropna(subset=["y_true", "y_pred"])


BASELINES = {
    "persistencia": persistence,
    "seasonal_naive": seasonal_naive,
    "climatologia_horaria": hourly_climatology,
}
