import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.calidad_aire.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_RECORD = {
    "schema_version": 1,
    "source": "madrid_calidad_aire",
    "station_id": "28079011",
    "station_name": "Ramón y Cajal",
    "station_address": "Avda. Ramón y Cajal  esq. C/ Príncipe de Vergara",
    "magnitude_code": "08",
    "magnitude_abbr": "NO2",
    "magnitude_name": "Dióxido de Nitrógeno",
    "unit": "µg/m³",
    "value": 25.0,
    "measured_at": "2026-08-15T12:00:00+02:00",
    "ingested_at": "2026-08-15T12:32:14.667483+02:00",
    "location": {"lat": 40.4514734, "lon": -3.6773491, "srid": "EPSG:4326"},
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "calidad_aire_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_station_id_is_rejected(self):
        record = {**VALID_RECORD, "station_id": None}
        self.assertIn("station_id_missing", validate_record(record))

    def test_missing_pollutant_is_rejected(self):
        record = {**VALID_RECORD, "magnitude_abbr": None}
        self.assertIn("pollutant_missing", validate_record(record))

    def test_missing_measured_at_is_rejected(self):
        record = {**VALID_RECORD, "measured_at": None}
        self.assertIn("measured_at_missing_or_unparseable", validate_record(record))

    def test_unparseable_measured_at_is_rejected(self):
        record = {**VALID_RECORD, "measured_at": "no es una fecha"}
        self.assertIn("measured_at_missing_or_unparseable", validate_record(record))

    def test_naive_measured_at_is_rejected(self):
        record = {**VALID_RECORD, "measured_at": "2026-08-15T12:00:00"}
        self.assertIn("measured_at_not_timezone_aware", validate_record(record))

    def test_missing_ingested_at_is_rejected(self):
        record = {**VALID_RECORD, "ingested_at": None}
        self.assertIn("ingested_at_missing_or_unparseable", validate_record(record))

    def test_naive_ingested_at_is_rejected(self):
        record = {**VALID_RECORD, "ingested_at": "2026-08-15T12:32:14.667483"}
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
            "magnitude_code": "10",
            "magnitude_abbr": "PM10",
            "magnitude_name": "Partículas < 10 µm",
            "value": 600.0,
        }
        self.assertEqual(validate_record(record), [])

    def test_unknown_pollutant_skips_range_check_but_not_negativity(self):
        record = {**VALID_RECORD, "magnitude_abbr": "XYZ", "value": 999999.0}
        self.assertEqual(validate_record(record), [])

        record = {**VALID_RECORD, "magnitude_abbr": "XYZ", "value": -5.0}
        self.assertIn("value_negative", validate_record(record))

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_RECORD, "station_id": None, "value": -1.0}
        reasons = validate_record(record)
        self.assertIn("station_id_missing", reasons)
        self.assertIn("value_negative", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_expected_fields(self):
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_RECORD, processed_at)

        self.assertEqual(silver["station_id"], "28079011")
        self.assertEqual(silver["pollutant"], "NO2")
        self.assertEqual(silver["pollutant_name"], "Dióxido de Nitrógeno")
        self.assertEqual(silver["unit"], "µg/m³")
        self.assertEqual(silver["value"], 25.0)
        self.assertEqual(silver["processed_at"], processed_at.isoformat())
        self.assertEqual(silver["location"]["lat"], 40.4514734)
        self.assertEqual(silver["location"]["lon"], -3.6773491)


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 5 lecturas reales (2 estaciones x NOx/NO/NO2/NOx/O3) = 5 válidas;
        # 4 rechazadas (station_id nulo, contaminante nulo, measured_at
        # corrupto, value nulo, value de NO2 disparado) -- son 5 motivos de
        # rechazo distintos sobre 5 registros, ver el fixture.
        self.assertEqual(len(silver_records), 5)
        self.assertEqual(len(rejected), 5)

        pollutants = {r["pollutant"] for r in silver_records}
        self.assertIn("NOx", pollutants)
        self.assertIn("NO", pollutants)
        self.assertIn("NO2", pollutants)
        self.assertIn("O3", pollutants)

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("station_id_missing", rejection_reasons)
        self.assertIn("pollutant_missing", rejection_reasons)
        self.assertIn("measured_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("value_missing", rejection_reasons)
        self.assertIn("value_out_of_plausible_range", rejection_reasons)


if __name__ == "__main__":
    unittest.main()
