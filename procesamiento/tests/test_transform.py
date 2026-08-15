import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.trafico.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_RECORD = {
    "schema_version": 1,
    "source": "madrid_trafico_intensidad",
    "point_id": "1001",
    "measured_at": "2026-08-15T10:05:00+02:00",
    "ingested_at": "2026-08-15T10:06:12+02:00",
    "description": "Punto de control 1001",
    "access_code": "0101",
    "subarea": "Centro",
    "intensity_vph": 900,
    "occupancy_pct": 12,
    "load_pct": 20,
    "service_level": 0,
    "saturation_intensity_vph": 3100,
    "has_error": False,
    "error_code": "N",
    "location": {"x": 438339.375874991, "y": 4480454.96970565, "srid": "EPSG:25830"},
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "trafico_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_point_id_is_rejected(self):
        record = {**VALID_RECORD, "point_id": None}
        self.assertIn("point_id_missing", validate_record(record))

    def test_occupancy_out_of_range_is_rejected(self):
        record = {**VALID_RECORD, "occupancy_pct": 150}
        self.assertIn("occupancy_pct_out_of_range", validate_record(record))

    def test_load_out_of_range_is_rejected(self):
        record = {**VALID_RECORD, "load_pct": -5}
        self.assertIn("load_pct_out_of_range", validate_record(record))

    def test_negative_intensity_is_rejected(self):
        record = {**VALID_RECORD, "intensity_vph": -1}
        self.assertIn("intensity_vph_out_of_range", validate_record(record))

    def test_sensor_reporting_error_is_rejected(self):
        record = {**VALID_RECORD, "has_error": True, "error_code": "S"}
        self.assertIn("sensor_reports_error", validate_record(record))

    def test_missing_coordinates_are_rejected(self):
        record = {**VALID_RECORD, "location": {"x": None, "y": None, "srid": "EPSG:25830"}}
        self.assertIn("location_missing_or_outside_madrid_bbox", validate_record(record))

    def test_coordinates_outside_madrid_are_rejected(self):
        record = {**VALID_RECORD, "location": {"x": 0.0, "y": 0.0, "srid": "EPSG:25830"}}
        self.assertIn("location_missing_or_outside_madrid_bbox", validate_record(record))

    def test_unparseable_measured_at_is_rejected(self):
        record = {**VALID_RECORD, "measured_at": "no es una fecha"}
        self.assertIn("measured_at_missing_or_unparseable", validate_record(record))

    def test_naive_measured_at_is_rejected(self):
        record = {**VALID_RECORD, "measured_at": "2026-08-15T10:05:00"}
        self.assertIn("measured_at_not_timezone_aware", validate_record(record))

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_RECORD, "point_id": None, "occupancy_pct": 200}
        reasons = validate_record(record)
        self.assertIn("point_id_missing", reasons)
        self.assertIn("occupancy_pct_out_of_range", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_reprojects_and_normalizes(self):
        processed_at = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_RECORD, processed_at)

        self.assertEqual(silver["point_id"], "1001")
        self.assertEqual(silver["processed_at"], processed_at.isoformat())
        self.assertEqual(silver["location"]["srid_target"], "EPSG:4326")
        self.assertAlmostEqual(silver["location"]["lat"], 40.4725, places=3)
        self.assertAlmostEqual(silver["location"]["lon"], -3.7274, places=3)
        # occupancy_pct=12 -> occupancy_ratio=0.12
        self.assertAlmostEqual(silver["occupancy_ratio"], 0.12)
        # load_pct=20 -> load_ratio=0.20
        self.assertAlmostEqual(silver["load_ratio"], 0.20)
        # intensity_vph=900 / saturation_intensity_vph=3100
        self.assertAlmostEqual(silver["intensity_ratio"], 900 / 3100)
        # Los campos en bruto se conservan sin cambios.
        self.assertEqual(silver["intensity_vph"], 900)
        self.assertEqual(silver["occupancy_pct"], 12)

    def test_missing_saturation_intensity_yields_null_ratio(self):
        record = {**VALID_RECORD, "saturation_intensity_vph": None}
        processed_at = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(record, processed_at)

        self.assertIsNone(silver["intensity_ratio"])

    def test_zero_saturation_intensity_yields_null_ratio_not_division_error(self):
        record = {**VALID_RECORD, "saturation_intensity_vph": 0}
        processed_at = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(record, processed_at)

        self.assertIsNone(silver["intensity_ratio"])


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 5 registros válidos en el fixture (1001 x3, 1002 x2); 5 rechazados
        # (point_id nulo, ocupación fuera de rango, sensor con error, sin
        # coordenadas, coordenadas fuera de Madrid).
        self.assertEqual(len(silver_records), 5)
        self.assertEqual(len(rejected), 5)

        silver_point_ids = {r["point_id"] for r in silver_records}
        self.assertEqual(silver_point_ids, {"1001", "1002"})

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("point_id_missing", rejection_reasons)
        self.assertIn("occupancy_pct_out_of_range", rejection_reasons)
        self.assertIn("sensor_reports_error", rejection_reasons)
        self.assertIn("location_missing_or_outside_madrid_bbox", rejection_reasons)

    def test_every_silver_record_passes_its_own_validation(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

        silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)

        for record in silver_records:
            self.assertIsNotNone(record["location"]["lat"])
            self.assertIsNotNone(record["location"]["lon"])


if __name__ == "__main__":
    unittest.main()
