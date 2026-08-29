"""Entry point de Tier 1 (`ML_03`): entrena los forecasters LightGBM sobre
un panel de `ML_01`, los compara con las líneas base de `ML_02`, y saca la
importancia SHAP.

    python -m modelado.training.train_gbt --panel modelado/_data/panel_calidad_aire.parquet --nombre calidad_aire

Loguea en MLflow si `modelado.registry` (ML_04) está disponible; si no, deja
los artefactos en `modelado/evaluation/artifacts/`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from modelado.datasets.splits import temporal_split
from modelado.evaluation import metrics
from modelado.models import baselines, gbt, shap_explain

_ART = Path("modelado/evaluation/artifacts")


def _mejor_baseline(train, test, horizon):
    ref = baselines.persistence(test, horizon=horizon).set_index(["entity_id", "ts"])
    mejor, mejor_mae = None, float("inf")
    for nombre, fn in baselines.BASELINES.items():
        pred = (fn(train, test, horizon=horizon) if nombre == "climatologia_horaria" else fn(test, horizon=horizon))
        pred = pred.set_index(["entity_id", "ts"])
        comun = pred.index.intersection(ref.index)
        m = metrics.mae(pred.loc[comun, "y_true"], pred.loc[comun, "y_pred"])
        if m < mejor_mae:
            mejor, mejor_mae = nombre, m
    return mejor, ref


def entrenar_todo(
    panel: pd.DataFrame,
    *,
    nombre: str,
    horizontes=(1, 3, 6),
    umbral: float | None = None,
    mlflow_experiment: str | None = None,
):
    tr, va, te = temporal_split(panel)
    feats = gbt.columnas_features(panel)
    filas, artefactos = [], {}

    log_run = None
    if mlflow_experiment:
        from modelado.registry.mlflow_setup import configurar, log_run

        uri = configurar(mlflow_experiment)
        print(f"MLflow: {uri}  experiment={mlflow_experiment}")

    for h in horizontes:
        model, _ = gbt.entrenar(tr, va, horizon=h, feature_cols=feats)
        pred = gbt.predecir(model, te, horizon=h, feature_cols=feats).set_index(["entity_id", "ts"])

        nombre_bl, ref = _mejor_baseline(tr, te, h)
        comun = pred.index.intersection(ref.index)
        m_gbt = metrics.evaluar_regresion(
            pred.loc[comun, "y_true"], pred.loc[comun, "y_pred"], y_ref=ref.loc[comun, "y_pred"]
        )
        m_bl = metrics.evaluar_regresion(
            ref.loc[comun, "y_true"], ref.loc[comun, "y_pred"], y_ref=ref.loc[comun, "y_pred"]
        )
        filas.append({"h": h, "modelo": "lightgbm", "n": len(comun), **m_gbt})
        filas.append({"h": h, "modelo": f"baseline ({nombre_bl})", "n": len(comun), **m_bl})

        Xtest, _, _ = gbt._xy(te, h, feats)
        imp = shap_explain.importancia_global(model, Xtest, top=15)
        fig_path = _ART / f"shap_{nombre}_h{h}.png"
        shap_explain.guardar_figura_importancia(
            imp, fig_path, titulo=f"{nombre} h{h} — importancia SHAP"
        )
        artefactos[f"shap_h{h}"] = imp.to_dict("records")

        if log_run:
            log_run(
                run_name=f"{nombre}_h{h}_lightgbm",
                params={
                    "target": nombre, "horizonte": h, "modelo": "lightgbm",
                    "n_features": len(feats), "n_train": len(tr), "n_test": len(comun),
                    **gbt.PARAMS_REG,
                },
                metrics={
                    **{f"gbt_{k}": v for k, v in m_gbt.items()},
                    **{f"baseline_{k}": v for k, v in m_bl.items()},
                    "n_test": len(comun),
                },
                tags={"tier": "1", "baseline_ganadora": nombre_bl},
                model=model, model_flavor="lightgbm",
                artifacts=[str(fig_path)] if fig_path.exists() else [],
                registered_name=f"madrono-{nombre}-h{h}",
            )

        if umbral is not None:
            clf, _ = gbt.entrenar_clasificador_episodio(
                tr, va, horizon=h, umbral=umbral, feature_cols=feats
            )
            pc = gbt.predecir(clf, te, horizon=h, feature_cols=feats)  # y_pred = P(episodio)
            real = (pc["y_true"] >= umbral).astype("int8")
            pred_bin = (pc["y_pred"] >= 0.5).astype("int8")
            tp = int(((pred_bin == 1) & (real == 1)).sum())
            fp = int(((pred_bin == 1) & (real == 0)).sum())
            fn = int(((pred_bin == 0) & (real == 1)).sum())
            prec = tp / (tp + fp) if (tp + fp) else 0.0
            rec = tp / (tp + fn) if (tp + fn) else 0.0
            filas.append({
                "h": h, "modelo": "lightgbm-episodio", "n": len(pc),
                "ep_precision": prec, "ep_recall": rec,
                "ep_f1": (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0,
                "ep_pr_auc": metrics._pr_auc(real, pc["y_pred"]),
                "ep_positivos": int(real.sum()),
            })

    return pd.DataFrame(filas), artefactos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", required=True, type=Path)
    ap.add_argument("--nombre", required=True, help="etiqueta del target (calidad_aire / trafico / ...)")
    ap.add_argument("--umbral", type=float, default=None, help="umbral de 'episodio' (OMS / percentil)")
    ap.add_argument("--mlflow", default=None, help="nombre de experimento MLflow (activa el logging + registro)")
    args = ap.parse_args(argv)

    panel = pd.read_parquet(args.panel)
    tabla, art = entrenar_todo(
        panel, nombre=args.nombre, umbral=args.umbral, mlflow_experiment=args.mlflow
    )

    _ART.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(_ART / f"tier1_{args.nombre}.csv", index=False)
    (_ART / f"tier1_{args.nombre}_shap.json").write_text(json.dumps(art, indent=1, ensure_ascii=False))

    pd.set_option("display.float_format", lambda v: f"{v:.4f}")
    print(f"\n{args.nombre}  ({len(panel):,} filas)")
    print(tabla.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
