"""Tests del productor de transporte público (EMT Madrid).

No hacen ninguna llamada de red: usan los fixtures `fixtures/emt_arrivals_sample.json`
(respuesta del endpoint de llegadas) y `fixtures/emt_login_v11_sample.json`
(respuesta del login v1.1, con un `accessToken` de ejemplo claramente falso,
no una credencial real), ambos con la misma forma exacta que devuelve la API
MobilityLabs real (ver docstring de `transporte_publico_madrid.py`), para
poder verificar el parseo/normalización y el flujo de login sin depender de
red ni de credenciales reales.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from ingesta.capturas.transporte_publico_madrid import (
    CaptureConfig,
    fetch_access_token,
    parse_records,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "emt_arrivals_sample.json"
LOGIN_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "emt_login_v11_sample.json"


def _make_config(**overrides) -> CaptureConfig:
    defaults = dict(
        base_url="https://openapi.emtmadrid.es",
        stop_id="70",
        client_id="fake-client-id",
        pass_key="fake-pass-key",
        timeout_seconds=5.0,
        max_retries=1,
        retry_backoff_seconds=0.0,
        sample_size=5,
    )
    defaults.update(overrides)
    return CaptureConfig(**defaults)


def _fake_response(body: dict):
    response = mock.Mock()
    response.raise_for_status = mock.Mock()
    response.json = mock.Mock(return_value=body)
    return response


class ParseRecordsTests(unittest.TestCase):
    def setUp(self):
        self.response_json = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.stop_id = "71"
        self.ingested_at = datetime(2026, 8, 12, 9, 15, 30, tzinfo=timezone.utc)
        self.records = list(parse_records(self.response_json, self.stop_id, self.ingested_at))

    def test_produces_one_record_per_arrive_element(self):
        self.assertEqual(len(self.records), 4)

    def test_normalizes_a_healthy_record(self):
        record = self.records[0]
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "madrid_emt_llegadas")
        self.assertEqual(record["stop_id"], "71")
        self.assertEqual(record["line"], "27")
        self.assertEqual(record["bus_id"], 1234)
        self.assertEqual(record["destination"], "PLAZA CASTILLA")
        self.assertEqual(record["estimate_arrive_sec"], 180)
        self.assertEqual(record["distance_bus_m"], 950)
        self.assertFalse(record["is_head"])
        self.assertEqual(record["ingested_at"], "2026-08-12T09:15:30+00:00")

    def test_parses_coordinates_as_lon_lat_wgs84(self):
        record = self.records[0]
        self.assertAlmostEqual(record["location"]["lon"], -3.700123)
        self.assertAlmostEqual(record["location"]["lat"], 40.420456)
        self.assertEqual(record["location"]["srid"], "EPSG:4326")

    def test_parses_is_head_flag(self):
        head_record = next(r for r in self.records if r["bus_id"] == 4321)
        self.assertTrue(head_record["is_head"])

    def test_handles_missing_fields(self):
        record = self.records[-1]
        self.assertIsNone(record["line"])
        self.assertIsNone(record["bus_id"])
        self.assertIsNone(record["estimate_arrive_sec"])
        self.assertIsNone(record["distance_bus_m"])
        self.assertIsNone(record["location"]["lon"])
        self.assertIsNone(record["location"]["lat"])

    def test_records_are_json_serializable(self):
        json.dumps(self.records)


class FetchAccessTokenTests(unittest.TestCase):
    """Prueba el login v1.1 (x-ClientId/passKey), sustituyendo `requests.get`."""

    def setUp(self):
        self.login_body = json.loads(LOGIN_FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_sends_client_id_and_pass_key_headers_not_email_password(self):
        config = _make_config()
        with mock.patch(
            "ingesta.capturas.transporte_publico_madrid.requests.get",
            return_value=_fake_response(self.login_body),
        ) as fake_get:
            token = fetch_access_token(config)

        self.assertEqual(token, "FAKE-ACCESS-TOKEN-NOT-A-REAL-CREDENTIAL")
        fake_get.assert_called_once()
        _, kwargs = fake_get.call_args
        self.assertEqual(kwargs["headers"]["x-ClientId"], "fake-client-id")
        self.assertEqual(kwargs["headers"]["passKey"], "fake-pass-key")
        self.assertNotIn("email", kwargs["headers"])
        self.assertNotIn("password", kwargs["headers"])

    def test_calls_v1_1_login_endpoint(self):
        config = _make_config()
        with mock.patch(
            "ingesta.capturas.transporte_publico_madrid.requests.get",
            return_value=_fake_response(self.login_body),
        ) as fake_get:
            fetch_access_token(config)

        args, _ = fake_get.call_args
        self.assertIn("/v1.1/mobilitylabs/user/login/", args[0])

    def test_accepts_code_01_token_extend_as_success(self):
        # La API puede devolver code="01" ("Token extend...") en vez de "00"
        # ("Register user...") si ya había una sesión reciente en caché para
        # estas credenciales; ambos traen un accessToken válido (verificado
        # en vivo, ver docstring del módulo).
        body = dict(self.login_body, code="01", description="Token extend into control-cache")
        config = _make_config()
        with mock.patch(
            "ingesta.capturas.transporte_publico_madrid.requests.get",
            return_value=_fake_response(body),
        ):
            token = fetch_access_token(config)

        self.assertEqual(token, "FAKE-ACCESS-TOKEN-NOT-A-REAL-CREDENTIAL")

    def test_raises_on_error_code(self):
        body = {"code": "99", "description": "Error", "data": []}
        config = _make_config()
        with mock.patch(
            "ingesta.capturas.transporte_publico_madrid.requests.get",
            return_value=_fake_response(body),
        ):
            with self.assertRaises(RuntimeError):
                fetch_access_token(config)

    def test_raises_when_credentials_missing(self):
        config = _make_config(client_id=None, pass_key=None)
        with self.assertRaises(RuntimeError):
            fetch_access_token(config)


class SampleFixtureTests(unittest.TestCase):
    """Verifica que la muestra committeada en `capturas/samples/` es válida."""

    def test_committed_sample_matches_schema(self):
        sample_path = (
            Path(__file__).parent.parent
            / "capturas"
            / "samples"
            / "transporte_publico_madrid_sample.json"
        )
        records = json.loads(sample_path.read_text(encoding="utf-8"))

        self.assertGreater(len(records), 0)
        self.assertLessEqual(len(records), 10)
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], "madrid_emt_llegadas")
            self.assertIn("stop_id", record)
            self.assertIn("location", record)
            self.assertIn("lon", record["location"])
            self.assertIn("lat", record["location"])


if __name__ == "__main__":
    unittest.main()
