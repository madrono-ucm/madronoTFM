"""Tests de la captura puntual de afluencia (popularidad) de lugares de Madrid.

No hacen ninguna llamada de red ni requieren `GOOGLE_MAPS_API_KEY`: usan
`fixtures/populartimes_get_id_sample.json` (una copia de la forma exacta que
devuelve `populartimes.get_id(...)`, verificada leyendo el código fuente de
la librería en `populartimes/crawler.py` durante la investigación de esta
tarea) y `fixtures/find_place_sample.json` (una copia de la forma de la
respuesta de la API oficial "Find Place from Text" de Google).

También verifica que la muestra commiteada en
`ingesta/capturas/samples/afluencia_lugares_madrid_sample.json` cumple el
esquema esperado.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.afluencia_lugares_madrid import (
    _pick_candidate,
    _typical_by_hour,
    normalize_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLES_DIR = Path(__file__).parent.parent / "capturas" / "samples"

POPULARTIMES_FIXTURE = json.loads((FIXTURES_DIR / "populartimes_get_id_sample.json").read_text())
FIND_PLACE_FIXTURE = json.loads((FIXTURES_DIR / "find_place_sample.json").read_text())

CAPTURED_AT = datetime(2026, 8, 13, 10, 0, 0, tzinfo=timezone.utc)


class TypicalByHourTests(unittest.TestCase):
    def test_normalizes_days_to_spanish_keys_with_24_values(self):
        raw = POPULARTIMES_FIXTURE["with_data"]["populartimes"]
        result = _typical_by_hour(raw)

        self.assertEqual(
            set(result.keys()),
            {"lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"},
        )
        for values in result.values():
            self.assertEqual(len(values), 24)
            self.assertTrue(all(0 <= v <= 100 for v in values))
        self.assertEqual(result["viernes"][20], 70)

    def test_missing_populartimes_returns_none(self):
        self.assertIsNone(_typical_by_hour(None))
        self.assertIsNone(_typical_by_hour([]))


class PickCandidateTests(unittest.TestCase):
    def test_returns_first_candidate_on_success(self):
        candidate = _pick_candidate(FIND_PLACE_FIXTURE["found"], "Puerta del Sol, Madrid")
        self.assertEqual(candidate["place_id"], "ChIJi7xhMz0nQg0RVeMHylTfhY4")

    def test_returns_none_on_zero_results(self):
        candidate = _pick_candidate(FIND_PLACE_FIXTURE["not_found"], "lugar inexistente xyz")
        self.assertIsNone(candidate)


class NormalizeRecordTests(unittest.TestCase):
    def test_normalizes_place_with_live_and_typical_data(self):
        raw = POPULARTIMES_FIXTURE["with_data"]
        record = normalize_record(raw, "Puerta del Sol, Madrid", CAPTURED_AT)

        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "google_populartimes")
        self.assertEqual(record["place_id"], "ChIJi7xhMz0nQg0RVeMHylTfhY4")
        self.assertEqual(record["name"], "Puerta del Sol")
        self.assertEqual(record["query"], "Puerta del Sol, Madrid")
        self.assertEqual(record["live_pct"], 63)
        self.assertEqual(record["captured_at"], "2026-08-13T10:00:00+00:00")
        self.assertAlmostEqual(record["location"]["lat"], 40.4169473)
        self.assertAlmostEqual(record["location"]["lon"], -3.7035285)
        self.assertEqual(record["location"]["srid"], "EPSG:4326")
        self.assertIsNotNone(record["typical_by_hour"])
        self.assertEqual(len(record["typical_by_hour"]["lunes"]), 24)
        self.assertFalse(record["is_mock"])

    def test_normalizes_place_without_live_or_typical_data(self):
        raw = POPULARTIMES_FIXTURE["without_data"]
        record = normalize_record(raw, "Quinta de los Molinos, Madrid", CAPTURED_AT)

        self.assertIsNone(record["live_pct"])
        self.assertIsNone(record["typical_by_hour"])
        self.assertEqual(record["name"], "Quinta de los Molinos")

    def test_is_mock_flag_is_passed_through(self):
        raw = POPULARTIMES_FIXTURE["with_data"]
        record = normalize_record(raw, "Puerta del Sol, Madrid", CAPTURED_AT, is_mock=True)
        self.assertTrue(record["is_mock"])


class CommittedSampleTests(unittest.TestCase):
    EXPECTED_KEYS = {
        "schema_version",
        "source",
        "place_id",
        "name",
        "query",
        "address",
        "location",
        "captured_at",
        "live_pct",
        "typical_by_hour",
        "is_mock",
    }

    def test_sample_matches_schema(self):
        records = json.loads((SAMPLES_DIR / "afluencia_lugares_madrid_sample.json").read_text())
        self.assertGreaterEqual(len(records), 3)
        self.assertLessEqual(len(records), 5)
        for record in records:
            self.assertEqual(set(record.keys()), self.EXPECTED_KEYS)
            self.assertTrue(record["place_id"])
            self.assertTrue(record["name"])
            self.assertIn("lat", record["location"])
            self.assertIn("lon", record["location"])
            if record["typical_by_hour"] is not None:
                self.assertEqual(
                    set(record["typical_by_hour"].keys()),
                    {"lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"},
                )
                for values in record["typical_by_hour"].values():
                    self.assertEqual(len(values), 24)

    def test_sample_is_marked_as_mock(self):
        # Ver docstring del módulo: no hay GOOGLE_MAPS_API_KEY configurada en
        # este entorno, así que la muestra commiteada es de ejemplo, no una
        # captura real.
        records = json.loads((SAMPLES_DIR / "afluencia_lugares_madrid_sample.json").read_text())
        self.assertTrue(all(record["is_mock"] for record in records))


if __name__ == "__main__":
    unittest.main()
