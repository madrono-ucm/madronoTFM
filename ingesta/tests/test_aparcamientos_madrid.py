"""Tests del productor de ocupación de aparcamientos de Madrid.

No hacen ninguna llamada de red: usan los fixtures
`fixtures/parking_list_sample.xml` y `fixtures/parking_detail_sample.xml`,
copias reducidas de respuestas SOAP reales del servicio `infoParking` de
datos.madrid.es, capturadas en vivo desde este entorno el 12/08/2026 (ver
docstring de `aparcamientos_madrid.py`). El aparcamiento `3` aparece en el
listado sin `lstOccupation`, a propósito, para verificar el caso de un
aparcamiento que no comparte ocupación en tiempo real.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.aparcamientos_madrid import (
    normalize_record,
    parse_list_parking,
    parse_total_spaces,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
LIST_PATH = FIXTURES_DIR / "parking_list_sample.xml"
DETAIL_PATH = FIXTURES_DIR / "parking_detail_sample.xml"


class ParseListParkingTests(unittest.TestCase):
    def setUp(self):
        self.xml_text = LIST_PATH.read_text(encoding="utf-8")
        self.entries = list(parse_list_parking(self.xml_text))

    def test_produces_one_entry_per_parking(self):
        self.assertEqual(len(self.entries), 3)

    def test_parses_an_entry_with_realtime_occupancy(self):
        entry = next(e for e in self.entries if e["parking_id"] == "5")
        self.assertEqual(entry["name"], "Nuestra Señora del Recuerdo")
        self.assertEqual(entry["address"], "Calle de la Hiedra")
        self.assertEqual(entry["free_spaces"], 431)
        self.assertEqual(entry["measured_at_raw"], "2026-08-12T03:17:36.000+02:00")
        self.assertAlmostEqual(entry["latitude"], 40.472181)
        self.assertAlmostEqual(entry["longitude"], -3.67916)

    def test_entry_without_occupancy_has_null_free_spaces(self):
        entry = next(e for e in self.entries if e["parking_id"] == "3")
        self.assertEqual(entry["name"], "Corazón de María II")
        self.assertIsNone(entry["free_spaces"])
        self.assertIsNone(entry["measured_at_raw"])


class ParseTotalSpacesTests(unittest.TestCase):
    def test_extracts_total_spaces_feature(self):
        xml_text = DETAIL_PATH.read_text(encoding="utf-8")
        self.assertEqual(parse_total_spaces(xml_text), 832)


class NormalizeRecordTests(unittest.TestCase):
    def test_normalizes_an_entry_with_occupancy_and_total(self):
        entries = list(parse_list_parking(LIST_PATH.read_text(encoding="utf-8")))
        entry = next(e for e in entries if e["parking_id"] == "5")
        ingested_at = datetime(2026, 8, 12, 9, 15, 30, tzinfo=timezone.utc)

        record = normalize_record(entry, total_spaces=832, ingested_at=ingested_at)

        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "madrid_aparcamientos_rotacionales")
        self.assertEqual(record["parking_id"], "5")
        self.assertEqual(record["name"], "Nuestra Señora del Recuerdo")
        self.assertEqual(record["free_spaces"], 431)
        self.assertEqual(record["total_spaces"], 832)
        self.assertEqual(record["measured_at"], "2026-08-12T01:17:36+00:00")
        self.assertEqual(record["ingested_at"], "2026-08-12T09:15:30+00:00")
        self.assertEqual(record["location"], {"lat": 40.472181, "lon": -3.67916, "srid": "EPSG:4326"})

    def test_normalizes_an_entry_without_occupancy_or_total(self):
        entries = list(parse_list_parking(LIST_PATH.read_text(encoding="utf-8")))
        entry = next(e for e in entries if e["parking_id"] == "3")
        ingested_at = datetime(2026, 8, 12, 9, 15, 30, tzinfo=timezone.utc)

        record = normalize_record(entry, total_spaces=None, ingested_at=ingested_at)

        self.assertIsNone(record["free_spaces"])
        self.assertIsNone(record["total_spaces"])
        self.assertIsNone(record["measured_at"])

    def test_records_are_json_serializable(self):
        entries = list(parse_list_parking(LIST_PATH.read_text(encoding="utf-8")))
        ingested_at = datetime(2026, 8, 12, 9, 15, 30, tzinfo=timezone.utc)
        records = [normalize_record(e, None, ingested_at) for e in entries]
        json.dumps(records)


class SampleFixtureTests(unittest.TestCase):
    """Verifica que la muestra commiteada en `capturas/samples/` es válida."""

    def test_committed_sample_matches_schema(self):
        sample_path = (
            Path(__file__).parent.parent / "capturas" / "samples" / "aparcamientos_madrid_sample.json"
        )
        records = json.loads(sample_path.read_text(encoding="utf-8"))

        self.assertGreater(len(records), 0)
        self.assertLessEqual(len(records), 10)
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], "madrid_aparcamientos_rotacionales")
            self.assertIn("parking_id", record)
            self.assertIn("free_spaces", record)
            self.assertIn("total_spaces", record)
            self.assertIn("location", record)
            self.assertIn("lat", record["location"])
            self.assertIn("lon", record["location"])


if __name__ == "__main__":
    unittest.main()
