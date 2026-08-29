"""Explicabilidad de los modelos de árbol de `gbt.py` (ML_03): importancia
global de features vía SHAP (`TreeExplainer`), y una figura opcional.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def importancia_global(model, X: pd.DataFrame, *, muestra: int = 5000, top: int | None = None) -> pd.DataFrame:
    """`mean(|SHAP value|)` por feature sobre una muestra de `X`. Devuelve un
    `DataFrame` `feature / importancia_shap` ordenado descendente."""
    import shap

    Xs = X.sample(min(len(X), muestra), random_state=42) if len(X) > muestra else X
    explainer = shap.TreeExplainer(model)
    vals = explainer.shap_values(Xs)
    if isinstance(vals, list):  # clasificador binario -> [clase0, clase1]
        vals = vals[1]
    imp = np.abs(np.asarray(vals)).mean(axis=0)
    df = (
        pd.DataFrame({"feature": list(X.columns), "importancia_shap": imp})
        .sort_values("importancia_shap", ascending=False)
        .reset_index(drop=True)
    )
    return df.head(top) if top else df


def guardar_figura_importancia(df_imp: pd.DataFrame, out_path, *, titulo: str = "") -> bool:
    """Barra horizontal de `importancia_global`. Devuelve `False` sin error si
    matplotlib no está instalado."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    d = df_imp.head(20).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, max(3, 0.35 * len(d))))
    ax.barh(d["feature"], d["importancia_shap"])
    ax.set_xlabel("mean(|SHAP value|)")
    if titulo:
        ax.set_title(titulo)
    fig.tight_layout()
    from pathlib import Path

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True
