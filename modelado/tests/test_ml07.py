import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from modelado.export import to_onnx


def _modelo_tiny():
    """LGBMRegressor pequeño sobre datos sintéticos con señal aprendible."""
    from lightgbm import LGBMRegressor

    rng = np.random.default_rng(0)
    n, f = 4000, 6
    X = rng.normal(0, 1, (n, f))
    y = 3 * X[:, 0] - 2 * X[:, 1] + X[:, 2] ** 2 + rng.normal(0, 0.1, n)
    cols = [f"f{i}" for i in range(f)]
    m = LGBMRegressor(n_estimators=60, num_leaves=15, min_child_samples=20, verbose=-1)
    m.fit(pd.DataFrame(X, columns=cols), y)
    return m, cols, pd.DataFrame(rng.normal(0, 1, (500, f)), columns=cols)


class OnnxExportTests(unittest.TestCase):
    def test_exportar_lightgbm_io_y_metadata(self):
        import onnx

        m, cols, X = _modelo_tiny()
        with tempfile.TemporaryDirectory() as tmp:
            out = to_onnx.exportar_lightgbm(m, cols, Path(tmp) / "m.onnx", unidades="u")
            g = onnx.load(str(out)).graph
            self.assertEqual(g.input[0].name, "input")
            self.assertEqual(g.input[0].type.tensor_type.shape.dim[1].dim_value, len(cols))
            self.assertEqual(g.output[0].type.tensor_type.shape.dim[1].dim_value, 1)
            meta = {p.key: p.value for p in onnx.load(str(out)).metadata_props}
            self.assertEqual(meta["features"], ",".join(cols))
            self.assertEqual(meta["n_features"], str(len(cols)))

    def test_paridad_nativo_vs_onnx(self):
        m, cols, X = _modelo_tiny()
        with tempfile.TemporaryDirectory() as tmp:
            out = to_onnx.exportar_lightgbm(m, cols, Path(tmp) / "m.onnx")
            y_nat = m.predict(X)
            dif = to_onnx.paridad(out, y_nat, X.to_numpy())
        # datos gaussianos continuos -> sin el artefacto de umbrales enteros:
        # la media debe ser diminuta.
        self.assertLess(dif["mean"], 1e-2)
        self.assertIn("p99", dif)
        self.assertEqual(dif["n"], len(X))

    def test_paridad_devuelve_stats(self):
        m, cols, X = _modelo_tiny()
        with tempfile.TemporaryDirectory() as tmp:
            out = to_onnx.exportar_lightgbm(m, cols, Path(tmp) / "m.onnx")
            dif = to_onnx.paridad(out, m.predict(X), X.to_numpy())
        for k in ("max", "p99", "mean", "n_sobre_1e-3", "n"):
            self.assertIn(k, dif)


if __name__ == "__main__":
    unittest.main()
