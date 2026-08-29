import unittest

import numpy as np
import pandas as pd
import torch

from modelado.datasets import graph_snapshots as gs
from modelado.models.stgnn import STGNN


def _panel_sintetico(n_ent=5, n=24 * 20):
    """Panel con difusión espacial: el valor de cada nodo arrastra al del
    vecino de la derecha una hora después (una señal que un GNN+GRU puede
    aprovechar)."""
    rng = np.random.default_rng(0)
    ts = pd.date_range("2026-08-01", periods=n, freq="h")
    lat = 40.40 + 0.01 * np.arange(n_ent)  # nodos en línea -> vecino = adyacente
    base = np.zeros((n, n_ent))
    base[0] = rng.normal(10, 1, n_ent)
    for t in range(1, n):
        base[t] = 0.6 * base[t - 1] + 0.3 * np.roll(base[t - 1], 1) + rng.normal(0, 0.5, n_ent)
    partes = []
    for e in range(n_ent):
        df = pd.DataFrame({
            "entity_id": f"E{e}", "ts": ts, "value": base[:, e],
            "lat": lat[e], "lon": -3.70,
        })
        df["value_lag_1h"] = df["value"].shift(1)
        df["value_lag_24h"] = df["value"].shift(24)
        df["hora_sin"] = np.sin(2 * np.pi * ts.hour / 24)
        for h in (1, 3, 6):
            df[f"target_h{h}"] = df["value"].shift(-h)
        partes.append(df)
    return pd.concat(partes, ignore_index=True).dropna(subset=["value_lag_24h"]).reset_index(drop=True)


class GraphSnapshotsTests(unittest.TestCase):
    def test_indice_y_features(self):
        p = _panel_sintetico()
        ni = gs.indice_nodos(p)
        self.assertEqual(sorted(ni.values()), list(range(5)))
        feats = gs.columnas_features(p)
        self.assertIn("value", feats)
        self.assertNotIn("entity_id", feats)
        self.assertNotIn("lat", feats)
        self.assertFalse(any(c.startswith("target_h") for c in feats))

    def test_edges_desde_coords_simetrico_sin_selfloop(self):
        coords = np.array([[40.40, -3.70], [40.41, -3.70], [40.42, -3.70], [40.60, -3.70]])
        ei, ew = gs.edges_desde_coords(coords, k=2)
        self.assertEqual(ei.shape[0], 2)
        self.assertEqual(ei.shape[1], ew.shape[0])
        self.assertFalse((ei[0] == ei[1]).any())  # sin self-loops
        pares = {frozenset((int(a), int(b))) for a, b in zip(ei[0], ei[1])}
        for a, b in zip(ei[0], ei[1]):  # simétrico
            self.assertIn(frozenset((int(b), int(a))), pares)
        self.assertTrue((ew > 0).all())

    def test_edges_desde_lista_ignora_nodos_fuera(self):
        ni = {"A": 0, "B": 1, "C": 2}
        ei, ew = gs.edges_desde_lista([("A", "B", 100.0), ("B", "Z", 50.0)], ni)
        self.assertEqual(ei.shape[1], 2)  # solo A-B, en las dos orientaciones

    def test_construir_snapshots_formas_y_mascara(self):
        p = _panel_sintetico()
        ni = gs.indice_nodos(p)
        feats = gs.columnas_features(p)
        snaps = gs.construir_snapshots(p, ni, feats)
        T = len(snaps["orden_ts"])
        self.assertEqual(snaps["X"].shape, (T, 5, len(feats)))
        self.assertEqual(snaps["Y"].shape, (T, 5, 3))
        self.assertEqual(snaps["M"].dtype, np.dtype(bool))
        # los últimos pasos no tienen target_h6 -> máscara en False
        self.assertFalse(snaps["M"][-1, :, 2].any())

    def test_ventanas_secuencia_sin_fuga(self):
        p = _panel_sintetico()
        ni = gs.indice_nodos(p)
        feats = gs.columnas_features(p)
        snaps = gs.construir_snapshots(p, ni, feats)
        vent = gs.ventanas_secuencia(snaps, longitud=6)
        S = vent["Xseq"].shape[0]
        self.assertEqual(vent["Xseq"].shape, (S, 6, 5, len(feats)))
        self.assertEqual(vent["Y"].shape, (S, 5, 3))
        # la muestra i mira X[i-5..i]; su objetivo es Y en orden_ts[i+5]
        self.assertEqual(vent["ts_objetivo"][0], snaps["orden_ts"][5])


class StgnnTests(unittest.TestCase):
    def test_forward_formas(self):
        torch.manual_seed(0)
        L, N, F = 4, 6, 3
        x = torch.randn(L, N, F)
        ei = torch.tensor([[0, 1, 2, 3, 4, 5], [1, 0, 3, 2, 5, 4]])
        ew = torch.ones(ei.shape[1])
        net = STGNN(in_dim=F, hidden=8, n_horizontes=3, n_targets=1, capas_gnn=2)
        out = net(x, ei, ew)
        self.assertEqual(tuple(out.shape), (N, 3, 1))

    def test_edge_weight_recibe_gradiente(self):
        torch.manual_seed(0)
        L, N, F = 3, 5, 2
        x = torch.randn(L, N, F)
        ei = torch.tensor([[0, 1, 2, 3, 4, 0], [1, 2, 3, 4, 0, 2]])
        ew = torch.ones(ei.shape[1], requires_grad=True)
        net = STGNN(in_dim=F, hidden=6, capas_gnn=2)
        out = net(x, ei, ew)
        out.sum().backward()
        self.assertIsNotNone(ew.grad)
        self.assertTrue(torch.isfinite(ew.grad).all())


if __name__ == "__main__":
    unittest.main()
