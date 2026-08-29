"""Reentrenamiento nocturno (ML_10). Pensado para un `cron` 1x/día en la EC2
del demonio (coste 0, sin tocar Terraform):

    30 3 * * *  cd /opt/madrono && AWS_PROFILE=madrono python -m modelado.training.retrain_nightly --rebuild-panel >> /var/log/madrono-retrain.log 2>&1

Cada noche: (opcional) regenera el panel (`ML_01`), reentrena LightGBM
(`ML_03`), evalúa (`ML_02`), loguea el run en MLflow (`ML_04`, experimento
`nightly`) y **promueve `@champion` solo si supera al vigente**. Deja una
fila por `(fecha, target, horizonte)` en
`modelado/evaluation/artifacts/nightly/historial.csv` — la historia de
"el modelo mejora según se acumulan datos" para §7.

No deja nada en bucle: corre una vez y termina (guardrail de
`tasks/README.md`).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
from pathlib import Path

import pandas as pd

from modelado.datasets.splits import temporal_split
from modelado.evaluation import metrics
from modelado.models import baselines, gbt

logger = logging.getLogger(__name__)
_HIST = Path("modelado/evaluation/artifacts/nightly/historial.csv")
_HORIZONTES = (1, 3, 6)

_PANELES = {
    "calidad_aire": "modelado/_data/panel_calidad_aire.parquet",
    "trafico": "modelado/_data/panel_trafico.parquet",
}
_BUILD_ARGS = {
    "calidad_aire": ["--target", "calidad_aire"],
    "trafico": ["--target", "trafico"],
}


def decidir_promocion(skill_nuevo: float, skill_vigente: "float | None", *, margen: float = 0.0) -> bool:
    """Promueve si no hay vigente, o si el nuevo skill supera al vigente por
    al menos `margen` (evita promociones por ruido)."""
    if skill_vigente is None:
        return True
    if skill_nuevo != skill_nuevo:  # NaN
        return False
    return skill_nuevo >= skill_vigente + margen


def _skill_champion(cliente, nombre_registrado: str) -> "float | None":
    try:
        mv = cliente.get_model_version_by_alias(nombre_registrado, "champion")
        r = cliente.get_run(mv.run_id)
        return r.data.metrics.get("gbt_skill_vs_ref")
    except Exception:  # noqa: BLE001 -- no hay champion todavía
        return None


def _rebuild_panel(target: str) -> None:
    from modelado.features.build import main as build_main

    out = _PANELES[target]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    hoy = dt.date.today()
    desde = (hoy - dt.timedelta(days=45)).isoformat()
    build_main([*_BUILD_ARGS[target], "--desde", desde, "--hasta", hoy.isoformat(), "--out", out])


def reentrenar(target: str, *, rebuild: bool, experimento: str = "nightly", margen: float = 0.0) -> pd.DataFrame:
    import mlflow

    from modelado.registry.mlflow_setup import configurar, log_run, marcar_champion

    if rebuild:
        logger.info("regenerando panel de %s", target)
        _rebuild_panel(target)

    panel = pd.read_parquet(_PANELES[target])
    feats = gbt.columnas_features(panel)
    tr, va, te = temporal_split(panel)
    configurar(experimento)
    cliente = mlflow.MlflowClient()
    hoy = dt.date.today().isoformat()

    filas = []
    for h in _HORIZONTES:
        model, _ = gbt.entrenar(tr, va, horizon=h, feature_cols=feats)
        pred = gbt.predecir(model, te, horizon=h, feature_cols=feats).set_index(["entity_id", "ts"])
        ref = baselines.persistence(te, horizon=h).set_index(["entity_id", "ts"])
        comun = pred.index.intersection(ref.index)
        m = metrics.evaluar_regresion(
            pred.loc[comun, "y_true"], pred.loc[comun, "y_pred"], y_ref=ref.loc[comun, "y_pred"]
        )
        nombre_reg = f"madrono-{target}-h{h}"
        skill_vigente = _skill_champion(cliente, nombre_reg)
        promover = decidir_promocion(m["skill_vs_ref"], skill_vigente, margen=margen)

        run_id = log_run(
            run_name=f"nightly_{hoy}_{target}_h{h}",
            params={"target": target, "horizonte": h, "fecha": hoy, "n_train": len(tr), "n_test": len(comun)},
            metrics={f"gbt_{k}": v for k, v in m.items()},
            tags={"job": "retrain_nightly", "promovido": str(promover)},
            model=model if promover else None,
            model_flavor="lightgbm",
            registered_name=nombre_reg if promover else None,
        )
        # `log_run` ya pone @champion a la versión nueva si `registered_name`;
        # si NO se promueve no se registra nada y el champion vigente queda.
        filas.append({
            "fecha": hoy, "target": target, "horizonte": h,
            "skill_nuevo": round(m["skill_vs_ref"], 4),
            "skill_vigente": round(skill_vigente, 4) if skill_vigente is not None else None,
            "promovido": promover, "n_test": len(comun), "run_id": run_id,
        })
    return pd.DataFrame(filas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", nargs="+", default=sorted(_PANELES), choices=sorted(_PANELES))
    ap.add_argument("--rebuild-panel", action="store_true", help="regenera el panel desde Athena (necesita AWS_PROFILE)")
    ap.add_argument("--experimento", default="nightly")
    ap.add_argument("--margen", type=float, default=0.0, help="mejora mínima de skill para promover")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    partes = [reentrenar(t, rebuild=args.rebuild_panel, experimento=args.experimento, margen=args.margen) for t in args.targets]
    tabla = pd.concat(partes, ignore_index=True)

    _HIST.parent.mkdir(parents=True, exist_ok=True)
    cab = not _HIST.exists()
    tabla.to_csv(_HIST, mode="a", header=cab, index=False)

    print(tabla.to_string(index=False))
    print(f"\nhistorial -> {_HIST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
