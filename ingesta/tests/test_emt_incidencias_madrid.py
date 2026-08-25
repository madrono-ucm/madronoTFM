"""Tests del productor de incidencias de EMT Madrid.

No hacen ninguna llamada de red: usan el fixture
`fixtures/emt_incidencias_sample.rss` (copia real y reducida de 2 items del
feed en vivo, capturados el 25/8/2026 -- ver
`ingesta/capturas/emt_incidencias_madrid.py`).
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.emt_incidencias_madrid import (
    normalize_record,
    select_sample_incidencias,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PATH = FIXTURES_DIR / "emt_incidencias_sample.rss"
SAMPLE_OUTPUT_PATH = Path(__file__).parent.parent / "capturas" / "samples" / "emt_incidencias_madrid_sample.json"


class SelectSampleIncidenciasTests(unittest.TestCase):
    def test_selects_up_to_sample_size(self):
        rss_bytes = SAMPLE_PATH.read_bytes()
        selected = select_sample_incidencias(rss_bytes, sample_size=1)
        self.assertEqual(len(selected), 1)

    def test_selects_all_when_sample_size_exceeds_available(self):
        rss_bytes = SAMPLE_PATH.read_bytes()
        selected = select_sample_incidencias(rss_bytes, sample_size=10)
        self.assertEqual(len(selected), 2)


class NormalizeRecordTests(unittest.TestCase):
    def setUp(self):
        rss_bytes = SAMPLE_PATH.read_bytes()
        self.items = select_sample_incidencias(rss_bytes, sample_size=10)
        self.ingested_at = datetime(2026, 8, 25, 21, 47, 14, tzinfo=timezone.utc)

    def test_normalizes_an_incident_with_affected_lines(self):
        record = normalize_record(self.items[0], self.ingested_at)

        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "madrid_emt_incidencias")
        self.assertEqual(record["incident_id"], "B60AFAC3-34A5-44B1-918E-BEADE2C8BD91")
        self.assertIn("Carretera de Castilla", record["title"])
        self.assertEqual(sorted(record["affected_lines"]), ["160", "161", "A", "N28"])
        self.assertEqual(record["cause"], "08 - Obras")
        self.assertEqual(record["effect"], "08 - Parada suprimida")
        self.assertEqual(record["valid_from"], "26/08/2026 6:00:00")
        self.assertEqual(record["valid_until"], "26/09/2026 19:00:00")
        self.assertEqual(record["ingested_at"], "2026-08-25T23:47:14+02:00")

    def test_parses_rfc822_pubdate_to_madrid_iso(self):
        record = normalize_record(self.items[0], self.ingested_at)
        # "Tue, 25 Aug 2026 14:46:47 GMT" -> hora de Madrid (UTC+2 en verano).
        self.assertEqual(record["published_at"], "2026-08-25T16:46:47+02:00")

    def test_two_distinct_incidents_have_different_ids(self):
        first = normalize_record(self.items[0], self.ingested_at)
        second = normalize_record(self.items[1], self.ingested_at)
        self.assertNotEqual(first["incident_id"], second["incident_id"])


class CommittedSampleTests(unittest.TestCase):
    def test_committed_sample_matches_expected_schema(self):
        records = json.loads(SAMPLE_OUTPUT_PATH.read_text(encoding="utf-8"))
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], "madrid_emt_incidencias")
            self.assertIsInstance(record["affected_lines"], list)


if __name__ == "__main__":
    unittest.main()
