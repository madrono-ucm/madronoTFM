import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.ruido.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_RECORD = {
    "schema_version": 1,
    "source": "madrid_ruido_diario",
    "station_id": "RF-01",
    "station_name": "Paseo de Recoletos",
    "station_address": "Frente al n23 del Paseo de Recoletos",
    "district": "Centro",
    "neighbourhood": "Justicia",
    "period": "D",
    "period_name": "diurno",
    "measured_date": "2026-08-13",
    "ingested_at": "2026-08-15T12:32:21.270994+02:00",
    "laeq_db": 62.6,
    "l1_db": 69.4,
    "l10_db": 65.9,
    "l50_db": 60.4,
    "l90_db": 54.8,
    "l99_db": 52.2,
    "location": {"lat": 40.422599, "lon": -3.691877, "srid": "EPSG:4326", "altitude_m": 648},
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "ruido_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_station_id_is_rejected(self):
        record = {**VALID_RECORD, "station_id": None}
        self.assertIn("station_id_missing", validate_record(record))

    def test_missing_period_is_rejected(self):
        record = {**VALID_RECORD, "period": None}
        self.assertIn("period_missing", validate_record(record))

    def test_missing_measured_date_is_rejected(self):
        record = {**VALID_RECORD, "measured_date": None}
        self.assertIn("measured_date_missing_or_unparseable", validate_record(record))

    def test_unparseable_measured_date_is_rejected(self):
        record = {**VALID_RECORD, "measured_date": "no es una fecha"}
        self.assertIn("measured_date_missing_or_unparseable", validate_record(record))

    def test_missing_ingested_at_is_rejected(self):
        record = {**VALID_RECORD, "ingested_at": None}
        self.assertIn("ingested_at_missing_or_unparseable", validate_record(record))

    def test_naive_ingested_at_is_rejected(self):
        record = {**VALID_RECORD, "ingested_at": "2026-08-15T12:32:14.667483"}
        self.assertIn("ingested_at_not_timezone_aware", validate_record(record))

    def test_missing_laeq_is_rejected(self):
        record = {**VALID_RECORD, "laeq_db": None}
        self.assertIn("laeq_missing", validate_record(record))

    def test_laeq_above_plausible_range_is_rejected(self):
        record = {**VALID_RECORD, "laeq_db": 150.0}
        self.assertIn("laeq_db_out_of_plausible_range", validate_record(record))

    def test_laeq_below_plausible_range_is_rejected(self):
        record = {**VALID_RECORD, "laeq_db": 5.0}
        self.assertIn("laeq_db_out_of_plausible_range", validate_record(record))

    def test_percentile_out_of_plausible_range_is_rejected_without_rejecting_laeq(self):
        record = {**VALID_RECORD, "l90_db": 5.0}
        reasons = validate_record(record)
        self.assertIn("l90_db_out_of_plausible_range", reasons)
        self.assertNotIn("laeq_db_out_of_plausible_range", reasons)

    def test_missing_percentile_is_accepted(self):
        record = {**VALID_RECORD, "l1_db": None, "l99_db": None}
        self.assertEqual(validate_record(record), [])

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_RECORD, "station_id": None, "laeq_db": None}
        reasons = validate_record(record)
        self.assertIn("station_id_missing", reasons)
        self.assertIn("laeq_missing", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_expected_fields(self):
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_RECORD, processed_at)

        self.assertEqual(silver["station_id"], "RF-01")
        self.assertEqual(silver["period"], "D")
        self.assertEqual(silver["period_name"], "diurno")
        self.assertEqual(silver["measured_date"], "2026-08-13")
        self.assertEqual(silver["laeq_db"], 62.6)
        self.assertEqual(silver["l90_db"], 54.8)
        self.assertEqual(silver["processed_at"], processed_at.isoformat())
        self.assertEqual(silver["location"]["lat"], 40.422599)
        self.assertEqual(silver["location"]["altitude_m"], 648)


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 20 lecturas reales (5 estaciones x periodos D/E/N/T) validas, 8
        # registros invalidos anadidos al fixture (uno por motivo de
        # rechazo), ver procesamiento/tests/fixtures/ruido_bronze_sample.json.
        self.assertEqual(len(silver_records), 20)
        self.assertEqual(len(rejected), 8)

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("station_id_missing", rejection_reasons)
        self.assertIn("period_missing", rejection_reasons)
        self.assertIn("measured_date_missing_or_unparseable", rejection_reasons)
        self.assertIn("ingested_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("ingested_at_not_timezone_aware", rejection_reasons)
        self.assertIn("laeq_missing", rejection_reasons)
        self.assertIn("laeq_db_out_of_plausible_range", rejection_reasons)
        self.assertIn("l90_db_out_of_plausible_range", rejection_reasons)


if __name__ == "__main__":
    unittest.main()
