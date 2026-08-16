import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.aparcamientos.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_RECORD = {
    "schema_version": 1,
    "source": "madrid_aparcamientos_rotacionales",
    "parking_id": "5",
    "name": "Nuestra Señora del Recuerdo",
    "address": "Calle de la Hiedra",
    "measured_at": "2026-08-15T12:23:55+02:00",
    "ingested_at": "2026-08-15T12:24:06.342708+02:00",
    "free_spaces": 333,
    "total_spaces": 832,
    "location": {"lat": 40.472181, "lon": -3.67916, "srid": "EPSG:4326"},
}

NO_OCCUPANCY_RECORD = {
    "schema_version": 1,
    "source": "madrid_aparcamientos_rotacionales",
    "parking_id": "20",
    "name": "Aparcamiento sin ocupacion en tiempo real",
    "address": "Calle sin dato",
    "measured_at": None,
    "ingested_at": "2026-08-15T12:24:06.342708+02:00",
    "free_spaces": None,
    "total_spaces": None,
    "location": {"lat": 40.42, "lon": -3.70, "srid": "EPSG:4326"},
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "aparcamientos_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_parking_id_is_rejected(self):
        record = {**VALID_RECORD, "parking_id": None}
        self.assertIn("parking_id_missing", validate_record(record))

    def test_missing_ingested_at_is_rejected(self):
        record = {**VALID_RECORD, "ingested_at": None}
        self.assertIn("ingested_at_missing_or_unparseable", validate_record(record))

    def test_naive_ingested_at_is_rejected(self):
        record = {**VALID_RECORD, "ingested_at": "2026-08-15T12:24:06.342708"}
        self.assertIn("ingested_at_not_timezone_aware", validate_record(record))

    def test_unparseable_measured_at_is_rejected(self):
        record = {**VALID_RECORD, "measured_at": "no es una fecha"}
        self.assertIn("measured_at_unparseable", validate_record(record))

    def test_naive_measured_at_is_rejected(self):
        record = {**VALID_RECORD, "measured_at": "2026-08-15T12:23:55"}
        self.assertIn("measured_at_not_timezone_aware", validate_record(record))

    def test_negative_free_spaces_is_rejected(self):
        record = {**VALID_RECORD, "free_spaces": -1}
        self.assertIn("free_spaces_negative", validate_record(record))

    def test_negative_total_spaces_is_rejected(self):
        record = {**VALID_RECORD, "total_spaces": -1}
        self.assertIn("total_spaces_negative", validate_record(record))

    def test_free_spaces_exceeding_total_spaces_is_rejected(self):
        record = {**VALID_RECORD, "free_spaces": 900, "total_spaces": 832}
        self.assertIn("free_spaces_exceeds_total_spaces", validate_record(record))

    def test_free_spaces_equal_to_total_spaces_is_accepted(self):
        record = {**VALID_RECORD, "free_spaces": 832, "total_spaces": 832}
        self.assertEqual(validate_record(record), [])

    def test_no_occupancy_record_is_accepted(self):
        # Decisión explícita del módulo: ocupación no compartida (measured_at/
        # free_spaces/total_spaces a None) no se descarta, ver transform.py.
        self.assertEqual(validate_record(NO_OCCUPANCY_RECORD), [])

    def test_missing_free_spaces_alone_skips_range_check(self):
        record = {**VALID_RECORD, "free_spaces": None}
        reasons = validate_record(record)
        self.assertNotIn("free_spaces_negative", reasons)
        self.assertNotIn("free_spaces_exceeds_total_spaces", reasons)

    def test_missing_total_spaces_alone_skips_range_check(self):
        record = {**VALID_RECORD, "total_spaces": None}
        reasons = validate_record(record)
        self.assertNotIn("total_spaces_negative", reasons)
        self.assertNotIn("free_spaces_exceeds_total_spaces", reasons)

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_RECORD, "parking_id": None, "free_spaces": -1}
        reasons = validate_record(record)
        self.assertIn("parking_id_missing", reasons)
        self.assertIn("free_spaces_negative", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_expected_fields(self):
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_RECORD, processed_at)

        self.assertEqual(silver["parking_id"], "5")
        self.assertEqual(silver["processed_at"], processed_at.isoformat())
        self.assertEqual(silver["location"]["lat"], 40.472181)
        self.assertEqual(silver["location"]["lon"], -3.67916)
        self.assertEqual(silver["free_spaces"], 333)
        self.assertEqual(silver["total_spaces"], 832)
        self.assertAlmostEqual(silver["occupancy_ratio"], 333 / 832)

    def test_no_occupancy_record_yields_null_numeric_fields(self):
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver = to_silver_record(NO_OCCUPANCY_RECORD, processed_at)

        self.assertEqual(silver["parking_id"], "20")
        self.assertIsNone(silver["measured_at"])
        self.assertIsNone(silver["free_spaces"])
        self.assertIsNone(silver["total_spaces"])
        self.assertIsNone(silver["occupancy_ratio"])

    def test_missing_total_spaces_yields_null_occupancy_ratio_not_division_error(self):
        record = {**VALID_RECORD, "total_spaces": None}
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver = to_silver_record(record, processed_at)

        self.assertIsNone(silver["occupancy_ratio"])

    def test_zero_total_spaces_yields_null_occupancy_ratio_not_division_error(self):
        record = {**VALID_RECORD, "total_spaces": 0}
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver = to_silver_record(record, processed_at)

        self.assertIsNone(silver["occupancy_ratio"])


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 5 aparcamientos reales con ocupación + 1 sin ocupación en tiempo
        # real (válido, ver decisión del módulo) = 6 válidos; 4 rechazados
        # (parking_id nulo, plazas libres negativas, plazas totales
        # negativas, libres por encima de totales).
        self.assertEqual(len(silver_records), 6)
        self.assertEqual(len(rejected), 4)

        silver_parking_ids = {r["parking_id"] for r in silver_records}
        self.assertEqual(silver_parking_ids, {"5", "7", "9", "12", "15", "20"})

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("parking_id_missing", rejection_reasons)
        self.assertIn("free_spaces_negative", rejection_reasons)
        self.assertIn("total_spaces_negative", rejection_reasons)
        self.assertIn("free_spaces_exceeds_total_spaces", rejection_reasons)

    def test_no_occupancy_silver_record_has_null_occupancy_ratio(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)

        record = next(r for r in silver_records if r["parking_id"] == "20")
        self.assertIsNone(record["measured_at"])
        self.assertIsNone(record["occupancy_ratio"])


if __name__ == "__main__":
    unittest.main()
