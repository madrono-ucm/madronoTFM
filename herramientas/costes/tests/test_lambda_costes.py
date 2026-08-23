"""Tests de `herramientas.costes.lambda_costes` -- mockea Lambda/CloudWatch,
sin llamadas reales."""

import unittest

from herramientas.costes import lambda_costes as lc


class FakeLambdaClient:
    def __init__(self, functions: "dict[str, int]"):
        """`functions` es `{function_name: memory_mb}`."""
        self.functions = functions

    def get_paginator(self, operation_name):
        assert operation_name == "list_functions"
        names = list(self.functions.keys())
        return _FakePaginator([{"Functions": [{"FunctionName": n} for n in names]}])

    def get_function_configuration(self, FunctionName):
        return {"MemorySize": self.functions[FunctionName]}


class _FakePaginator:
    def __init__(self, pages):
        self._pages = pages

    def paginate(self, **kwargs):
        return iter(self._pages)


class FakeCloudWatchClient:
    def __init__(self, metrics: "dict[str, dict[str, list]]"):
        """`metrics` es `{function_name: {metric_name: [{"Sum":..,"SampleCount":..}, ...]}}`."""
        self.metrics = metrics

    def get_metric_statistics(self, Namespace, MetricName, Dimensions, StartTime, EndTime, Period, Statistics):
        function_name = next(d["Value"] for d in Dimensions if d["Name"] == "FunctionName")
        datapoints = self.metrics.get(function_name, {}).get(MetricName, [])
        return {"Datapoints": datapoints}


class SummarizeFunctionTests(unittest.TestCase):
    def test_calcula_gb_segundos_y_coste(self):
        lambda_client = FakeLambdaClient({"fn-a": 512})
        cw_client = FakeCloudWatchClient(
            {
                "fn-a": {
                    "Invocations": [{"Sum": 1000, "SampleCount": 14}],
                    "Duration": [{"Sum": 500_000, "SampleCount": 1000}],
                    "Errors": [{"Sum": 3, "SampleCount": 14}],
                }
            }
        )
        summary = lc.summarize_function("fn-a", lambda_client, cw_client, window_days=14)

        self.assertEqual(summary["invocations"], 1000)
        self.assertEqual(summary["errors"], 3)
        self.assertAlmostEqual(summary["avg_duration_s"], 0.5, places=3)
        expected_gb_seconds = 1000 * 0.5 * (512 / 1024)
        self.assertAlmostEqual(summary["gb_seconds"], expected_gb_seconds, places=3)
        self.assertGreater(summary["total_cost_usd_ventana"], 0)

    def test_sin_invocaciones_coste_cero(self):
        lambda_client = FakeLambdaClient({"fn-b": 128})
        cw_client = FakeCloudWatchClient({"fn-b": {}})
        summary = lc.summarize_function("fn-b", lambda_client, cw_client, window_days=14)
        self.assertEqual(summary["invocations"], 0)
        self.assertEqual(summary["total_cost_usd_ventana"], 0.0)


class BuildReportTests(unittest.TestCase):
    def test_ordena_funciones_por_coste_desc(self):
        lambda_client = FakeLambdaClient({"fn-cara": 1024, "fn-barata": 128})
        cw_client = FakeCloudWatchClient(
            {
                "fn-cara": {
                    "Invocations": [{"Sum": 10000, "SampleCount": 14}],
                    "Duration": [{"Sum": 5_000_000, "SampleCount": 10000}],
                    "Errors": [{"Sum": 0, "SampleCount": 14}],
                },
                "fn-barata": {
                    "Invocations": [{"Sum": 10, "SampleCount": 14}],
                    "Duration": [{"Sum": 1000, "SampleCount": 10}],
                    "Errors": [{"Sum": 0, "SampleCount": 14}],
                },
            }
        )
        report = lc.build_report(lambda_client, cw_client, window_days=14)
        self.assertEqual(report["functions"][0]["function_name"], "fn-cara")
        self.assertEqual(report["functions"][1]["function_name"], "fn-barata")
        self.assertFalse(report["assumptions"]["free_tier_descontado"])


if __name__ == "__main__":
    unittest.main()
