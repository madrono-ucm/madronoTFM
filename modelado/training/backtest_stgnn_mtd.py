"""FIL_38 — backtest del STGNN del proyecto (`modelado/models/stgnn.py`)
sobre el **Madrid Traffic Dataset** (MTD, Gómez & Ilarri, CC BY 4.0,
`10.17632/697ht4f65b.4`), subconjunto de 300 sensores, ~29 meses
(2022-06 .. 2024-10).

Objetivo: una tabla de resultados §7 más creíble que la ventana corta del
propio proyecto. **Results-only**: no toca los ONNX vendorizados ni las
tools; el modelo entrenado aquí es un artefacto de evaluación.

Entrada — ficheros de MTD v4 en `modelado/_data/mtd/` (descarga puntual,
ver `doc/FIL-38-...md`):
- `his_MTD_training_seq_len12_horizon12.npz`  -> `data` [T, 300, 3], `mean`, `std`
- `his_MTD_target_month_seq_len12_horizon12.npz`
- `idx_{train,val,test}_MTD_training_seq_len12_horizon12.npy`
- `MTD_adj_matrix.npy` (553×553) + `ids_MTD_training_...txt` (300) para filtrar
- `MTD_id_longitude_latitude.csv`

    python -m modelado.training.backtest_stgnn_mtd

Cero red, cero AWS. `torch` CPU. Determinista (`--semilla`).
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from modelado.evaluation import metrics
from modelado.models.stgnn import STGNN

logger = logging.getLogger(__name__)
_MTD = Path("modelado/_data/mtd")
_ART = Path("modelado/evaluation/artifacts")
_HORIZONTES = (1, 3, 6)
_SEQ = 12


def _cargar_mtd():
    tr = np.load(_MTD / "his_MTD_training_seq_len12_horizon12.npz")
    data = tr["data"].astype("float32")  # [T, N, 3]  (feat0 = intensidad estandarizada)
    mean, std = float(tr["mean"]), float(tr["std"])
    ids = [l.strip() for l in (_MTD / "ids_MTD_training_seq_len12_horizon12.txt").read_text().splitlines() if l.strip()]
    adj_full = np.load(_MTD / "MTD_adj_matrix.npy")
    coords = pd.read_csv(_MTD / "MTD_id_longitude_latitude.csv", dtype={"id": str})
    # el adj y las coords vienen del paquete completo (553) -> filtrar a los 300
    pos = {str(i): k for k, i in enumerate(coords["id"])}
    sel = [pos[i] for i in ids if i in pos]
    if len(sel) != data.shape[1]:
        # fallback: si no casan, usar los primeros N (mismo orden que el .npz)
        adj = adj_full[: data.shape[1], : data.shape[1]]
    else:
        adj = adj_full[np.ix_(sel, sel)]
    idx = {s: np.load(_MTD / f"idx_{s}_MTD_training_seq_len12_horizon12.npy") for s in ("train", "val", "test")}
    return data, mean, std, adj.astype("float32"), idx


def _edges_desde_adj(adj: np.ndarray, umbral: float = 1e-4):
    a, b = np.where((adj > umbral) & ~np.eye(len(adj), dtype=bool))
    return np.vstack([a, b]).astype("int64"), adj[a, b].astype("float32")


def _ventanas(data, anclas, *, stride: int):
    """De índices-ancla `t` a `(Xseq [S,L,N,3], Y [S,N,H], persist [S,N,H])`.
    `Y[.,.,h]` = feat0 (intensidad) en `t+h`; persistencia = feat0 en `t`."""
    T = data.shape[0]
    ok = [int(t) for t in anclas[::stride] if t - _SEQ + 1 >= 0 and t + max(_HORIZONTES) < T]
    X = np.stack([data[t - _SEQ + 1 : t + 1] for t in ok]).astype("float32")
    Y = np.stack([np.stack([data[t + h, :, 0] for h in _HORIZONTES], axis=-1) for t in ok]).astype("float32")
    P = np.stack([np.repeat(data[t, :, 0:1], len(_HORIZONTES), axis=1) for t in ok]).astype("float32")
    return X, Y, P


def entrenar(*, semilla=42, max_epocas=8, paciencia=2, hidden=48, stride=6, test_stride=4, lr=5e-3):
    torch.manual_seed(semilla)
    np.random.seed(semilla)
    data, mean, std, adj, idx = _cargar_mtd()
    N = data.shape[1]
    ei, ew = _edges_desde_adj(adj)
    logger.info("MTD: T=%d N=%d aristas=%d  split tr/va/te=%d/%d/%d",
                data.shape[0], N, ei.shape[1], *(len(idx[s]) for s in ("train", "val", "test")))

    Xtr, Ytr, _ = _ventanas(data, idx["train"], stride=stride)
    Xva, Yva, Pva = _ventanas(data, idx["val"], stride=stride)
    Xte, Yte, Pte = _ventanas(data, idx["test"], stride=test_stride)

    dev = torch.device("cpu")
    ei_t = torch.as_tensor(ei, device=dev)
    ew_t = torch.as_tensor(ew, device=dev)
    to = lambda a: torch.as_tensor(a, dtype=torch.float32, device=dev)
    modelo = STGNN(in_dim=3, hidden=hidden, n_horizontes=len(_HORIZONTES), n_targets=1).to(dev)
    opt = torch.optim.Adam(modelo.parameters(), lr=lr, weight_decay=1e-4)

    def _corre(Xt):
        modelo.eval()
        with torch.no_grad():
            return torch.stack([modelo(Xt[i], ei_t, ew_t).squeeze(-1) for i in range(Xt.size(0))])

    Xtr_t, Ytr_t = to(Xtr), to(Ytr)
    Xva_t, Yva_t = to(Xva), to(Yva)
    mejor, espera, estado = float("inf"), 0, None
    for ep in range(1, max_epocas + 1):
        modelo.train()
        for i in np.random.permutation(Xtr_t.size(0)):
            opt.zero_grad()
            p = modelo(Xtr_t[i], ei_t, ew_t).squeeze(-1)
            loss = torch.mean((p - Ytr_t[i]) ** 2)
            loss.backward()
            opt.step()
        val = torch.mean((_corre(Xva_t) - Yva_t) ** 2).item()
        if val < mejor - 1e-5:
            mejor, espera = val, 0
            estado = {k: v.detach().clone() for k, v in modelo.state_dict().items()}
        else:
            espera += 1
        logger.info("epoca %2d  val_mse=%.4f  (mejor %.4f, espera %d)", ep, val, mejor, espera)
        if espera >= paciencia:
            break
    if estado:
        modelo.load_state_dict(estado)

    pred = _corre(to(Xte)).numpy() * std + mean  # destandardizado -> veh/intervalo
    y_raw = Yte * std + mean
    p_raw = Pte * std + mean

    filas = []
    for hi, h in enumerate(_HORIZONTES):
        yt, yp, yref = y_raw[:, :, hi].ravel(), pred[:, :, hi].ravel(), p_raw[:, :, hi].ravel()
        m_stgnn = metrics.evaluar_regresion(yt, yp, y_ref=yref)
        m_base = metrics.evaluar_regresion(yt, yref, y_ref=yref)
        filas.append({"h": h, "modelo": "stgnn", "n": int(yt.size), **m_stgnn})
        filas.append({"h": h, "modelo": "persistencia", "n": int(yt.size), **m_base})
    tabla = pd.DataFrame(filas)

    _ART.mkdir(parents=True, exist_ok=True)
    tabla.to_csv(_ART / "backtest_mtd.csv", index=False)
    (_ART / "backtest_mtd.json").write_text(
        json.dumps(
            {
                "dataset": "MTD v4 (10.17632/697ht4f65b.4) subconjunto 300 sensores",
                "periodo": "2022-06 .. 2024-10 (~29 meses)",
                "n_nodos": N, "n_aristas": int(ei.shape[1]),
                "n_test_ventanas": int(Xte.shape[0]),
                "horizontes": list(_HORIZONTES),
                "resultados": filas,
            },
            indent=1, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return tabla


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--epocas", type=int, default=8)
    ap.add_argument("--stride", type=int, default=6, help="submuestreo de ventanas de train/val (CPU)")
    ap.add_argument("--test-stride", type=int, default=4, help="submuestreo de ventanas de test")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not (_MTD / "his_MTD_training_seq_len12_horizon12.npz").exists():
        raise SystemExit(
            "Faltan los ficheros de MTD en modelado/_data/mtd/ — ver doc/FIL-38-...md "
            "(descarga puntual de https://data.mendeley.com/datasets/697ht4f65b/4)"
        )
    tabla = entrenar(semilla=args.semilla, max_epocas=args.epocas,
                     stride=args.stride, test_stride=args.test_stride)
    pd.set_option("display.float_format", lambda v: f"{v:.3f}")
    print(f"\nMTD backtest — STGNN vs persistencia (300 sensores, ~29 meses)\n{tabla.to_string(index=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
