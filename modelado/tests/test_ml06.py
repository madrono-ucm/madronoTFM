import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from modelado.evaluation import drift


class DriftTests(unittest.TestCase):
    def test_psi_cero_si_misma_distribucion(self):
        rng = np.random.default_rng(0)
        x = rng.normal(0, 1, 5000)
        self.assertLess(abs(drift.psi(x, x)), 1e-9)

    def test_psi_detecta_desplazamiento(self):
        rng = np.random.default_rng(0)
        a = rng.normal(0, 1, 5000)
        b = rng.normal(3, 1, 5000)  # media muy distinta
        self.assertGreater(drift.psi(a, b), 0.2)

    def test_ks_pvalue_bajo_con_deriva(self):
        rng = np.random.default_rng(1)
        d, p = drift._ks(rng.normal(0, 1, 2000), rng.normal(1.5, 1, 2000))
        self.assertGreater(d, 0.3)
        self.assertLess(p, 0.05)

    def test_tabla_drift_marca_columna_derivada(self):
        rng = np.random.default_rng(2)
        ref = pd.DataFrame({"estable": rng.normal(0, 1, 1000), "derivada": rng.normal(0, 1, 1000)})
        cur = pd.DataFrame({"estable": rng.normal(0, 1, 400), "derivada": rng.normal(2, 1, 400)})
        t = drift.tabla_drift(ref, cur, ["estable", "derivada"])
        fila = {r["feature"]: r["deriva"] for _, r in t.iterrows()}
        self.assertTrue(fila["derivada"])
        self.assertFalse(fila["estable"])

    def test_analizar_sobre_fixture(self):
        rng = np.random.default_rng(3)
        ts = pd.date_range("2026-08-01", periods=24 * 12, freq="h")
        partes = []
        for e in range(4):
            df = pd.DataFrame({
                "entity_id": f"E{e}", "ts": ts,
                "value": rng.normal(10, 2, len(ts)),
                "value_lag_1h": rng.normal(10, 2, len(ts)),
            })
            df["target_h1"] = df["value"].shift(-1)
            partes.append(df)
        panel = pd.concat(partes, ignore_index=True)
        with tempfile.TemporaryDirectory() as tmp:
            out = drift.analizar(
                panel, target="fixture", dias_recientes=3,
                con_evidently=False, out_dir=Path(tmp),
            )
        r = out["resumen"]
        self.assertEqual(r["n_ref"] + r["n_actual"], len(panel))
        self.assertIn("n_features_con_deriva", r)
        self.assertLessEqual(r["n_features_con_deriva"], r["n_features"])


if __name__ == "__main__":
    unittest.main()
