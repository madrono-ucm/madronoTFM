"""FIL_33 (M2) — valida `viz/data/prevision_animada.parquet` y las funciones
puras de `viz/build_prevision_animada.py`.

No re-ejecuta el build (inferencia 24×3 sobre 1.798 nodos, ~1 min) — valida
el artefacto versionado + unidades de las funciones de mezcla.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from viz.build_prevision_animada import DIAS, _idw, _norm, _salud

_ART = Path(__file__).resolve().parents[1] / "viz" / "data" / "prevision_animada.parquet"
_COLS = {
    "node_id", "lat", "lon", "district", "day", "hour", "ts", "dow",
    "y_traf_obs", "y_traf_persist", "y_traf_h1", "y_traf_h3", "y_traf_h6",
    "y_traf_act_h1", "y_traf_act_h3", "y_traf_act_h6",
    "no2", "o3", "noise_db", "health_index",
}


class FuncionesPurasTests(unittest.TestCase):
    def test_norm_clip(self):
        self.assertEqual(_norm(None, 10.0), 0.0)
        self.assertEqual(_norm(-5, 10.0), 0.0)
        self.assertEqual(_norm(20, 10.0), 1.0)
        self.assertAlmostEqual(_norm(60, 75.0, 45.0), 0.5)

    def test_salud_monotona_y_acotada(self):
        limpio = _salud(0.0, 0.0, 0.0, 45.0)
        sucio = _salud(4.0, 200.0, 180.0, 75.0)
        self.assertEqual(limpio, 100.0)
        self.assertEqual(sucio, 0.0)
        self.assertLess(_salud(2.0, 80.0, 90.0, 60.0), limpio)

    def test_idw_pondera_por_cercania(self):
        est = {"cerca": (40.4, -3.7), "lejos": (40.9, -3.2)}
        v = _idw(40.4, -3.7, est, {"cerca": 10.0, "lejos": 100.0})
        self.assertLess(v, 20.0)  # domina la estación pegada


class ArtefactoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _ART.exists():
            raise unittest.SkipTest("falta viz/data/prevision_animada.parquet — corre el build")
        cls.d = pd.read_parquet(_ART)

    def test_forma(self):
        self.assertEqual(set(self.d.columns), _COLS)
        self.assertEqual(self.d["node_id"].nunique(), 1798)
        self.assertEqual(sorted(self.d["day"].unique()), sorted(DIAS))
        self.assertEqual(sorted(self.d["hour"].unique()), list(range(24)))
        self.assertEqual(len(self.d), 1798 * 24 * len(DIAS))

    def test_columnas_clave_sin_nan(self):
        for c in ("y_traf_h1", "y_traf_h3", "y_traf_h6", "no2", "o3", "health_index"):
            self.assertEqual(int(self.d[c].isna().sum()), 0, f"{c} tiene NaN")

    def test_persistencia_es_la_observacion(self):
        m = self.d.dropna(subset=["y_traf_obs"])
        self.assertTrue((m["y_traf_persist"] == m["y_traf_obs"]).all())

    def test_rangos(self):
        self.assertTrue(self.d["health_index"].between(0, 100).all())
        self.assertTrue(self.d["no2"].between(0, 500).all())
        self.assertTrue(self.d["o3"].between(0, 400).all())
        nd = self.d["noise_db"].dropna()
        self.assertTrue(nd.between(30, 100).all())


if __name__ == "__main__":
    unittest.main()
