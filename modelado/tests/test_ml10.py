import unittest

import numpy as np
import pandas as pd

from modelado.evaluation import backtest
from modelado.training.retrain_nightly import decidir_promocion


def _panel_sintetico(n_ent=5, dias=16):
    """Panel horario con señal diaria aprendible, `dias` días."""
    rng = np.random.default_rng(0)
    n = 24 * dias
    ts = pd.date_range("2026-08-01", periods=n, freq="h")
    partes = []
    for e in range(n_ent):
        base = 20 + 8 * np.sin(2 * np.pi * ts.hour / 24) + e
        val = base + rng.normal(0, 1.0, n)
        df = pd.DataFrame({"entity_id": f"E{e}", "ts": ts, "value": val})
        df["value_lag_1h"] = df["value"].shift(1)
        df["value_lag_24h"] = df["value"].shift(24)
        df["hora"] = ts.hour
        df["es_finde"] = (ts.dayofweek >= 5).astype("int8")
        for h in (1, 3, 6):
            df[f"target_h{h}"] = df["value"].shift(-h)
        partes.append(df)
    return pd.concat(partes, ignore_index=True).dropna(subset=["value_lag_24h"]).reset_index(drop=True)


class DecidirPromocionTests(unittest.TestCase):
    def test_sin_vigente_promueve(self):
        self.assertTrue(decidir_promocion(0.1, None))

    def test_mejor_promueve_peor_no(self):
        self.assertTrue(decidir_promocion(0.62, 0.60))
        self.assertFalse(decidir_promocion(0.58, 0.60))

    def test_margen(self):
        self.assertFalse(decidir_promocion(0.605, 0.60, margen=0.02))
        self.assertTrue(decidir_promocion(0.63, 0.60, margen=0.02))

    def test_nan_no_promueve(self):
        self.assertFalse(decidir_promocion(float("nan"), 0.5))


class BacktestTests(unittest.TestCase):
    def test_produce_curva_con_columnas(self):
        df = backtest.backtest_incremental(
            _panel_sintetico(dias=16), target="x",
            horizontes=(1, 3), test_days=2, min_train_days=5,
        )
        self.assertFalse(df.empty)
        self.assertEqual(
            set(df.columns),
            {"target", "fecha_corte", "horizonte", "n_train", "n_test", "mae", "rmse", "skill"},
        )
        # varios cortes de fecha, y n_train crece con la fecha (rolling origin)
        self.assertGreaterEqual(df["fecha_corte"].nunique(), 3)
        por_fecha = df[df["horizonte"] == 1].sort_values("fecha_corte")
        self.assertTrue((por_fecha["n_train"].diff().dropna() >= 0).all())

    def test_figura_no_rompe(self):
        import tempfile
        from pathlib import Path

        df = backtest.backtest_incremental(_panel_sintetico(dias=14), target="x", horizontes=(1,), test_days=2)
        with tempfile.TemporaryDirectory() as d:
            backtest.figura_skill_vs_fecha(df, Path(d) / "c.png", titulo="t")


if __name__ == "__main__":
    unittest.main()
