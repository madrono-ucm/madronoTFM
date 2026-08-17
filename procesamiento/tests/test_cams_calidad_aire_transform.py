import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.cams_calidad_aire.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_RECORD = {
    "schema_version": 1,
    "source": "cams",
    "pollutant": "NO2",
    "pollutant_code": "nitrogen_dioxide",
    "value": 11.34,
    "unit": "µg/m3",
    "valid_datetime": "2026-08-15T02:00:00+02:00",
    "forecast_issued_at": "2026-08-15T02:00:00+02:00",
    "leadtime_hour": 0,
    "model": "ensemble",
    "latitude": 40.45,
    "longitude": -3.75,
    "captured_at": "2026-08-16T02:21:09.151607+02:00",
    "is_mock": False,
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "cams_calidad_aire_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_pollutant_is_rejected(self):
        record = {**VALID_RECORD, "pollutant": None}
        self.assertIn("pollutant_missing", validate_record(record))

    def test_missing_pollutant_code_is_rejected(self):
        record = {**VALID_RECORD, "pollutant_code": None}
        self.assertIn("pollutant_code_missing", validate_record(record))

    def test_missing_valid_datetime_is_rejected(self):
        record = {**VALID_RECORD, "valid_datetime": None}
        self.assertIn("valid_datetime_missing_or_unparseable", validate_record(record))

    def test_unparseable_valid_datetime_is_rejected(self):
        record = {**VALID_RECORD, "valid_datetime": "no es una fecha"}
        self.assertIn("valid_datetime_missing_or_unparseable", validate_record(record))

    def test_naive_valid_datetime_is_rejected(self):
        record = {**VALID_RECORD, "valid_datetime": "2026-08-15T02:00:00"}
        self.assertIn("valid_datetime_not_timezone_aware", validate_record(record))

    def test_missing_forecast_issued_at_is_rejected(self):
        record = {**VALID_RECORD, "forecast_issued_at": None}
        self.assertIn("forecast_issued_at_missing_or_unparseable", validate_record(record))

    def test_naive_forecast_issued_at_is_rejected(self):
        record = {**VALID_RECORD, "forecast_issued_at": "2026-08-15T02:00:00"}
        self.assertIn("forecast_issued_at_not_timezone_aware", validate_record(record))

    def test_missing_leadtime_hour_is_rejected(self):
        record = {**VALID_RECORD, "leadtime_hour": None}
        self.assertIn("leadtime_hour_missing", validate_record(record))

    def test_negative_leadtime_hour_is_rejected(self):
        record = {**VALID_RECORD, "leadtime_hour": -1}
        self.assertIn("leadtime_hour_negative", validate_record(record))

    def test_missing_ingested_at_is_rejected(self):
        record = {**VALID_RECORD, "captured_at": None}
        self.assertIn("ingested_at_missing_or_unparseable", validate_record(record))

    def test_naive_ingested_at_is_rejected(self):
        record = {**VALID_RECORD, "captured_at": "2026-08-16T02:21:09.151607"}
        self.assertIn("ingested_at_not_timezone_aware", validate_record(record))

    def test_missing_value_is_rejected(self):
        record = {**VALID_RECORD, "value": None}
        self.assertIn("value_missing", validate_record(record))

    def test_negative_value_is_rejected(self):
        record = {**VALID_RECORD, "value": -1.0}
        self.assertIn("value_negative", validate_record(record))

    def test_value_far_above_plausible_range_for_its_pollutant_is_rejected(self):
        # NO2: PLAUSIBLE_MAX_BY_POLLUTANT["NO2"] == 500.
        record = {**VALID_RECORD, "value": 5000.0}
        self.assertIn("value_out_of_plausible_range", validate_record(record))

    def test_same_value_is_accepted_for_a_pollutant_with_a_higher_plausible_range(self):
        # PM10: PLAUSIBLE_MAX_BY_POLLUTANT["PM10"] == 1000, un valor de 600
        # (que rechazaríamos para NO2) es plausible para PM10 -- el rango es
        # por contaminante, no global.
        record = {
            **VALID_RECORD,
            "pollutant": "PM10",
            "pollutant_code": "particulate_matter_10um",
            "value": 600.0,
        }
        self.assertEqual(validate_record(record), [])

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_RECORD, "pollutant": None, "value": -1.0}
        reasons = validate_record(record)
        self.assertIn("pollutant_missing", reasons)
        self.assertIn("value_negative", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_expected_fields(self):
        processed_at = datetime(2026, 8, 16, 3, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_RECORD, processed_at)

        self.assertEqual(silver["pollutant"], "NO2")
        self.assertEqual(silver["pollutant_code"], "nitrogen_dioxide")
        self.assertEqual(silver["value"], 11.34)
        self.assertEqual(silver["unit"], "µg/m3")
        self.assertEqual(silver["valid_datetime"], "2026-08-15T02:00:00+02:00")
        self.assertEqual(silver["forecast_issued_at"], "2026-08-15T02:00:00+02:00")
        self.assertEqual(silver["leadtime_hour"], 0)
        self.assertEqual(silver["model"], "ensemble")
        self.assertEqual(silver["latitude"], 40.45)
        self.assertEqual(silver["longitude"], -3.75)
        # `captured_at` se renombra a `ingested_at` -- mismo criterio que el
        # resto del patrón.
        self.assertEqual(silver["ingested_at"], "2026-08-16T02:21:09.151607+02:00")
        self.assertEqual(silver["processed_at"], processed_at.isoformat())
        self.assertNotIn("is_mock", silver)


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 16, 3, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 16 registros reales de muestra (4 contaminantes x 4 leadtime_hour,
        # todos válidos) + 13 registros sintéticos, cada uno violando
        # exactamente una regla de rechazo.
        self.assertEqual(len(silver_records), 16)
        self.assertEqual(len(rejected), 13)

        pollutants = {r["pollutant"] for r in silver_records}
        self.assertEqual(pollutants, {"NO2", "O3", "PM10", "PM2.5"})

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("pollutant_missing", rejection_reasons)
        self.assertIn("pollutant_code_missing", rejection_reasons)
        self.assertIn("valid_datetime_missing_or_unparseable", rejection_reasons)
        self.assertIn("valid_datetime_not_timezone_aware", rejection_reasons)
        self.assertIn("forecast_issued_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("forecast_issued_at_not_timezone_aware", rejection_reasons)
        self.assertIn("leadtime_hour_missing", rejection_reasons)
        self.assertIn("leadtime_hour_negative", rejection_reasons)
        self.assertIn("ingested_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("ingested_at_not_timezone_aware", rejection_reasons)
        self.assertIn("value_missing", rejection_reasons)
        self.assertIn("value_negative", rejection_reasons)
        self.assertIn("value_out_of_plausible_range", rejection_reasons)


if __name__ == "__main__":
    unittest.main()
