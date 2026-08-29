"""Vigilancia de deriva (ML_06): compara la distribución de las features y
del target entre el periodo de entrenamiento y los datos más recientes.

Dos capas:

1.  **Estadística pura** (numpy, sin dependencias frágiles) -- PSI +
    Kolmogorov-Smirnov por feature. Es el resultado que siempre se produce
    y el que se loguea en MLflow ("nº de features con deriva significativa").
2.  **Informe Evidently** (`DataDriftPreset` + HTML) -- *best effort*: si
    `evidently` está instalado y su API responde, se guarda el HTML; si no,
    se anota y se sigue. La API de Evidently ha cambiado mucho entre
    versiones y el entorno es Python 3.14, así que no se hace depender la
    tarea de ella.

Con ~2-4 semanas de datos (`NEXT_STEPS.md` §4) el análisis es **ilustrativo,
no concluyente** (§7.4).

    python -m modelado.evaluation.drift --panel modelado/_data/panel_calidad_aire.parquet --target calidad_aire
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_ART = Path("modelado/evaluation/artifacts/drift")
_UMBRAL_PSI = 0.2   # regla habitual: <0.1 estable, 0.1-0.2 moderada, >0.2 deriva
_UMBRAL_P = 0.05


def psi(ref: np.ndarray, cur: np.ndarray, *, bins: int = 10) -> float:
    """Population Stability Index entre `ref` y `cur` con cortes por cuantiles
    de `ref`. 0 = idénticas; >0.2 se considera deriva."""
    ref = np.asarray(ref, dtype="float64")
    cur = np.asarray(cur, dtype="float64")
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]
    if ref.size == 0 or cur.size == 0:
        return float("nan")
    bordes = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if bordes.size < 2:
        return 0.0
    bordes[0], bordes[-1] = -np.inf, np.inf
    r = np.histogram(ref, bordes)[0] / ref.size
    c = np.histogram(cur, bordes)[0] / cur.size
    eps = 1e-6
    r = np.clip(r, eps, None)
    c = np.clip(c, eps, None)
    return float(np.sum((c - r) * np.log(c / r)))


def _ks(ref: np.ndarray, cur: np.ndarray) -> "tuple[float, float]":
    """Estadístico KS de 2 muestras y su p-valor. Usa scipy si está;
    si no, KS asintótico a mano."""
    ref = np.asarray(ref, dtype="float64")
    cur = np.asarray(cur, dtype="float64")
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]
    if ref.size < 2 or cur.size < 2:
        return float("nan"), float("nan")
    try:
        from scipy.stats import ks_2samp

        r = ks_2samp(ref, cur)
        return float(r.statistic), float(r.pvalue)
    except Exception:  # noqa: BLE001
        a, b = np.sort(ref), np.sort(cur)
        todos = np.concatenate([a, b])
        cdf_a = np.searchsorted(a, todos, side="right") / a.size
        cdf_b = np.searchsorted(b, todos, side="right") / b.size
        d = float(np.max(np.abs(cdf_a - cdf_b)))
        en = a.size * b.size / (a.size + b.size)
        lam = (np.sqrt(en) + 0.12 + 0.11 / np.sqrt(en)) * d
        p = 2 * np.sum([(-1) ** (k - 1) * np.exp(-2 * k**2 * lam**2) for k in range(1, 101)])
        return d, float(min(max(p, 0.0), 1.0))


def tabla_drift(
    ref: pd.DataFrame, cur: pd.DataFrame, columnas: "list[str]"
) -> pd.DataFrame:
    """PSI + KS por columna. `deriva_psi` = PSI > 0.2 (umbral interpretable);
    `deriva_ks` = p-valor KS < 0.05 (muy sensible al tamaño de muestra:
    con decenas de miles de filas marca casi todo). `deriva` = las dos."""
    filas = []
    for c in columnas:
        if c not in ref or c not in cur:
            continue
        p = psi(ref[c].to_numpy(), cur[c].to_numpy())
        d, pv = _ks(ref[c].to_numpy(), cur[c].to_numpy())
        d_psi = bool(np.isfinite(p) and p > _UMBRAL_PSI)
        d_ks = bool(np.isfinite(pv) and pv < _UMBRAL_P)
        filas.append({
            "feature": c,
            "psi": round(p, 4),
            "ks_stat": round(d, 4) if np.isfinite(d) else None,
            "ks_pvalue": round(pv, 4) if np.isfinite(pv) else None,
            "deriva_psi": d_psi,
            "deriva_ks": d_ks,
            "deriva": d_psi and d_ks,
        })
    return pd.DataFrame(filas).sort_values("psi", ascending=False, na_position="last").reset_index(drop=True)


def informe_evidently(ref: pd.DataFrame, cur: pd.DataFrame, out_dir: Path) -> "str | None":
    """Informe HTML de Evidently (`DataDriftPreset`). Devuelve la ruta del
    HTML o `None` si Evidently no está o su API no responde. Probado con
    `evidently 0.7.x` (`rep.run(...)` -> `Snapshot` con `save_html`)."""
    try:
        from evidently import Report
        from evidently.presets import DataDriftPreset
    except Exception:  # noqa: BLE001 -- no instalado o API vieja
        try:
            from evidently.report import Report  # <0.5
            from evidently.metric_preset import DataDriftPreset
        except Exception:  # noqa: BLE001
            logger.warning("evidently no disponible o API incompatible -- solo estadística pura")
            return None
    try:
        rep = Report(metrics=[DataDriftPreset()])
        salida = rep.run(reference_data=ref, current_data=cur)
        obj = salida if hasattr(salida, "save_html") else rep  # 0.7 devuelve Snapshot
        html = out_dir / "evidently_drift.html"
        obj.save_html(str(html))
        if hasattr(obj, "save_json"):
            obj.save_json(str(out_dir / "evidently_drift.json"))
        return html.as_posix()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Evidently falló (%s) -- solo estadística pura", type(exc).__name__)
        return None


def analizar(
    panel: pd.DataFrame,
    *,
    target: str,
    dias_recientes: int = 3,
    ts_col: str = "ts",
    con_evidently: bool = True,
    max_filas_evidently: int = 150_000,
    out_dir: "Path | None" = None,
) -> dict:
    """Parte el panel en referencia (lo antiguo) vs actual (últimos
    `dias_recientes` días) y calcula la deriva de features + target."""
    ts = pd.to_datetime(panel[ts_col])
    corte = ts.max() - dt.timedelta(days=dias_recientes)
    ref = panel[ts <= corte]
    cur = panel[ts > corte]
    if ref.empty or cur.empty:
        raise SystemExit("ventana insuficiente para partir referencia/actual")

    feat_cols = [
        c for c in panel.columns
        if c not in (ts_col, "entity_id") and not c.startswith("target_h")
        and pd.api.types.is_numeric_dtype(panel[c])
    ]
    tabla = tabla_drift(ref, cur, feat_cols)
    tgt_col = "target_h1" if "target_h1" in panel.columns else "value"
    tgt = tabla_drift(ref, cur, [tgt_col]).to_dict("records")

    out_dir = out_dir or (_ART / target)
    out_dir.mkdir(parents=True, exist_ok=True)
    cols = feat_cols + ([tgt_col] if tgt_col not in feat_cols else [])
    html = None
    if con_evidently:
        # Evidently monta un HTML pesado; con paneles de millones de filas se
        # submuestrea (la estadística pura de arriba sí usa todo).
        ev_ref = ref[cols].sample(min(len(ref), max_filas_evidently), random_state=42)
        ev_cur = cur[cols].sample(min(len(cur), max_filas_evidently), random_state=42)
        html = informe_evidently(ev_ref.reset_index(drop=True), ev_cur.reset_index(drop=True), out_dir)

    resumen = {
        "target": target,
        "ventana_ref": [str(ts[ts <= corte].min()), str(corte)],
        "ventana_actual": [str(corte), str(ts.max())],
        "n_ref": int(len(ref)),
        "n_actual": int(len(cur)),
        "n_features": len(feat_cols),
        "n_features_con_deriva": int(tabla["deriva"].sum()),          # PSI>0.2 y KS
        "n_deriva_psi": int(tabla["deriva_psi"].sum()),               # PSI>0.2
        "n_deriva_ks": int(tabla["deriva_ks"].sum()),                 # KS p<0.05 (sensible a n)
        "features_con_deriva": tabla.loc[tabla["deriva"], "feature"].tolist(),
        "features_deriva_psi": tabla.loc[tabla["deriva_psi"], "feature"].tolist(),
        "target_col": tgt_col,
        "target_deriva": tgt,
        "evidently_html": html,
        "nota": (
            "Ventana corta (NEXT_STEPS §4): la referencia (~10 d) y la actual "
            "(~3 d) no cubren los mismos días de la semana, de ahí el PSI alto "
            "de las features de calendario. KS con n grande marca casi todo; "
            "PSI (umbral 0.2) es el criterio de referencia. Ilustrativo, no "
            "concluyente (§7.4)."
        ),
    }
    (out_dir / "resumen.json").write_text(json.dumps(resumen, indent=1, ensure_ascii=False), encoding="utf-8")
    tabla.to_csv(out_dir / "features.csv", index=False)
    return {"resumen": resumen, "tabla": tabla}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", required=True, type=Path)
    ap.add_argument("--target", required=True)
    ap.add_argument("--dias-recientes", type=int, default=3)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    r = analizar(pd.read_parquet(args.panel), target=args.target, dias_recientes=args.dias_recientes)
    res = r["resumen"]
    print(f"\ndrift {args.target}:  PSI>0.2: {res['n_deriva_psi']}/{res['n_features']}   "
          f"KS p<0.05: {res['n_deriva_ks']}/{res['n_features']}   ambas: {res['n_features_con_deriva']}")
    print(f"  ref  {res['ventana_ref'][0][:13]} .. {res['ventana_ref'][1][:13]}  (n={res['n_ref']})")
    print(f"  now  {res['ventana_actual'][0][:13]} .. {res['ventana_actual'][1][:13]}  (n={res['n_actual']})")
    if res["features_deriva_psi"]:
        print("  deriva PSI:", ", ".join(res["features_deriva_psi"]))
    print(res["nota"])
    print(r["tabla"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
