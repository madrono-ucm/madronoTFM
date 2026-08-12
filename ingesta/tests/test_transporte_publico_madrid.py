"""Tests del productor de transporte público (EMT Madrid).

No hacen ninguna llamada de red: usan el fixture
`fixtures/emt_arrivals_sample.json`, una respuesta de ejemplo con la misma
forma exacta que devuelve el endpoint real de llegadas de la API MobilityLabs
(`v2/transport/busemtmad/stops/{stop_id}/arrives/`), verificada contra el
esquema real de la API (ver docstring de `transporte_publico_madrid.py`),
para poder verificar el parseo/normalización sin depender de credenciales.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.transporte_publico_madrid import parse_records

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "emt_arrivals_sample.json"


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
