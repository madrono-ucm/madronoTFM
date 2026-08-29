import tempfile
import unittest
from pathlib import Path

from modelado.registry import mlflow_setup


class MlflowSetupTests(unittest.TestCase):
    def test_log_run_registra_params_metrics_y_filtra_no_finitos(self):
        import mlflow

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            uri = f"sqlite:///{Path(tmp).as_posix()}/t.db"
            mlflow_setup.configurar("test_exp", tracking_uri=uri)
            run_id = mlflow_setup.log_run(
                run_name="r1",
                params={"target": "x", "horizonte": 1},
                metrics={"mae": 1.5, "skill": float("nan")},  # nan se filtra
                tags={"tier": "1"},
            )
            self.assertTrue(run_id)
            data = mlflow.get_run(run_id).data
            self.assertEqual(data.params["target"], "x")
            self.assertAlmostEqual(data.metrics["mae"], 1.5)
            self.assertNotIn("skill", data.metrics)  # no finito -> fuera
            self.assertIn("skill", data.tags["metricas_no_finitas"])


if __name__ == "__main__":
    unittest.main()
