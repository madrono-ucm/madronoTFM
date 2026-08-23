"""Tests de `herramientas.costes.s3_costes` -- mockea S3/CloudWatch, sin
llamadas reales."""

import unittest
from datetime import datetime, timedelta, timezone

from herramientas.costes import s3_costes as sc


class FakeS3Client:
    def __init__(self, bucket_names: "list[str]"):
        self.bucket_names = bucket_names

    def list_buckets(self):
        return {"Buckets": [{"Name": n} for n in self.bucket_names]}


class FakeCloudWatchClient:
    def __init__(self, sizes: "dict[str, dict[str, float]]"):
        """`sizes` es `{bucket_name: {storage_type: bytes}}`."""
        self.sizes = sizes

    def get_metric_statistics(self, Namespace, MetricName, Dimensions, StartTime, EndTime, Period, Statistics):
        bucket_name = next(d["Value"] for d in Dimensions if d["Name"] == "BucketName")
        storage_type = next(d["Value"] for d in Dimensions if d["Name"] == "StorageType")
        value = self.sizes.get(bucket_name, {}).get(storage_type)
        if value is None:
            return {"Datapoints": []}
        return {
            "Datapoints": [
                {"Timestamp": datetime.now(timezone.utc) - timedelta(days=1), "Average": value}
            ]
        }


class SummarizeBucketTests(unittest.TestCase):
    def test_convierte_bytes_a_gb_y_calcula_coste(self):
        cw_client = FakeCloudWatchClient({"mi-bucket": {"StandardStorage": 10 * 1024**3}})
        summary = sc.summarize_bucket("mi-bucket", cw_client)
        self.assertAlmostEqual(summary["size_gb"], 10.0, places=3)
        self.assertAlmostEqual(summary["cost_per_month_usd"], 10.0 * sc.PRICE_PER_GB_MONTH_USD, places=4)

    def test_sin_datapoints_tamano_cero(self):
        cw_client = FakeCloudWatchClient({})
        summary = sc.summarize_bucket("bucket-vacio", cw_client)
        self.assertEqual(summary["size_gb"], 0.0)
        self.assertEqual(summary["cost_per_month_usd"], 0.0)


class BuildReportTests(unittest.TestCase):
    def test_ordena_buckets_por_coste_desc(self):
        s3_client = FakeS3Client(["bucket-grande", "bucket-pequeno"])
        cw_client = FakeCloudWatchClient(
            {
                "bucket-grande": {"StandardStorage": 100 * 1024**3},
                "bucket-pequeno": {"StandardStorage": 1 * 1024**3},
            }
        )
        report = sc.build_report(s3_client, cw_client)
        self.assertEqual(report["buckets"][0]["bucket_name"], "bucket-grande")
        self.assertEqual(report["buckets"][1]["bucket_name"], "bucket-pequeno")
        self.assertFalse(report["assumptions"]["cubre_peticiones_y_transferencia"])


if __name__ == "__main__":
    unittest.main()
