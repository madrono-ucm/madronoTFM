"""Tests del productor de calles y plazas del Servicio de Estacionamiento
Regulado (SER) de Madrid.

No hacen ninguna llamada de red: usan `fixtures/ser_calles_sample.csv`
(copia real y reducida de 3 filas del recurso 2026 real, más una fila
sintética sin coordenadas para el caso de filtrado, ver
`ingesta/capturas/ser_calles_madrid.py`) y
`fixtures/ser_calles_package_show_sample.json` (copia real y reducida de la
respuesta de `package_show`, con recursos de varios años para verificar la
resolución del más reciente por fecha real, no por sufijo de `id`).
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.ser_calles_madrid import (
    normalize_record,
    resolve_latest_csv_url,
    select_sample_calles,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CSV_PATH = FIXTURES_DIR / "ser_calles_sample.csv"
PACKAGE_SHOW_PATH = FIXTURES_DIR / "ser_calles_package_show_sample.json"
SAMPLE_OUTPUT_PATH = Path(__file__).parent.parent / "capturas" / "samples" / "ser_calles_madrid_sample.json"


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        pass


class ResolveLatestCsvUrlTests(unittest.TestCase):
    def test_picks_resource_by_real_date_not_id_suffix(self):
        # El fixture incluye 218228-26-ser-calles-csv (id alto, en realidad
        # de 2021) y 218228-1-ser-calles-csv (id bajo, en realidad de 2026,
        # last_modified más reciente) -- verifica que gana el segundo.
        payload = PACKAGE_SHOW_PATH.read_bytes()

        class FakeConfig:
            catalog_api_url = "https://example.invalid/package_show"
            timeout_seconds = 5.0
            max_retries = 1
            retry_backoff_seconds = 0.0

        import ingesta.capturas.ser_calles_madrid as mod

        original = mod._fetch_with_retries
        mod._fetch_with_retries = lambda config, url: payload
        try:
            url = resolve_latest_csv_url(FakeConfig())
        finally:
            mod._fetch_with_retries = original

        self.assertIn("218228-1-ser-calles-csv", url)


class SelectSampleCallesTests(unittest.TestCase):
    def test_skips_rows_without_coordinates(self):
        csv_text = CSV_PATH.read_text(encoding="latin-1")
        selected = select_sample_calles(csv_text, sample_size=10)
        # 3 filas reales con coordenadas + 1 fila sintética sin ellas (se descarta).
        self.assertEqual(len(selected), 3)
        self.assertTrue(all(row["gis_x"].strip() for row in selected))


class NormalizeRecordTests(unittest.TestCase):
    def setUp(self):
        csv_text = CSV_PATH.read_text(encoding="latin-1")
        self.rows = select_sample_calles(csv_text, sample_size=10)
        self.ingested_at = datetime(2026, 8, 25, 21, 52, 19, tzinfo=timezone.utc)

    def test_recovers_corrupted_gis_coordinates(self):
        record = normalize_record(self.rows[0], self.ingested_at)

        self.assertEqual(record["district"], "Retiro")
        self.assertEqual(record["neighbourhood"], "Adelfas")
        self.assertEqual(record["street"], "CERRO DE LA PLATA, CALLE, DEL")
        self.assertAlmostEqual(record["location"]["x"], 442724.91, places=2)
        self.assertAlmostEqual(record["location"]["y"], 4472388.99, places=2)
        self.assertEqual(record["location"]["srid"], "EPSG:25830")

    def test_splits_zone_color_rgb_prefix_from_name(self):
        record = normalize_record(self.rows[0], self.ingested_at)
        self.assertEqual(record["zone_color"], "Azul")
        self.assertEqual(record["zone_rgb"], "043000255")

    def test_num_spaces_is_int(self):
        record = normalize_record(self.rows[0], self.ingested_at)
        self.assertEqual(record["num_spaces"], 4)
        self.assertIsInstance(record["num_spaces"], int)


class CommittedSampleTests(unittest.TestCase):
    def test_committed_sample_matches_expected_schema(self):
        records = json.loads(SAMPLE_OUTPUT_PATH.read_text(encoding="utf-8"))
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], "madrid_ser_calles")
            self.assertIsInstance(record["location"]["x"], float)
            self.assertIsInstance(record["location"]["y"], float)
            # UTM 30N plausible para Madrid: easting ~430k-450k, northing ~4.46M-4.49M.
            self.assertTrue(400000 < record["location"]["x"] < 470000)
            self.assertTrue(4450000 < record["location"]["y"] < 4500000)


if __name__ == "__main__":
    unittest.main()
