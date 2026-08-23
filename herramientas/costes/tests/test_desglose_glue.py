"""Tests de `herramientas.costes.desglose_glue` -- mockea el cliente de
Glue (mismo patrón que `grafo/tests/test_extract.py`: una clase fake que
responde `get_paginator(...).paginate(...)` sin ninguna llamada de red
real, sin credenciales)."""

import unittest
from datetime import datetime, timedelta, timezone

from herramientas.costes import desglose_glue as dg


def _dt(days_ago: float) -> datetime:
    return datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc) - timedelta(days=days_ago)


def _run(run_id: str, started_days_ago: float, dpu_seconds, state: str = "SUCCEEDED", error=None) -> dict:
    run = {
        "Id": run_id,
        "JobRunState": state,
        "StartedOn": _dt(started_days_ago),
        "ExecutionTime": 100,
    }
    if dpu_seconds is not None:
        run["DPUSeconds"] = dpu_seconds
    if error:
        run["ErrorMessage"] = error
    return run


class _FakePaginator:
    def __init__(self, pages):
        self._pages = pages

    def paginate(self, **kwargs):
        return iter(self._pages)


class FakeGlueClient:
    """`jobs_and_runs` es `{job_name: [run, ...]}`."""

    def __init__(self, jobs_and_runs: "dict[str, list]"):
        self.jobs_and_runs = jobs_and_runs

    def get_paginator(self, operation_name):
        if operation_name == "get_jobs":
            names = list(self.jobs_and_runs.keys())
            return _FakePaginator([{"Jobs": [{"Name": n} for n in names]}])
        if operation_name == "get_job_runs":
            return self
        raise AssertionError(f"paginador inesperado: {operation_name}")

    def paginate(self, JobName):
        return iter([{"JobRuns": self.jobs_and_runs[JobName]}])


class DatasetFromJobNameTests(unittest.TestCase):
    def test_reconoce_los_cuatro_sufijos_conocidos(self):
        self.assertEqual(dg.dataset_from_job_name("madrono-tfm-dev-trafico-bronze-to-silver"), "trafico")
        self.assertEqual(dg.dataset_from_job_name("madrono-tfm-dev-trafico-silver-to-gold"), "trafico")
        self.assertEqual(
            dg.dataset_from_job_name("madrono-tfm-dev-agenda-eventos-silver-backfill-dedup"), "agenda-eventos"
        )
        self.assertEqual(
            dg.dataset_from_job_name("madrono-tfm-dev-agenda-eventos-gold-backfill-dedup"), "agenda-eventos"
        )

    def test_job_kind_sin_sufijo_conocido_es_otro(self):
        self.assertEqual(dg.job_kind("algo-sin-sufijo-reconocido"), "otro")


class ComputeTrendTests(unittest.TestCase):
    def test_sin_ejecuciones_completadas_suficientes_devuelve_none(self):
        runs = [_run("r1", 1, dpu_seconds=100)]
        self.assertIsNone(dg.compute_trend(runs))

    def test_detecta_tendencia_creciente(self):
        runs = [_run(f"r{i}", 10 - i, dpu_seconds=100 + i * 50) for i in range(10)]
        trend = dg.compute_trend(runs)
        self.assertEqual(trend["sample_size_real"], 5)
        self.assertGreater(trend["avg_dpu_seconds_last"], trend["avg_dpu_seconds_first"])
        self.assertGreater(trend["growth_pct"], 0)

    def test_ignora_ejecuciones_sin_dpu_seconds_running(self):
        runs = [_run("r1", 2, dpu_seconds=100), _run("r2", 1, dpu_seconds=None, state="RUNNING")]
        # Solo una ejecución completada -> no hay suficientes datos para tendencia.
        self.assertIsNone(dg.compute_trend(runs))


