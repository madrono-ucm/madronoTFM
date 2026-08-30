import inspect
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


def _torch_disponible():
    try:
        import torch  # noqa: F401

        return True
    except Exception:
        return False


@unittest.skipUnless(_torch_disponible(), "torch no instalado")
class StgnnOnnxExportTests(unittest.TestCase):
    """FIL_20: el STGNN SÍ se exporta a ONNX con el exportador dynamo de
    torch. Sintético (sin registry ni Athena), rápido."""

    def _modelo_y_ejemplo(self, n=18, longitud=10, f=6):
        import torch

        from modelado.models.stgnn import STGNN

        torch.manual_seed(0)
        m = STGNN(in_dim=f, hidden=16, n_horizontes=3, n_targets=1, capas_gnn=2, dropout=0.0).eval()
        x_seq = torch.randn(longitud, n, f)
        src = list(range(n - 1)) + list(range(1, n))
        dst = list(range(1, n)) + list(range(n - 1))
        ei = torch.tensor([src, dst], dtype=torch.long)
        ew = torch.rand(ei.shape[1])
        return m, (x_seq, ei, ew)

    def test_export_dynamo_paridad_y_nodos_dinamicos(self):
        """Un solo export (el paso lento): paridad exacta sobre el propio
        ejemplo Y sobre un grafo con distinto nº de nodos."""
        import torch

        if "dynamo" not in inspect.signature(torch.onnx.export).parameters:
            self.skipTest("torch demasiado antiguo: torch.onnx.export sin `dynamo=`")

        m, ej = self._modelo_y_ejemplo(n=18)
        with torch.no_grad():
            y_nat = m(*ej).numpy()
        with tempfile.TemporaryDirectory() as tmp:
            r = to_onnx.exportar_stgnn(m, ej, Path(tmp) / "stgnn.onnx", y_nativo=y_nat)
            self.assertTrue(Path(r["onnx"]).exists())
            self.assertLess(r["paridad"]["max"], 1e-4)  # ~float32 epsilon
            self.assertEqual(r["paridad"]["shape_onnx"], list(y_nat.shape))

            _m2, ej2 = self._modelo_y_ejemplo(n=25)  # misma semilla -> mismos pesos
            with torch.no_grad():
                y_nat2 = _m2(*ej2).numpy()
            dif = to_onnx.paridad_stgnn(Path(r["onnx"]), y_nat2, ej2)
        self.assertEqual(dif["shape_onnx"][0], 25)
        self.assertLess(dif["max"], 1e-4)


if __name__ == "__main__":
    unittest.main()
