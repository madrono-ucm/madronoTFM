"""Regenera los estudios de §7 (ML_08) contra los paneles reales.

    python -m modelado.evaluation.estudios.run_all            # calidad_aire + trafico (GBT) + calidad_aire (GNN)
    python -m modelado.evaluation.estudios.run_all --con-gnn-trafico   # + STGNN de trafico (~40 min CPU)

Estudio 1 (comparación baseline/GBT/GNN) y Estudio 2 (explicabilidad SHAP +
aristas). Las ablaciones 3 y 4 (§7.3) se descartan para esta entrega
(decisión 8). Artefactos en `modelado/evaluation/artifacts/estudios/`;
opcionalmente un run de MLflow por estudio (`--mlflow`).
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from modelado.evaluation.estudios import estudio_comparacion as ec

logger = logging.getLogger(__name__)
_ART = Path("modelado/evaluation/artifacts/estudios")

# target -> (panel Tier 1, panel de grafo para el STGNN o None)
_TARGETS = {
    "calidad_aire": ("modelado/_data/panel_calidad_aire.parquet", "modelado/_data/panel_calidad_aire_grafo.parquet"),
    "trafico": ("modelado/_data/panel_trafico.parquet", "modelado/_data/panel_trafico_grafo.parquet"),
}


def _un_target(nombre: str, panel_gbt: str, panel_gnn: "str | None", *, con_gnn: bool):
    from modelado.training.train_gbt import entrenar_todo

    tabla_gbt, artefactos = entrenar_todo(pd.read_parquet(panel_gbt), nombre=nombre)
    shap_por_h = {k.replace("shap_", ""): v for k, v in artefactos.items() if k.startswith("shap_h")}

    tabla_stgnn, edges = None, None
    if con_gnn and panel_gnn and Path(panel_gnn).exists():
        from modelado.training.train_stgnn import entrenar as entrenar_stgnn

        tabla_stgnn, edges = entrenar_stgnn(pd.read_parquet(panel_gnn), nombre=nombre)

    comp = ec.tabla_comparacion(tabla_gbt, tabla_stgnn, target=nombre)
    expl = ec.resumen_explicabilidad(shap_por_h, edges, target=nombre)

    _ART.mkdir(parents=True, exist_ok=True)
    comp.to_csv(_ART / f"comparacion_{nombre}.csv", index=False)
    (_ART / f"explicabilidad_{nombre}.json").write_text(
        json.dumps(expl, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    ec.figura_skill(comp, _ART / f"skill_{nombre}.png", titulo=f"{nombre} — skill por horizonte y modelo")
    return comp, expl


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", nargs="+", default=sorted(_TARGETS), choices=sorted(_TARGETS))
    ap.add_argument("--sin-gnn", action="store_true", help="salta el STGNN por completo (solo GBT + baselines)")
    ap.add_argument("--con-gnn-trafico", action="store_true", help="incluye el STGNN de trafico (~40 min CPU)")
    ap.add_argument("--mlflow", default=None, help="experimento MLflow (un run por estudio, tags.study=)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    log_run = None
    if args.mlflow:
        from modelado.registry.mlflow_setup import configurar, log_run as _lr

        configurar(args.mlflow)
        log_run = _lr

    todas_comp = []
    for t in args.targets:
        panel_gbt, panel_gnn = _TARGETS[t]
        con_gnn = not args.sin_gnn and (t != "trafico" or args.con_gnn_trafico)
        comp, expl = _un_target(t, panel_gbt, panel_gnn, con_gnn=con_gnn)
        todas_comp.append(comp)
        print(f"\n=== {t} ===\n{comp.to_string(index=False)}")

        if log_run:
            met = {
                f"{r.familia}_h{int(r.horizonte)}_skill": float(r.skill)
                for r in comp.itertuples() if pd.notna(r.skill)
            }
            log_run(
                run_name=f"estudio_comparacion_{t}",
                params={"target": t, "con_gnn": con_gnn},
                metrics=met,
                tags={"study": "comparacion"},
                artifacts=[str(_ART / f"comparacion_{t}.csv"), str(_ART / f"skill_{t}.png")],
            )
            log_run(
                run_name=f"estudio_explicabilidad_{t}",
                params={"target": t},
                metrics={},
                tags={"study": "explicabilidad"},
                artifacts=[str(_ART / f"explicabilidad_{t}.json")],
            )

    pd.concat(todas_comp, ignore_index=True).to_csv(_ART / "comparacion_todos.csv", index=False)
    print(f"\nartefactos -> {_ART}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
