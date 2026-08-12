"""Tests del productor de BiciMAD (bicicleta compartida).

No hacen ninguna llamada de red: usan los fixtures
`fixtures/bicimad_station_information_sample.json` y
`fixtures/bicimad_station_status_sample.json`, copias reducidas (3 y 2
estaciones respectivamente) de respuestas reales del feed público GBFS de
BiciMAD, capturadas en vivo desde este entorno (ver docstring de
`bicimad.py`). La estación `1408` aparece en `station_information` pero no en
`station_status`, a propósito, para verificar el caso de una estación sin
estado sincronizado.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.bicimad import parse_records

FIXTURES_DIR = Path(__file__).parent / "fixtures"
STATION_INFORMATION_PATH = FIXTURES_DIR / "bicimad_station_information_sample.json"
STATION_STATUS_PATH = FIXTURES_DIR / "bicimad_station_status_sample.json"


class ParseRecordsTests(unittest.TestCase):
    def setUp(self):
        self.station_information = json.loads(STATION_INFORMATION_PATH.read_text(encoding="utf-8"))
        self.station_status = json.loads(STATION_STATUS_PATH.read_text(encoding="utf-8"))
        self.ingested_at = datetime(2026, 8, 12, 9, 15, 30, tzinfo=timezone.utc)
        self.records = list(
            parse_records(self.station_information, self.station_status, self.ingested_at)
        )

    def test_produces_one_record_per_station_information_entry(self):
        self.assertEqual(len(self.records), 3)

    def test_normalizes_a_station_with_status(self):
        record = self.records[0]
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "bicimad_gbfs")
        self.assertEqual(record["station_id"], "1406")
        self.assertEqual(record["name"], "2 - Metro Callao")
        self.assertEqual(record["bikes_available"], 2)
        self.assertEqual(record["docks_available"], 23)
        self.assertEqual(record["docks_total"], 47)
        self.assertEqual(record["status"], "IN_SERVICE")
        self.assertTrue(record["is_renting"])
        self.assertEqual(record["measured_at"], "2026-08-12T01:13:00+00:00")
        self.assertEqual(record["ingested_at"], "2026-08-12T09:15:30+00:00")

    def test_parses_coordinates_as_lat_lon_wgs84(self):
        record = self.records[0]
        self.assertAlmostEqual(record["location"]["lat"], 40.4204)
        self.assertAlmostEqual(record["location"]["lon"], -3.70569)
        self.assertEqual(record["location"]["srid"], "EPSG:4326")

    def test_station_without_matching_status_gets_null_status_fields(self):
        record = next(r for r in self.records if r["station_id"] == "1408")
        self.assertEqual(record["name"], "4 - Malasaña")
        self.assertIsNone(record["bikes_available"])
        self.assertIsNone(record["docks_available"])
        self.assertIsNone(record["status"])
        self.assertIsNone(record["measured_at"])
        # Los metadatos fijos de station_information siguen presentes.
        self.assertEqual(record["docks_total"], 47)

    def test_records_are_json_serializable(self):
        json.dumps(self.records)


class SampleFixtureTests(unittest.TestCase):
    """Verifica que la muestra committeada en `capturas/samples/` es válida."""

    def test_committed_sample_matches_schema(self):
        sample_path = (
            Path(__file__).parent.parent / "capturas" / "samples" / "bicimad_sample.json"
        )
        records = json.loads(sample_path.read_text(encoding="utf-8"))

        self.assertGreater(len(records), 0)
        self.assertLessEqual(len(records), 10)
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], "bicimad_gbfs")
            self.assertIn("station_id", record)
            self.assertIn("bikes_available", record)
            self.assertIn("docks_available", record)
            self.assertIn("docks_total", record)
            self.assertIn("location", record)
            self.assertIn("lat", record["location"])
            self.assertIn("lon", record["location"])


if __name__ == "__main__":
    unittest.main()