class ComputeProjectionTests(unittest.TestCase):
    def test_proyecta_coste_dia_y_mes(self):
        # 5 ejecuciones repartidas en 4 días -> 1 ejecución/día aprox.
        runs = [_run(f"r{i}", 4 - i, dpu_seconds=3600) for i in range(5)]
        projection = dg.compute_projection(runs, price_per_dpu_hour=0.44)
        self.assertAlmostEqual(projection["runs_per_day_historico"], 1.0, places=2)
        self.assertAlmostEqual(projection["avg_cost_usd_ultimas_ejecuciones"], 0.44, places=4)
        self.assertAlmostEqual(projection["cost_per_day_usd"], 0.44, places=2)
        self.assertAlmostEqual(projection["cost_per_month_usd"], 0.44 * 30, places=2)

    def test_una_sola_ejecucion_no_proyecta(self):
        runs = [_run("r1", 1, dpu_seconds=100)]
        self.assertIsNone(dg.compute_projection(runs, price_per_dpu_hour=0.44))


class SummarizeJobTests(unittest.TestCase):
    def test_suma_dpu_segundos_y_marca_ejecuciones_desperdiciadas(self):
        runs = [
            _run("r1", 3, dpu_seconds=3600, state="SUCCEEDED"),
            _run("r2", 2, dpu_seconds=1800, state="FAILED", error="boom"),
            _run("r3", 1, dpu_seconds=None, state="RUNNING"),
        ]
        summary = dg.summarize_job("madrono-tfm-dev-trafico-bronze-to-silver", runs, price_per_dpu_hour=0.44)

        self.assertEqual(summary["dataset"], "trafico")
        self.assertEqual(summary["num_runs"], 3)
        self.assertEqual(summary["num_runs_en_curso"], 1)
        self.assertAlmostEqual(summary["total_cost_usd"], (3600 + 1800) / 3600 * 0.44, places=4)
        self.assertEqual(len(summary["wasted_runs"]), 1)
        self.assertEqual(summary["wasted_runs"][0]["run_id"], "r2")
        self.assertAlmostEqual(summary["wasted_cost_usd"], 1800 / 3600 * 0.44, places=4)

    def test_sin_ejecuciones_desperdiciadas_lista_vacia_y_coste_cero(self):
        runs = [_run("r1", 1, dpu_seconds=100, state="SUCCEEDED")]
        summary = dg.summarize_job("job", runs, price_per_dpu_hour=0.44)
        self.assertEqual(summary["wasted_runs"], [])
        self.assertEqual(summary["wasted_cost_usd"], 0.0)


class BuildReportTests(unittest.TestCase):
    def test_agrega_por_dataset_y_ordena_por_coste_desc(self):
        client = FakeGlueClient(
            {
                "madrono-tfm-dev-trafico-bronze-to-silver": [_run("r1", 1, dpu_seconds=3600 * 10)],
                "madrono-tfm-dev-trafico-silver-to-gold": [_run("r2", 1, dpu_seconds=3600 * 5)],
                "madrono-tfm-dev-ruido-bronze-to-silver": [_run("r3", 1, dpu_seconds=3600)],
            }
        )
        report = dg.build_report(client, price_per_dpu_hour=1.0)

        self.assertEqual(report["price_per_dpu_hour_usd"], 1.0)
        self.assertAlmostEqual(report["total_cost_usd"], 16.0, places=4)
        self.assertEqual(report["datasets"][0]["dataset"], "trafico")
        self.assertAlmostEqual(report["datasets"][0]["total_cost_usd"], 15.0, places=4)
        self.assertEqual(report["datasets"][1]["dataset"], "ruido")
        self.assertEqual(report["jobs"][0]["job_name"], "madrono-tfm-dev-trafico-bronze-to-silver")

    def test_usa_precio_por_defecto_si_no_se_indica(self):
        client = FakeGlueClient({"job": [_run("r1", 1, dpu_seconds=3600)]})
        report = dg.build_report(client)
        self.assertEqual(report["price_per_dpu_hour_usd"], dg.DEFAULT_PRICE_PER_DPU_HOUR)


class FormatTableTests(unittest.TestCase):
    def test_produce_texto_no_vacio_con_las_secciones_esperadas(self):
        client = FakeGlueClient({"madrono-tfm-dev-trafico-bronze-to-silver": [_run("r1", 1, dpu_seconds=3600)]})
        report = dg.build_report(client, price_per_dpu_hour=0.44)
        text = dg.format_table(report)
        self.assertIn("Coste total estimado", text)
        self.assertIn("Por dataset:", text)
        self.assertIn("Por job", text)
        self.assertIn("trafico", text)


if __name__ == "__main__":
    unittest.main()
