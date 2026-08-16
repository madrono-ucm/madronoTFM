import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.bicimad.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_RECORD = {
    "schema_version": 1,
    "source": "bicimad_gbfs",
    "station_id": "1406",
    "name": "2 - Metro Callao",
    "address": "Calle Miguel Moya nº 1",
    "measured_at": "2026-08-15T12:23:30+02:00",
    "ingested_at": "2026-08-15T12:24:00.526219+02:00",
    "bikes_available": 1,
    "bikes_disabled": 5,
    "docks_available": 21,
    "docks_disabled": 0,
    "docks_total": 47,
    "status": "IN_SERVICE",
    "is_renting": True,
    "is_returning": True,
    "is_installed": True,
    "location": {"lat": 40.4204, "lon": -3.70569, "srid": "EPSG:4326"},
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "bicimad_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_station_id_is_rejected(self):
        record = {**VALID_RECORD, "station_id": None}
        self.assertIn("station_id_missing", validate_record(record))

    def test_unparseable_measured_at_is_rejected(self):
        record = {**VALID_RECORD, "measured_at": "no es una fecha"}
        self.assertIn("measured_at_missing_or_unparseable", validate_record(record))

    def test_missing_measured_at_is_rejected(self):
        record = {**VALID_RECORD, "measured_at": None}
        self.assertIn("measured_at_missing_or_unparseable", validate_record(record))

    def test_naive_measured_at_is_rejected(self):
        record = {**VALID_RECORD, "measured_at": "2026-08-15T12:23:30"}
        self.assertIn("measured_at_not_timezone_aware", validate_record(record))

    def test_naive_ingested_at_is_rejected(self):
        record = {**VALID_RECORD, "ingested_at": "2026-08-15T12:24:00"}
        self.assertIn("ingested_at_not_timezone_aware", validate_record(record))

    def test_uninstalled_station_is_rejected(self):
        record = {**VALID_RECORD, "is_installed": False}
        self.assertIn("station_not_installed", validate_record(record))

    def test_negative_counter_is_rejected(self):
        record = {**VALID_RECORD, "bikes_disabled": -1}
        self.assertIn("bikes_disabled_negative", validate_record(record))

    def test_bikes_over_capacity_is_rejected(self):
        record = {**VALID_RECORD, "bikes_available": 40, "bikes_disabled": 10, "docks_total": 47}
        self.assertIn("bikes_exceed_docks_total", validate_record(record))

    def test_docks_over_capacity_is_rejected(self):
        record = {**VALID_RECORD, "docks_available": 40, "docks_disabled": 10, "docks_total": 47}
        self.assertIn("docks_exceed_docks_total", validate_record(record))

    def test_counters_within_capacity_with_slack_are_accepted(self):
        # 1 + 5 = 6 <= 47: por debajo de la capacidad total, aceptado (ver
        # docstring del módulo: la suma real no tiene por qué agotar la
        # capacidad, hay bicis fuera de la red en cada instante).
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_docks_total_skips_consistency_checks(self):
        record = {**VALID_RECORD, "docks_total": None}
        reasons = validate_record(record)
        self.assertNotIn("bikes_exceed_docks_total", reasons)
        self.assertNotIn("docks_exceed_docks_total", reasons)

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_RECORD, "station_id": None, "is_installed": False}
        reasons = validate_record(record)
        self.assertIn("station_id_missing", reasons)
        self.assertIn("station_not_installed", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_expected_fields(self):
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_RECORD, processed_at)

        self.assertEqual(silver["station_id"], "1406")
        self.assertEqual(silver["processed_at"], processed_at.isoformat())
        self.assertEqual(silver["location"]["lat"], 40.4204)
        self.assertEqual(silver["location"]["lon"], -3.70569)
        self.assertEqual(silver["bikes_available"], 1)
        self.assertEqual(silver["docks_total"], 47)
        # bikes_available=1 / docks_total=47
        self.assertAlmostEqual(silver["occupancy_ratio"], 1 / 47)

    def test_missing_docks_total_yields_null_occupancy_ratio(self):
        record = {**VALID_RECORD, "docks_total": None}
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver = to_silver_record(record, processed_at)

        self.assertIsNone(silver["occupancy_ratio"])

    def test_zero_docks_total_yields_null_occupancy_ratio_not_division_error(self):
        record = {**VALID_RECORD, "docks_total": 0}
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver = to_silver_record(record, processed_at)

        self.assertIsNone(silver["occupancy_ratio"])


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 5 estaciones reales válidas (1406-1410); 5 rechazadas (station_id
        # nulo, measured_at nulo, estación desinstalada, contador negativo,
        # bicis por encima de la capacidad).
        self.assertEqual(len(silver_records), 5)
        self.assertEqual(len(rejected), 5)

        silver_station_ids = {r["station_id"] for r in silver_records}
        self.assertEqual(silver_station_ids, {"1406", "1407", "1408", "1409", "1410"})

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("station_id_missing", rejection_reasons)
        self.assertIn("measured_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("station_not_installed", rejection_reasons)
        self.assertIn("bikes_disabled_negative", rejection_reasons)
        self.assertIn("bikes_exceed_docks_total", rejection_reasons)

    def test_every_silver_record_has_a_valid_occupancy_ratio(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)

        for record in silver_records:
            self.assertIsNotNone(record["occupancy_ratio"])
            self.assertGreaterEqual(record["occupancy_ratio"], 0)


if __name__ == "__main__":
    unittest.main()
