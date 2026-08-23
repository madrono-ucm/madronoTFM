"""Tests de `herramientas.costes.resumen_costes` -- parchea `boto3.client`
para devolver los mismos fakes que ya usan los tests de cada módulo, sin
llamadas reales."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from herramientas.costes import resumen_costes
from herramientas.costes.tests.test_desglose_glue import FakeGlueClient, _run
from herramientas.costes.tests.test_lambda_costes import FakeCloudWatchClient as FakeLambdaCloudWatchClient
from herramientas.costes.tests.test_lambda_costes import FakeLambdaClient
from herramientas.costes.tests.test_s3_costes import FakeCloudWatchClient as FakeS3CloudWatchClient
from herramientas.costes.tests.test_s3_costes import FakeS3Client


class _CombinedFakeCloudWatchClient:
    """`resumen_costes.main` pide un cliente `cloudwatch` distinto para
    Lambda y para S3 (mismo `boto3.client("cloudwatch", ...)`, no hay forma
    de distinguirlos por parámetros) -- este fake enruta según qué
    dimensión trae la llamada real (`FunctionName` vs `BucketName`)."""

    def __init__(self, lambda_cw_client, s3_cw_client):
        self._lambda_cw_client = lambda_cw_client
        self._s3_cw_client = s3_cw_client

    def get_metric_statistics(self, Namespace, Dimensions, **kwargs):
        names = {d["Name"] for d in Dimensions}
        target = self._lambda_cw_client if "FunctionName" in names else self._s3_cw_client
        return target.get_metric_statistics(Namespace=Namespace, Dimensions=Dimensions, **kwargs)


def _fake_boto3_client(glue_client, lambda_client, lambda_cw_client, s3_client, s3_cw_client):
    combined_cw_client = _CombinedFakeCloudWatchClient(lambda_cw_client, s3_cw_client)

    def _client(service_name, region_name=None):
        return {
            "glue": glue_client,
            "lambda": lambda_client,
            "s3": s3_client,
            "cloudwatch": combined_cw_client,
        }[service_name]

    return _client


class MainTests(unittest.TestCase):
    def setUp(self):
        self.glue_client = FakeGlueClient({"madrono-tfm-dev-trafico-bronze-to-silver": [_run("r1", 1, 3600)]})
        self.lambda_client = FakeLambdaClient({"fn-a": 128})
        self.lambda_cw_client = FakeLambdaCloudWatchClient(
            {"fn-a": {"Invocations": [{"Sum": 10, "SampleCount": 1}], "Duration": [], "Errors": []}}
        )
        self.s3_client = FakeS3Client(["bucket-a"])
        self.s3_cw_client = FakeS3CloudWatchClient({"bucket-a": {"StandardStorage": 1024**3}})

    def test_formato_tabla_solo_glue_por_defecto(self):
        client_factory = _fake_boto3_client(
            self.glue_client, self.lambda_client, self.lambda_cw_client, self.s3_client, self.s3_cw_client
        )
        with patch("herramientas.costes.resumen_costes.boto3.client", side_effect=client_factory):
            out = io.StringIO()
            with redirect_stdout(out):
                resumen_costes.main(["--formato", "tabla"])
        text = out.getvalue()
        self.assertIn("Coste total estimado", text)
        self.assertNotIn("Lambda", text)
        self.assertNotIn("S3", text)

    def test_formato_json_incluye_lambda_y_s3_si_se_piden(self):
        client_factory = _fake_boto3_client(
            self.glue_client, self.lambda_client, self.lambda_cw_client, self.s3_client, self.s3_cw_client
        )
        with patch("herramientas.costes.resumen_costes.boto3.client", side_effect=client_factory):
            out = io.StringIO()
            with redirect_stdout(out):
                resumen_costes.main(["--formato", "json", "--incluir-lambda", "--incluir-s3"])
        report = json.loads(out.getvalue())
        self.assertIn("glue", report)
        self.assertIn("lambda", report)
        self.assertIn("s3", report)


if __name__ == "__main__":
    unittest.main()
