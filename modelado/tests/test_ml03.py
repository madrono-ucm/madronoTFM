import unittest

import numpy as np
import pandas as pd

from modelado.datasets.splits import temporal_split
from modelado.models import gbt


def _panel_sintetico(n_ent=6, n=24 * 25):
    """Panel con señal aprendible: value ~ patrón diario + ruido; target_h1
    depende de value + hora."""
    rng = np.random.default_rng(0)
    partes = []
    ts = pd.date_range("2026-08-01", periods=n, freq="h")
    for e in range(n_ent):
        base = 10 + 5 * np.sin(2 * np.pi * ts.hour / 24) + e
        val = base + rng.normal(0, 0.5, n)
        df = pd.DataFrame({"entity_id": f"E{e}", "ts": ts, "value": val})
        df["value_lag_1h"] = df["value"].shift(1)
        df["value_lag_24h"] = df["value"].shift(24)
        df["hora"] = ts.hour
        df["es_finde"] = (ts.dayofweek >= 5).astype("int8")
        for h in (1, 3):
            df[f"target_h{h}"] = df["value"].shift(-h)
        partes.append(df)
    return pd.concat(partes, ignore_index=True).dropna(subset=["value_lag_24h"]).reset_index(drop=True)


class GbtTests(unittest.TestCase):
    def test_columnas_features_excluye_ids_y_targets(self):
        p = _panel_sintetico()
        feats = gbt.columnas_features(p)
        self.assertIn("value", feats)
        self.assertIn("value_lag_1h", feats)
        self.assertNotIn("entity_id", feats)
        self.assertNotIn("ts", feats)
        self.assertFalse(any(c.startswith("target_h") for c in feats))

    def test_entrenar_y_predecir_bate_a_la_media(self):
        p = _panel_sintetico()
        tr, va, te = temporal_split(p, test_days=3, val_days=2)
        model, feats = gbt.entrenar(tr, va, horizon=1)
        pred = gbt.predecir(model, te, horizon=1, feature_cols=feats)
        self.assertEqual(set(pred.columns), {"entity_id", "ts", "y_true", "y_pred"})
        mae_modelo = np.mean(np.abs(pred["y_true"] - pred["y_pred"]))
        mae_media = np.mean(np.abs(pred["y_true"] - tr[f"target_h1"].mean()))
        self.assertLess(mae_modelo, mae_media)  # el modelo aprende algo

    def test_clasificador_episodio_da_probabilidades(self):
        p = _panel_sintetico()
        tr, va, te = temporal_split(p, test_days=3, val_days=2)
        umbral = float(p["value"].quantile(0.8))
        clf, feats = gbt.entrenar_clasificador_episodio(tr, va, horizon=1, umbral=umbral)
        pred = gbt.predecir(clf, te, horizon=1, feature_cols=feats)
        self.assertTrue(((pred["y_pred"] >= 0) & (pred["y_pred"] <= 1)).all())


if __name__ == "__main__":
    unittest.main()
