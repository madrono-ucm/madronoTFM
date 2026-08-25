"""Tests del productor de parques y jardines municipales de Madrid.

No hacen ninguna llamada de red: usan el fixture `fixtures/parques_jardines_sample.xml`
(copia real y reducida de 2 fichas del catálogo, con las descripciones
largas recortadas para mantener el fixture pequeño -- ver
`ingesta/capturas/parques_jardines_madrid.py` para el esquema real).
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.parques_jardines_madrid import (
    normalize_record,
    select_sample_parques,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PATH = FIXTURES_DIR / "parques_jardines_sample.xml"
SAMPLE_OUTPUT_PATH = Path(__file__).parent.parent / "capturas" / "samples" / "parques_jardines_madrid_sample.json"


class SelectSampleParquesTests(unittest.TestCase):
    def test_selects_up_to_sample_size(self):
        xml_bytes = SAMPLE_PATH.read_bytes()
        selected = select_sample_parques(xml_bytes, sample_size=1)
        self.assertEqual(len(selected), 1)

    def test_selects_all_with_coordinates_when_sample_size_exceeds_available(self):
        # El fixture trae 3 <contenido> reales: 2 con LATITUD/LONGITUD y 1
        # sin ellas (caso real encontrado en el catálogo) -- solo los 2 con
        # coordenadas deben pasar el filtro.
        xml_bytes = SAMPLE_PATH.read_bytes()
        selected = select_sample_parques(xml_bytes, sample_size=10)
        self.assertEqual(len(selected), 2)


class NormalizeRecordTests(unittest.TestCase):
    def setUp(self):
        xml_bytes = SAMPLE_PATH.read_bytes()
        self.parques = select_sample_parques(xml_bytes, sample_size=10)
        self.ingested_at = datetime(2026, 8, 25, 21, 44, 25, tzinfo=timezone.utc)

    def test_normalizes_a_park_with_full_location(self):
        record = normalize_record(self.parques[0], self.ingested_at)

        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "madrid_parques_jardines")
        self.assertEqual(record["park_id"], "5986859")
        self.assertEqual(record["name"], "El Capricho de la Alameda Osuna")
        self.assertEqual(record["district"], "BARAJAS")
        self.assertEqual(record["neighbourhood"], "ALAMEDA DE OSUNA")
        self.assertEqual(record["address"], "PASEO ALAMEDA DE OSUNA 25")
        self.assertEqual(record["postal_code"], "28042")
        self.assertAlmostEqual(record["location"]["lat"], 40.45446361509569)
        self.assertAlmostEqual(record["location"]["lon"], -3.6000964360303476)
        self.assertEqual(record["location"]["srid"], "EPSG:4326")
        self.assertEqual(record["ingested_at"], "2026-08-25T23:44:25+02:00")

    def test_second_park_has_no_schedule(self):
        record = normalize_record(self.parques[1], self.ingested_at)
        self.assertEqual(record["name"], "Jardines Gregorio Ordóñez")
        self.assertIsNone(record["schedule"])
        self.assertEqual(record["district"], "SALAMANCA")


class CommittedSampleTests(unittest.TestCase):
    def test_committed_sample_matches_expected_schema(self):
        records = json.loads(SAMPLE_OUTPUT_PATH.read_text(encoding="utf-8"))
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], "madrid_parques_jardines")
            self.assertIsInstance(record["name"], str)
            self.assertIsInstance(record["location"]["lat"], float)
            self.assertIsInstance(record["location"]["lon"], float)


if __name__ == "__main__":
    unittest.main()
