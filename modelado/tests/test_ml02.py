import unittest

import numpy as np
import pandas as pd

from modelado.datasets.splits import es_split_sin_fuga, temporal_split
from modelado.evaluation import metrics
from modelado.models import baselines


def _panel(entity_id="A", n=24 * 20, inicio="2026-08-01") -> pd.DataFrame:
    ts = pd.date_range(inicio, periods=n, freq="h")
    val = np.arange(n, dtype="float64")
    df = pd.DataFrame({"entity_id": entity_id, "ts": ts, "value": val})
    for h in (1, 3, 6):
        df[f"target_h{h}"] = df["value"].shift(-h)
    return df


class MetricsTests(unittest.TestCase):
    def test_mae_rmse(self):
        self.assertAlmostEqual(metrics.mae([1, 2, 3], [1, 2, 5]), 2 / 3)
        self.assertAlmostEqual(metrics.rmse([0, 0], [3, 4]), np.sqrt(12.5))

    def test_skill_score(self):
        # modelo perfecto vs referencia con error -> skill 1.0
        self.assertAlmostEqual(metrics.skill_score([1, 2, 3], [1, 2, 3], [2, 2, 2]), 1.0)
        # modelo == referencia -> skill 0
        self.assertAlmostEqual(metrics.skill_score([1, 2, 3], [2, 2, 2], [2, 2, 2]), 0.0)

    def test_ignora_nan(self):
        self.assertAlmostEqual(metrics.mae([1, np.nan, 3], [1, 5, 4]), 0.5)

    def test_episodio(self):
        yt = [10, 20, 30, 40]
        ys = [12, 18, 33, 45]
        d = metrics.evaluar_episodio(yt, ys, umbral=25)
        self.assertEqual(d["ep_positivos"], 2)  # 30, 40 reales >= 25
        self.assertAlmostEqual(d["ep_recall"], 1.0)  # 33, 45 previstos >= 25
        self.assertAlmostEqual(d["ep_precision"], 1.0)


class SplitTests(unittest.TestCase):
    def test_split_temporal_sin_fuga(self):
        p = _panel(n=24 * 20)  # 20 días
        tr, va, te = temporal_split(p, test_days=3, val_days=2)
        self.assertTrue(es_split_sin_fuga(tr, va, te))
        self.assertGreater(len(tr), len(va))
        self.assertGreater(len(tr), len(te))
        # test cubre ~3 días
        span_test = (pd.to_datetime(te["ts"]).max() - pd.to_datetime(te["ts"]).min()).days
        self.assertLessEqual(span_test, 3)


class BaselineTests(unittest.TestCase):
    def test_persistencia(self):
        p = _panel(n=24 * 10)
        r = baselines.persistence(p, horizon=1)
        # target_h1 = value+1 ; y_pred = value ; error constante 1
        self.assertTrue(np.allclose((r["y_true"] - r["y_pred"]), 1.0))

    def test_seasonal_naive(self):
        p = _panel(n=24 * 10)
        r = baselines.seasonal_naive(p, horizon=3)
        # y_pred(t+3) = value(t+3-24) = value en t-21 ; y_true = value(t+3)
        # value es un contador -> diferencia constante 24
        self.assertTrue(np.allclose((r["y_true"] - r["y_pred"]), 24.0))

    def test_climatologia_devuelve_prediccion_para_todo(self):
        p = _panel(n=24 * 15)
        tr, _, _ = temporal_split(p, test_days=3, val_days=2)
        r = baselines.hourly_climatology(tr, p, horizon=1)
        self.assertFalse(r["y_pred"].isna().any())
        self.assertEqual(len(r), p["target_h1"].notna().sum())


if __name__ == "__main__":
    unittest.main()
