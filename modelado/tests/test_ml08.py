import unittest

import pandas as pd

from modelado.evaluation.estudios import estudio_comparacion as ec


def _tabla_gbt():
    return pd.DataFrame([
        {"h": 1, "modelo": "lightgbm", "n": 100, "mae": 2.0, "rmse": 3.0, "mape": 10.0, "skill_vs_ref": 0.3},
        {"h": 1, "modelo": "baseline (persistencia)", "n": 100, "mae": 2.8, "rmse": 4.0, "mape": 12.0, "skill_vs_ref": 0.0},
        {"h": 6, "modelo": "lightgbm", "n": 90, "mae": 4.0, "rmse": 6.0, "mape": 20.0, "skill_vs_ref": 0.7},
        {"h": 6, "modelo": "baseline (seasonal_naive)", "n": 90, "mae": 7.0, "rmse": 12.0, "mape": 40.0, "skill_vs_ref": 0.0},
    ])


def _tabla_stgnn():
    return pd.DataFrame([
        {"h": 1, "modelo": "stgnn", "n": 100, "mae": 2.4, "rmse": 3.5, "mape": 11.0, "skill_vs_ref": -0.1},
        {"h": 1, "modelo": "baseline (persistencia)", "n": 100, "mae": 2.8, "rmse": 4.0, "mape": 12.0, "skill_vs_ref": 0.0},
        {"h": 6, "modelo": "stgnn", "n": 90, "mae": 3.6, "rmse": 5.0, "mape": 18.0, "skill_vs_ref": 0.55},
    ])


class ComparacionTests(unittest.TestCase):
    def test_tabla_comparacion_familias_y_orden(self):
        t = ec.tabla_comparacion(_tabla_gbt(), _tabla_stgnn(), target="x")
        self.assertEqual(set(t.columns), {"target", "familia", "horizonte", "n", "mae", "rmse", "skill"})
        self.assertEqual(set(t["familia"]), {"baseline", "lightgbm", "stgnn"})
        # dentro de un horizonte, orden baseline -> lightgbm -> stgnn
        h1 = t[t["horizonte"] == 1]["familia"].tolist()
        self.assertEqual(h1, ["baseline", "lightgbm", "stgnn"])
        # una sola fila baseline por horizonte
        self.assertEqual(len(t[(t["horizonte"] == 1) & (t["familia"] == "baseline")]), 1)

    def test_solo_gbt_sin_stgnn(self):
        t = ec.tabla_comparacion(_tabla_gbt(), None, target="x")
        self.assertEqual(set(t["familia"]), {"baseline", "lightgbm"})

    def test_resumen_explicabilidad(self):
        shap = {"h1": [{"feature": "value", "importancia_shap": 10.0},
                       {"feature": "hora", "importancia_shap": 2.0}]}
        edges = {"top_aristas": [{"a": "A", "b": "B", "importancia": 5.0}], "ejemplo_nodo": {"nodo": "A"}}
        r = ec.resumen_explicabilidad(shap, edges, target="x", top=1)
        self.assertEqual(r["shap_top"]["h1"], [{"feature": "value", "importancia": 10.0}])
        self.assertEqual(r["aristas_top"], [{"a": "A", "b": "B", "importancia": 5.0}])
        self.assertEqual(r["aristas_ejemplo"], {"nodo": "A"})

    def test_figura_skill_no_rompe(self):
        import tempfile
        from pathlib import Path

        t = ec.tabla_comparacion(_tabla_gbt(), _tabla_stgnn(), target="x")
        with tempfile.TemporaryDirectory() as d:
            ec.figura_skill(t, Path(d) / "s.png", titulo="t")  # True/False según matplotlib, sin excepción


if __name__ == "__main__":
    unittest.main()
