"""Tests del productor de tráfico de Madrid.

No hacen ninguna llamada de red: usan el fixture `fixtures/pm_sample.xml`,
una copia reducida de una respuesta real de
https://informo.madrid.es/informo/tmadrid/pm.xml capturada el 12/08/2026,
para poder verificar el parseo/normalización y la escritura a Bronze de
forma rápida y determinista.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.bronze import BronzeWriter
from ingesta.capturas.trafico_madrid import parse_records

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pm_sample.xml"


class ParseRecordsTests(unittest.TestCase):
    def setUp(self):
        self.xml_text = FIXTURE_PATH.read_text(encoding="utf-8")
        self.ingested_at = datetime(2026, 8, 12, 0, 0, 0, tzinfo=timezone.utc)
        self.records = list(parse_records(self.xml_text, self.ingested_at))

    def test_produces_one_record_per_pm_element(self):
        self.assertEqual(len(self.records), 3)

    def test_normalizes_a_healthy_record(self):
        record = self.records[0]
        self.assertEqual(record["point_id"], "9841")
        self.assertEqual(record["source"], "madrid_trafico_intensidad")
        self.assertEqual(record["intensity_vph"], 20)
        self.assertEqual(record["occupancy_pct"], 0)
        self.assertEqual(record["load_pct"], 0)
        self.assertEqual(record["saturation_intensity_vph"], 3100)
        self.assertFalse(record["has_error"])
        self.assertEqual(record["error_code"], "N")
        self.assertIn("Valle de Mena", record["description"])

    def test_parses_comma_decimal_coordinates(self):
        record = self.records[0]
        self.assertAlmostEqual(record["location"]["x"], 438339.375874991)
        self.assertAlmostEqual(record["location"]["y"], 4480454.96970565)
        self.assertEqual(record["location"]["srid"], "EPSG:25830")

    def test_parses_global_timestamp_as_madrid_local_time(self):
        # fecha_hora='12/08/2026 1:45:04' es hora de Madrid (verano => UTC+2);
        # se conserva en hora de Madrid, no se convierte a UTC (tarea 035).
        for record in self.records:
            self.assertEqual(record["measured_at"], "2026-08-12T01:45:04+02:00")

    def test_handles_missing_numeric_fields_and_error_flag(self):
        record = next(r for r in self.records if r["point_id"] == "5555")
        self.assertIsNone(record["intensity_vph"])
        self.assertIsNone(record["occupancy_pct"])
        self.assertTrue(record["has_error"])
        self.assertEqual(record["error_code"], "S")

    def test_records_are_json_serializable(self):
        json.dumps(self.records)


class BronzeWriterTests(unittest.TestCase):
    def test_write_batch_creates_partitioned_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            writer = BronzeWriter(tmp, dataset="trafico")
            moment = datetime(2026, 8, 12, 9, 30, 0, tzinfo=timezone.utc)
            records = [{"point_id": "1", "intensity_vph": 10}]

            out_path = writer.write_batch(records, moment=moment)

            self.assertTrue(out_path.exists())
            expected_dir = Path(tmp) / "trafico" / "fecha=2026-08-12" / "hora=09"
            self.assertEqual(out_path.parent, expected_dir)

            with out_path.open(encoding="utf-8") as f:
                written = json.load(f)
            self.assertEqual(written, records)


if __name__ == "__main__":
    unittest.main()
