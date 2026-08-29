"""Backtest incremental (rolling origin) para §7 (ML_10).

Los datos crecen ~1 día/día hasta la entrega. Para cada día `D` desde que
hay histórico suficiente, se entrena con `[inicio, D - test_days]` y se
evalúa en `(D - test_days, D]`; se registra el skill por horizonte. La
curva "skill vs fecha" es la historia de "el modelo mejora según se acumulan
datos".

    python -m modelado.evaluation.backtest --panel modelado/_data/panel_calidad_aire.parquet --target calidad_aire

Funciones puras salvo el entry point; el entrenamiento reusa
`modelado.models.gbt` (LightGBM de `ML_03`) y las métricas
`modelado.evaluation.metrics` (`ML_02`).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from modelado.evaluation import metrics
from modelado.models import baselines, gbt

logger = logging.getLogger(__name__)
_ART = Path("modelado/evaluation/artifacts/backtest")
_HORIZONTES = (1, 3, 6)


def _fit_predict(train: pd.DataFrame, test: pd.DataFrame, horizon: int, feats: "list[str]"):
    """Entrena LightGBM en `train` (val = último día) y predice en `test`."""
    ts = pd.to_datetime(train["ts"])
    corte_val = ts.max() - dt.timedelta(days=1)
    tr, va = train[ts <= corte_val], train[ts > corte_val]
    if len(va) < 50:  # muy poco train: sin early stopping
        va = tr
    model, _ = gbt.entrenar(tr, va, horizon=horizon, feature_cols=feats)
    return gbt.predecir(model, test, horizon=horizon, feature_cols=feats).set_index(["entity_id", "ts"])


def backtest_incremental(
    panel: pd.DataFrame,
    *,
    target: str,
    horizontes=_HORIZONTES,
    test_days: int = 2,
    min_train_days: int = 5,
    paso_dias: int = 1,
) -> pd.DataFrame:
    """Rolling origin. Devuelve una fila por `(fecha_corte, horizonte)` con
    `n`, `mae`, `rmse`, `skill` (vs persistencia)."""
    panel = panel.copy()
    panel["ts"] = pd.to_datetime(panel["ts"])
    feats = gbt.columnas_features(panel)
    dia_min = panel["ts"].min().normalize()
    dia_max = panel["ts"].max().normalize()

    filas = []
    d = dia_min + dt.timedelta(days=min_train_days + test_days)
    while d <= dia_max:
        corte_eval = d - dt.timedelta(days=test_days)
        train = panel[panel["ts"] <= corte_eval]
        test = panel[(panel["ts"] > corte_eval) & (panel["ts"] <= d)]
        if train.empty or test.empty:
            d += dt.timedelta(days=paso_dias)
            continue
        for h in horizontes:
            ref = baselines.persistence(test, horizon=h).set_index(["entity_id", "ts"])
            try:
                pred = _fit_predict(train, test, h, feats)
            except Exception as exc:  # noqa: BLE001 -- un día sin datos suficientes no rompe la curva
                logger.warning("D=%s h=%d: %s", d.date(), h, type(exc).__name__)
                continue
            comun = pred.index.intersection(ref.index)
            if comun.empty:
                continue
            m = metrics.evaluar_regresion(
                pred.loc[comun, "y_true"], pred.loc[comun, "y_pred"], y_ref=ref.loc[comun, "y_pred"]
            )
            filas.append({
                "target": target, "fecha_corte": d.date().isoformat(), "horizonte": h,
                "n_train": int(len(train)), "n_test": int(len(comun)),
                "mae": m["mae"], "rmse": m["rmse"], "skill": m["skill_vs_ref"],
            })
        d += dt.timedelta(days=paso_dias)
    return pd.DataFrame(filas)


def figura_skill_vs_fecha(df: pd.DataFrame, out_path, *, titulo: str = "") -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    if df.empty:
        return False
    fig, ax = plt.subplots(figsize=(8, 4))
    for h in sorted(df["horizonte"].unique()):
        sub = df[df["horizonte"] == h]
        ax.plot(pd.to_datetime(sub["fecha_corte"]), sub["skill"], marker="o", label=f"h{h}")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("skill vs persistencia")
    ax.set_xlabel("fecha de corte del backtest")
    ax.legend()
    if titulo:
        ax.set_title(titulo)
    fig.autofmt_xdate()
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", required=True, type=Path)
    ap.add_argument("--target", required=True)
    ap.add_argument("--test-days", type=int, default=2)
    ap.add_argument("--min-train-days", type=int, default=5)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    df = backtest_incremental(
        pd.read_parquet(args.panel), target=args.target,
        test_days=args.test_days, min_train_days=args.min_train_days,
    )
    _ART.mkdir(parents=True, exist_ok=True)
    df.to_csv(_ART / f"backtest_{args.target}.csv", index=False)
    figura_skill_vs_fecha(df, _ART / f"skill_vs_fecha_{args.target}.png", titulo=f"{args.target} — backtest incremental")

    pd.set_option("display.float_format", lambda v: f"{v:.4f}")
    print(f"\n{args.target}: {len(df)} puntos de backtest -> {_ART}/")
    if not df.empty:
        print(df.pivot_table(index="fecha_corte", columns="horizonte", values="skill").to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
