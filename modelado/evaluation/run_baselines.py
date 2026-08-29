"""Ejecuta las 3 líneas base (`ML_02`) sobre un panel de `ML_01` y saca la
tabla de métricas por horizonte -- el suelo que Tier 1/2 tienen que superar.

    python -m modelado.evaluation.run_baselines --panel modelado/_data/panel_calidad_aire.parquet
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from modelado.datasets.splits import temporal_split
from modelado.evaluation import metrics
from modelado.models import baselines


def evaluar_panel(panel: pd.DataFrame, *, horizontes=(1, 3, 6), test_days=3, val_days=2) -> pd.DataFrame:
    tr, _, te = temporal_split(panel, test_days=test_days, val_days=val_days)
    te_idx = te.set_index(["entity_id", "ts"])
    filas = []
    for h in horizontes:
        # persistencia como referencia del skill score
        ref = baselines.persistence(te, horizon=h).set_index(["entity_id", "ts"])
        for nombre, fn in baselines.BASELINES.items():
            pred = (fn(tr, te, horizon=h) if nombre == "climatologia_horaria" else fn(te, horizon=h))
            pred = pred.set_index(["entity_id", "ts"])
            comun = pred.index.intersection(ref.index)
            m = metrics.evaluar_regresion(
                pred.loc[comun, "y_true"], pred.loc[comun, "y_pred"],
                y_ref=ref.loc[comun, "y_pred"],
            )
            filas.append({"horizonte_h": h, "baseline": nombre, "n": len(comun), **m})
    return pd.DataFrame(filas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", required=True, type=Path)
    ap.add_argument("--test-days", type=int, default=3)
    ap.add_argument("--val-days", type=int, default=2)
    args = ap.parse_args(argv)

    panel = pd.read_parquet(args.panel)
    tabla = evaluar_panel(panel, test_days=args.test_days, val_days=args.val_days)
    pd.set_option("display.float_format", lambda v: f"{v:.4f}")
    print(f"\n{args.panel.name}  ({len(panel):,} filas, {panel['entity_id'].nunique()} entidades)")
    print(tabla.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
