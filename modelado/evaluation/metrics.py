"""Métricas de evaluación (ML_02), compartidas por Tier 1 (`ML_03`) y Tier 2
(`ML_05`). Puro numpy/pandas -- testable sin sklearn ni MLflow.

- Regresión: MAE, RMSE, MAPE (con guarda), y **skill score vs una
  referencia** (`1 - MSE_modelo / MSE_ref`, positivo = mejor que la
  referencia).
- Clasificación de "episodio" (el target cruza un umbral): precisión,
  recall, F1, PR-AUC.
- `evaluar_regresion(...)` y `evaluar_episodio(...)` devuelven un `dict`
  plano listo para `mlflow.log_metrics`.
"""

from __future__ import annotations

import numpy as np


def _limpio(y_true, y_pred):
    y_true = np.asarray(y_true, dtype="float64")
    y_pred = np.asarray(y_pred, dtype="float64")
    m = np.isfinite(y_true) & np.isfinite(y_pred)
    return y_true[m], y_pred[m]


def mae(y_true, y_pred) -> float:
    yt, yp = _limpio(y_true, y_pred)
    return float(np.mean(np.abs(yt - yp))) if yt.size else float("nan")


def rmse(y_true, y_pred) -> float:
    yt, yp = _limpio(y_true, y_pred)
    return float(np.sqrt(np.mean((yt - yp) ** 2))) if yt.size else float("nan")


def mape(y_true, y_pred, *, eps: float = 1.0) -> float:
    """MAPE con `eps` en el denominador para no explotar cerca de 0."""
    yt, yp = _limpio(y_true, y_pred)
    if not yt.size:
        return float("nan")
    return float(np.mean(np.abs((yt - yp) / np.maximum(np.abs(yt), eps))) * 100)


def skill_score(y_true, y_pred, y_ref) -> float:
    """`1 - MSE(modelo) / MSE(referencia)`. 0 = igual que la referencia
    (p. ej. persistencia); >0 = mejor; <0 = peor."""
    yt, yp = _limpio(y_true, y_pred)
    yt2, yr = _limpio(y_true, y_ref)
    n = min(yt.size, yt2.size)
    if n == 0:
        return float("nan")
    mse_m = np.mean((yt[:n] - yp[:n]) ** 2)
    mse_r = np.mean((yt2[:n] - yr[:n]) ** 2)
    return float(1 - mse_m / mse_r) if mse_r > 0 else float("nan")


def evaluar_regresion(y_true, y_pred, *, y_ref=None, prefijo: str = "") -> "dict[str, float]":
    p = f"{prefijo}_" if prefijo else ""
    out = {f"{p}mae": mae(y_true, y_pred), f"{p}rmse": rmse(y_true, y_pred), f"{p}mape": mape(y_true, y_pred)}
    if y_ref is not None:
        out[f"{p}skill_vs_ref"] = skill_score(y_true, y_pred, y_ref)
    return out


def _pr_auc(y_true_bin, score) -> float:
    """Área bajo la curva precisión-recall por regla del trapecio, sin
    sklearn. `score` = probabilidad/valor continuo del que se derivan los
    umbrales."""
    yt = np.asarray(y_true_bin, dtype="int8")
    s = np.asarray(score, dtype="float64")
    m = np.isfinite(s)
    yt, s = yt[m], s[m]
    if yt.sum() == 0 or yt.size == 0:
        return float("nan")
    orden = np.argsort(-s)
    yt = yt[orden]
    tp = np.cumsum(yt)
    fp = np.cumsum(1 - yt)
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / yt.sum()
    recall = np.concatenate([[0.0], recall])
    precision = np.concatenate([[1.0], precision])
    return float(np.trapezoid(precision, recall))


def evaluar_episodio(
    y_true, y_score, *, umbral: float, prefijo: str = ""
) -> "dict[str, float]":
    """`y_true`/`y_score` son el valor real y el previsto (continuos); el
    "episodio" es `valor >= umbral`. Precisión/recall/F1 sobre la
    predicción binarizada al mismo umbral, y PR-AUC usando `y_score` como
    ranking."""
    yt, ys = _limpio(y_true, y_score)
    if not yt.size:
        return {}
    real = (yt >= umbral).astype("int8")
    pred = (ys >= umbral).astype("int8")
    tp = int(np.sum((pred == 1) & (real == 1)))
    fp = int(np.sum((pred == 1) & (real == 0)))
    fn = int(np.sum((pred == 0) & (real == 1)))
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    p = f"{prefijo}_" if prefijo else ""
    return {
        f"{p}ep_precision": prec,
        f"{p}ep_recall": rec,
        f"{p}ep_f1": f1,
        f"{p}ep_pr_auc": _pr_auc(real, ys),
        f"{p}ep_positivos": int(real.sum()),
    }
