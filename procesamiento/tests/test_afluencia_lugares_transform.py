import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.afluencia_lugares.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_RECORD = {
    "schema_version": 1,
    "source": "google_populartimes",
    "place_id": "ChIJi7xhMz0nQg0RVeMHylTfhY4",
    "name": "Puerta del Sol",
    "query": "Puerta del Sol, Madrid",
    "address": "Puerta del Sol, 28013 Madrid, Spain",
    "location": {"lat": 40.4169473, "lon": -3.7035285, "srid": "EPSG:4326"},
    "captured_at": "2026-08-13T14:30:00+02:00",
    "live_pct": 72,
    "typical_by_hour": {
        "lunes": [0] * 24,
        "martes": [0] * 24,
        "miercoles": [0] * 24,
        "jueves": [0] * 24,
        "viernes": [0, 0, 0, 0, 0, 0, 6, 13, 26, 40, 50, 60, 66, 65, 58, 56, 60, 68, 75, 80, 70, 55, 35, 15],
        "sabado": [0] * 24,
        "domingo": [0] * 24,
    },
    "is_mock": True,
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "afluencia_lugares_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_place_id_is_rejected(self):
        record = {**VALID_RECORD, "place_id": None}
        self.assertIn("place_id_missing", validate_record(record))

    def test_missing_name_is_rejected(self):
        record = {**VALID_RECORD, "name": None}
        self.assertIn("name_missing", validate_record(record))

    def test_missing_captured_at_is_rejected(self):
        record = {**VALID_RECORD, "captured_at": None}
        self.assertIn("captured_at_missing_or_unparseable", validate_record(record))

    def test_unparseable_captured_at_is_rejected(self):
        record = {**VALID_RECORD, "captured_at": "no es una fecha"}
        self.assertIn("captured_at_missing_or_unparseable", validate_record(record))

    def test_naive_captured_at_is_rejected(self):
        record = {**VALID_RECORD, "captured_at": "2026-08-13T14:30:00"}
        self.assertIn("captured_at_not_timezone_aware", validate_record(record))

    def test_null_live_pct_is_accepted(self):
        # `live_pct=None` es un dato válido (lugar sin popularidad "en vivo"
        # disponible, o registro del handler de patrón típico), no un error.
        record = {**VALID_RECORD, "live_pct": None}
        self.assertEqual(validate_record(record), [])

    def test_live_pct_above_100_is_rejected(self):
        record = {**VALID_RECORD, "live_pct": 150}
        self.assertIn("live_pct_out_of_range", validate_record(record))

    def test_negative_live_pct_is_rejected(self):
        record = {**VALID_RECORD, "live_pct": -1}
        self.assertIn("live_pct_out_of_range", validate_record(record))

    def test_null_typical_by_hour_is_accepted(self):
        # `typical_by_hour=None` es un dato válido (lugar sin patrón
        # habitual suficiente en Google), no un error.
        record = {**VALID_RECORD, "typical_by_hour": None}
        self.assertEqual(validate_record(record), [])

    def test_both_live_pct_and_typical_by_hour_null_is_accepted(self):
        # Caso real de muestra: "Plaza Mayor".
        record = {**VALID_RECORD, "live_pct": None, "typical_by_hour": None}
        self.assertEqual(validate_record(record), [])

    def test_typical_by_hour_value_out_of_range_is_rejected(self):
        typical = {**VALID_RECORD["typical_by_hour"], "viernes": [0] * 23 + [250]}
        record = {**VALID_RECORD, "typical_by_hour": typical}
        self.assertIn("typical_by_hour_value_out_of_range", validate_record(record))

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_RECORD, "place_id": None, "live_pct": 999}
        reasons = validate_record(record)
        self.assertIn("place_id_missing", reasons)
        self.assertIn("live_pct_out_of_range", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_expected_fields(self):
        processed_at = datetime(2026, 8, 13, 15, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_RECORD, processed_at)

        self.assertEqual(silver["place_id"], "ChIJi7xhMz0nQg0RVeMHylTfhY4")
        self.assertEqual(silver["name"], "Puerta del Sol")
        self.assertEqual(silver["query"], "Puerta del Sol, Madrid")
        self.assertEqual(silver["lat"], 40.4169473)
        self.assertEqual(silver["lon"], -3.7035285)
        self.assertEqual(silver["live_pct"], 72)
        self.assertEqual(silver["typical_by_hour"], VALID_RECORD["typical_by_hour"])
        # `captured_at` se renombra a `ingested_at` -- mismo criterio que el
        # resto del patrón.
        self.assertEqual(silver["ingested_at"], "2026-08-13T14:30:00+02:00")
        self.assertEqual(silver["processed_at"], processed_at.isoformat())
        self.assertNotIn("is_mock", silver)
        self.assertNotIn("location", silver)

    def test_handles_null_live_pct_and_typical_by_hour(self):
        processed_at = datetime(2026, 8, 13, 15, 0, 0, tzinfo=timezone.utc)
        record = {**VALID_RECORD, "live_pct": None, "typical_by_hour": None}

        silver = to_silver_record(record, processed_at)

        self.assertIsNone(silver["live_pct"])
        self.assertIsNone(silver["typical_by_hour"])


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 13, 15, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 5 lugares reales de muestra (todos válidos, incluida Plaza Mayor
        # con live_pct/typical_by_hour ambos null) + 6 registros sintéticos
        # que violan cada regla de rechazo por turnos.
        self.assertEqual(len(silver_records), 5)
        self.assertEqual(len(rejected), 6)

        names = {r["name"] for r in silver_records}
        self.assertEqual(
            names,
            {"Puerta del Sol", "El Retiro Park", "Mercado de San Miguel", "Museo Nacional del Prado", "Plaza Mayor"},
        )

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("place_id_missing", rejection_reasons)
        self.assertIn("name_missing", rejection_reasons)
        self.assertIn("captured_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("captured_at_not_timezone_aware", rejection_reasons)
        self.assertIn("live_pct_out_of_range", rejection_reasons)
        self.assertIn("typical_by_hour_value_out_of_range", rejection_reasons)


if __name__ == "__main__":
    unittest.main()
