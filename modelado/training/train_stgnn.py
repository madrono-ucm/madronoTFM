"""Entry point de Tier 2 (`ML_05`): entrena el GNN espacio-temporal
(`modelado/models/stgnn.py`) contra un panel de `ML_01` + el grafo urbano, lo
compara con la persistencia en la misma tabla que Tier 1, y saca la
**importancia de aristas** (gradiente de la pérdida respecto a `edge_weight`).

    python -m modelado.training.train_stgnn \
        --panel modelado/_data/panel_calidad_aire_grafo.parquet \
        --nombre calidad_aire --mlflow tier2

Grafo: por defecto se deriva de las coordenadas del panel (k-NN con núcleo
gaussiano). Con `--aristas-json path.json` (lista `[[id_a, id_b, dist_m], ...]`,
p. ej. exportada de las `PROXIMO_A` de Neo4j) usa el grafo real. `torch` (CPU)
es la única dependencia nueva; determinista (`--semilla`).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from modelado.datasets import graph_snapshots as gs
from modelado.evaluation import metrics
from modelado.models.stgnn import STGNN

logger = logging.getLogger(__name__)
_ART = Path("modelado/evaluation/artifacts")
_HORIZONTES = (1, 3, 6)


def _split_temporal_idx(ts_objetivo, *, test_days: int, val_days: int):
    """Máscaras booleanas train/val/test sobre la lista de horas objetivo,
    con los mismos cortes que `datasets.splits.temporal_split`."""
    ts = pd.to_datetime(pd.Series(ts_objetivo))
    t_max = ts.max()
    corte_test = t_max - dt.timedelta(days=test_days)
    corte_val = corte_test - dt.timedelta(days=val_days)
    tr = (ts <= corte_val).to_numpy()
    va = ((ts > corte_val) & (ts <= corte_test)).to_numpy()
    te = (ts > corte_test).to_numpy()
    return tr, va, te


def _estandarizar(train_arr, *arrs, eje):
    mu = train_arr.mean(axis=eje, keepdims=True)
    sd = train_arr.std(axis=eje, keepdims=True)
    sd = np.where(sd < 1e-6, 1.0, sd)
    return mu, sd, [(a - mu) / sd for a in (train_arr, *arrs)]


def _mse_enmascarado(pred, y, m):
    dif = (pred - y) * m
    n = m.sum().clamp_min(1.0)
    return (dif**2).sum() / n


def _preparar(panel: pd.DataFrame, *, longitud: int, aristas_json: "str | None", knn: int):
    panel = panel.copy()
    panel["entity_id"] = panel["entity_id"].astype(str)
    node_index = gs.indice_nodos(panel)
    coords = gs.coordenadas_por_nodo(panel, node_index)

    sin_coord = np.where(~np.isfinite(coords).all(axis=1))[0]
    if len(sin_coord):
        vivos = {eid for eid, i in node_index.items() if i not in set(sin_coord.tolist())}
        panel = panel[panel["entity_id"].isin(vivos)]
        node_index = gs.indice_nodos(panel)
        coords = gs.coordenadas_por_nodo(panel, node_index)
        logger.info("descartados %d nodos sin coordenadas -> %d nodos", len(sin_coord), len(node_index))

    if aristas_json:
        aristas = [tuple(x) for x in json.loads(Path(aristas_json).read_text(encoding="utf-8"))]
        edge_index, edge_weight = gs.edges_desde_lista(aristas, node_index)
        origen_grafo = f"neo4j:{Path(aristas_json).name}"
    else:
        edge_index, edge_weight = gs.edges_desde_coords(coords, k=knn)
        origen_grafo = f"coords-knn{knn}"

    feats = gs.columnas_features(panel)
    snaps = gs.construir_snapshots(panel, node_index, feats)
    vent = gs.ventanas_secuencia(snaps, longitud=longitud)
    return node_index, feats, edge_index, edge_weight, vent, origen_grafo


def entrenar(
    panel: pd.DataFrame,
    *,
    nombre: str,
    longitud: int = 12,
    hidden: int = 48,
    capas_gnn: int = 2,
    dropout: float = 0.3,
    lr: float = 5e-3,
    weight_decay: float = 1e-4,
    max_epocas: int = 150,
    paciencia: int = 20,
    semilla: int = 42,
    aristas_json: "str | None" = None,
    knn: int = 8,
    mlflow_experiment: "str | None" = None,
):
    torch.manual_seed(semilla)
    np.random.seed(semilla)

    node_index, feats, edge_index, edge_weight, vent, origen_grafo = _preparar(
        panel, longitud=longitud, aristas_json=aristas_json, knn=knn
    )
    idx_valor = feats.index("value")
    Xseq, Y, Mk, ts_obj = vent["Xseq"], vent["Y"], vent["M"], vent["ts_objetivo"]
    tr, va, te = _split_temporal_idx(ts_obj, test_days=3, val_days=2)
    if not (tr.any() and va.any() and te.any()):
        raise SystemExit("split vacío: la ventana de datos es demasiado corta para 3+2 días de holdout")

    persistencia_raw = Xseq[:, -1, :, idx_valor].copy()  # value(t) -> ŷ(t+h)
    _, _, (Xtr, Xva, Xte) = _estandarizar(Xseq[tr], Xseq[va], Xseq[te], eje=(0, 1, 2))
    y_mu, y_sd, (Ytr, Yva, Yte) = _estandarizar(Y[tr], Y[va], Y[te], eje=(0, 1))

    dev = torch.device("cpu")
    ei = torch.as_tensor(edge_index, dtype=torch.long, device=dev)
    ew = torch.as_tensor(edge_weight, dtype=torch.float32, device=dev)
    to = lambda a: torch.as_tensor(a, dtype=torch.float32, device=dev)
    Xtr_t, Ytr_t, Mtr_t = to(Xtr), to(Ytr), torch.as_tensor(Mk[tr])
    Xva_t, Yva_t, Mva_t = to(Xva), to(Yva), torch.as_tensor(Mk[va])
    Xte_t = to(Xte)

    modelo = STGNN(
        in_dim=len(feats), hidden=hidden, n_horizontes=len(_HORIZONTES),
        n_targets=1, capas_gnn=capas_gnn, dropout=dropout,
    ).to(dev)
    opt = torch.optim.Adam(modelo.parameters(), lr=lr, weight_decay=weight_decay)

    def _eval_split(Xt, Yt, Mt):
        modelo.eval()
        with torch.no_grad():
            perd, filas = 0.0, 0
            preds = []
            for i in range(Xt.size(0)):
                p = modelo(Xt[i], ei, ew).squeeze(-1)  # [N, H]
                preds.append(p)
                perd += _mse_enmascarado(p, Yt[i], Mt[i].float()).item()
                filas += 1
        return perd / max(filas, 1), torch.stack(preds)

    mejor, mejor_ep, espera, estado = float("inf"), 0, 0, None
    for ep in range(1, max_epocas + 1):
        modelo.train()
        orden = np.random.permutation(Xtr_t.size(0))
        tot = 0.0
        for i in orden:
            opt.zero_grad()
            p = modelo(Xtr_t[i], ei, ew).squeeze(-1)
            loss = _mse_enmascarado(p, Ytr_t[i], Mtr_t[i].float())
            loss.backward()
            opt.step()
            tot += loss.item()
        val, _ = _eval_split(Xva_t, Yva_t, Mva_t)
        if val < mejor - 1e-5:
            mejor, mejor_ep, espera = val, ep, 0
            estado = {k: v.detach().clone() for k, v in modelo.state_dict().items()}
        else:
            espera += 1
        if ep % 10 == 0 or espera == 0:
            logger.info("epoca %3d  train_mse=%.4f  val_mse=%.4f  (mejor @%d)", ep, tot / len(orden), val, mejor_ep)
        if espera >= paciencia:
            logger.info("early stopping en la epoca %d (mejor val @%d)", ep, mejor_ep)
            break
    if estado:
        modelo.load_state_dict(estado)

    # --- test: destandarizar y comparar con persistencia, por horizonte ---
    _, pred_te = _eval_split(Xte_t, to(Yte), torch.as_tensor(Mk[te]))
    pred_raw = pred_te.numpy() * y_sd + y_mu  # [S, N, H]
    y_raw = Y[te]  # [S, N, H]
    m_te = Mk[te]

    filas = []
    for hi, h in enumerate(_HORIZONTES):
        mask = m_te[:, :, hi]
        yt = y_raw[:, :, hi][mask]
        yp = pred_raw[:, :, hi][mask]
        yref = np.broadcast_to(persistencia_raw[te][:, :, None], y_raw.shape)[:, :, hi][mask]
        m_stgnn = metrics.evaluar_regresion(yt, yp, y_ref=yref)
        m_base = metrics.evaluar_regresion(yt, yref, y_ref=yref)
        filas.append({"h": h, "modelo": "stgnn", "n": int(mask.sum()), **m_stgnn})
        filas.append({"h": h, "modelo": "baseline (persistencia)", "n": int(mask.sum()), **m_base})
    tabla = pd.DataFrame(filas)

    # --- importancia de aristas: d(loss)/d(edge_weight) sobre test ---
    imp = _importancia_aristas(modelo, Xte_t, to(Yte), torch.as_tensor(Mk[te]), ei, ew, node_index)

    _ART.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(_ART / f"tier2_{nombre}.csv", index=False)
    (_ART / f"tier2_{nombre}_aristas.json").write_text(
        json.dumps(imp, indent=1, ensure_ascii=False), encoding="utf-8"
    )

    if mlflow_experiment:
        _log_mlflow(
            modelo, nombre, mlflow_experiment, tabla,
            params={
                "tier": 2, "target": nombre, "origen_grafo": origen_grafo,
                "n_nodos": len(node_index), "n_aristas_dirigidas": int(ei.size(1)),
                "longitud_ventana": longitud, "hidden": hidden, "capas_gnn": capas_gnn,
                "dropout": dropout, "lr": lr, "weight_decay": weight_decay,
                "epocas_efectivas": mejor_ep, "n_features": len(feats),
                "n_train": int(tr.sum()), "n_test": int(te.sum()),
            },
            artefactos=[_ART / f"tier2_{nombre}_aristas.json"],
        )

    return tabla, imp


def _importancia_aristas(modelo, Xt, Yt, Mt, ei, ew, node_index, *, muestras: int = 32):
    """`mean |d(loss)/d(edge_weight)|` sobre hasta `muestras` snapshots de
    test, plegado a aristas no dirigidas. Devuelve top-15 `(a, b, importancia)`
    + un ejemplo por nodo."""
    rev = {i: eid for eid, i in node_index.items()}
    modelo.eval()
    ew_var = ew.clone().detach().requires_grad_(True)
    acc = torch.zeros_like(ew_var)
    n = min(muestras, Xt.size(0))
    for i in range(n):
        modelo.zero_grad()
        if ew_var.grad is not None:
            ew_var.grad.zero_()
        p = modelo(Xt[i], ei, ew_var).squeeze(-1)
        loss = _mse_enmascarado(p, Yt[i], Mt[i].float())
        loss.backward()
        acc += ew_var.grad.abs()
    acc = (acc / max(n, 1)).detach().numpy()

    e = ei.numpy()
    plegado: "dict[tuple[int, int], float]" = {}
    for k in range(e.shape[1]):
        a, b = int(e[0, k]), int(e[1, k])
        clave = (min(a, b), max(a, b))
        plegado[clave] = plegado.get(clave, 0.0) + float(acc[k])

    orden = sorted(plegado.items(), key=lambda kv: kv[1], reverse=True)
    top = [
        {"a": rev[a], "b": rev[b], "importancia": round(v, 6)}
        for (a, b), v in orden[:15]
    ]
    # ejemplo: para el nodo con la arista más importante, sus vecinos por peso
    nodo = orden[0][0][0] if orden else None
    ejemplo = None
    if nodo is not None:
        vecinos = sorted(
            ((rev[b], v) for (a, b), v in plegado.items() if a == nodo),
            key=lambda x: x[1], reverse=True,
        )[:5]
        ejemplo = {"nodo": rev[nodo], "vecinos_por_importancia": [{"vecino": x[0], "importancia": round(x[1], 6)} for x in vecinos]}
    return {"top_aristas": top, "ejemplo_nodo": ejemplo}


def _log_mlflow(modelo, nombre, experimento, tabla, *, params, artefactos):
    from modelado.registry.mlflow_setup import configurar, log_run

    uri = configurar(experimento)
    logger.info("MLflow: %s  experiment=%s", uri, experimento)
    met = {}
    for _, r in tabla.iterrows():
        pref = "stgnn" if r["modelo"] == "stgnn" else "baseline"
        for k in ("mae", "rmse", "mape", "skill_vs_ref"):
            if k in r and pd.notna(r[k]):
                met[f"{pref}_h{int(r['h'])}_{k}"] = float(r[k])
    log_run(
        run_name=f"{nombre}_stgnn",
        params=params,
        metrics=met,
        tags={"tier": "2", "arquitectura": "graphsage+gru"},
        model=modelo,
        model_flavor="pytorch",
        # `pt2` (por defecto en MLflow 3) traza el grafo y exige input_example;
        # el forward lleva bucle temporal + index_add -> pickle clásico.
        model_kwargs={"serialization_format": "pickle"},
        artifacts=[str(a) for a in artefactos if Path(a).exists()],
        registered_name=f"madrono-stgnn-{nombre}",
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", required=True, type=Path)
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--aristas-json", default=None, help="lista [[id_a,id_b,dist_m],...] del grafo real (Neo4j)")
    ap.add_argument("--knn", type=int, default=8, help="vecinos del grafo de coordenadas si no hay --aristas-json")
    ap.add_argument("--longitud", type=int, default=12, help="horas de historia por muestra (GRU)")
    ap.add_argument("--hidden", type=int, default=48)
    ap.add_argument("--epocas", type=int, default=150)
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--mlflow", default=None, help="experimento MLflow (activa logging + registro)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    panel = pd.read_parquet(args.panel)
    tabla, imp = entrenar(
        panel, nombre=args.nombre, longitud=args.longitud, hidden=args.hidden,
        max_epocas=args.epocas, semilla=args.semilla, aristas_json=args.aristas_json,
        knn=args.knn, mlflow_experiment=args.mlflow,
    )
    pd.set_option("display.float_format", lambda v: f"{v:.4f}")
    print(f"\n{args.nombre}  (Tier 2 — STGNN)\n{tabla.to_string(index=False)}")
    if imp.get("ejemplo_nodo"):
        print(f"\nimportancia de aristas — ejemplo:\n  {json.dumps(imp['ejemplo_nodo'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
