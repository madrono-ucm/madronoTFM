"""Consolidación pura de las salidas de Tier 1/Tier 2 en las tablas de §7
(ML_08). Sin credenciales, sin entrenar -- recibe los `DataFrame` que
devuelven `train_gbt.entrenar_todo` y `train_stgnn.entrenar`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_MODELOS_ORDEN = ["baseline", "lightgbm", "stgnn"]


def _familia(modelo: str) -> str:
    m = str(modelo).lower()
    if "baseline" in m:
        return "baseline"
    if "stgnn" in m or "gnn" in m:
        return "stgnn"
    if "light" in m or "gbt" in m or "lgbm" in m:
        return "lightgbm"
    return m


def tabla_comparacion(
    tabla_gbt: pd.DataFrame,
    tabla_stgnn: "pd.DataFrame | None" = None,
    *,
    target: str,
) -> pd.DataFrame:
    """Una fila por `(target, familia_modelo, h)` con MAE/RMSE/skill. `skill`
    es `skill_vs_ref` tal como lo calcula cada entry point (vs la mejor línea
    base en Tier 1, vs persistencia en Tier 2); la fila `baseline` la aporta
    Tier 1 (su mejor línea base) y se marca como referencia (`skill = 0`).
    """
    frames = []
    for src in (tabla_gbt, tabla_stgnn):
        if src is None or src.empty:
            continue
        d = src.copy()
        d["familia"] = d["modelo"].map(_familia)
        d["target"] = target
        frames.append(d[["target", "familia", "h", "n", "mae", "rmse", "skill_vs_ref"]])
    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={"skill_vs_ref": "skill", "h": "horizonte"})
    # una fila baseline por horizonte (la de Tier 1); dedup por si Tier 2
    # trae otra
    out = out.sort_values(["horizonte", "familia"]).drop_duplicates(
        ["target", "familia", "horizonte"], keep="first"
    )
    out["_ord"] = out["familia"].map({m: i for i, m in enumerate(_MODELOS_ORDEN)}).fillna(9)
    return out.sort_values(["horizonte", "_ord"]).drop(columns="_ord").reset_index(drop=True)


def resumen_explicabilidad(
    shap_por_h: "dict[str, list[dict]]",
    edges: "dict | None" = None,
    *,
    target: str,
    top: int = 8,
) -> dict:
    """SHAP top-k por horizonte (Tier 1) + aristas top-k (Tier 2) en un solo
    dict, listo para `json.dump` y para la tabla de §7.3."""
    shap_top = {
        h: [{"feature": r["feature"], "importancia": round(float(r["importancia_shap"]), 5)}
            for r in filas[:top]]
        for h, filas in (shap_por_h or {}).items()
    }
    out = {"target": target, "shap_top": shap_top}
    if edges:
        out["aristas_top"] = edges.get("top_aristas", [])[:top]
        out["aristas_ejemplo"] = edges.get("ejemplo_nodo")
    return out


def figura_skill(tabla: pd.DataFrame, out_path, *, titulo: str = "") -> bool:
    """Barras de `skill` por horizonte y familia de modelo. `False` sin error
    si no hay matplotlib."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    familias = [f for f in _MODELOS_ORDEN if f in set(tabla["familia"])]
    horizontes = sorted(tabla["horizonte"].unique())
    x = np.arange(len(horizontes))
    ancho = 0.8 / max(len(familias), 1)
    fig, ax = plt.subplots(figsize=(7, 4))
    for i, fam in enumerate(familias):
        sub = tabla[tabla["familia"] == fam].set_index("horizonte").reindex(horizontes)
        ax.bar(x + i * ancho, sub["skill"].to_numpy(), ancho, label=fam)
    ax.set_xticks(x + ancho * (len(familias) - 1) / 2)
    ax.set_xticklabels([f"h{h}" for h in horizontes])
    ax.set_ylabel("skill vs referencia")
    ax.axhline(0, color="k", lw=0.8)
    ax.legend()
    if titulo:
        ax.set_title(titulo)
    fig.tight_layout()
    from pathlib import Path

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True
