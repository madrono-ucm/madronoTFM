import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.aforos_peatones_bicicletas.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_PEDESTRIAN_RECORD = {
    "schema_version": 1,
    "source": "madrid_aforos_peatones_bicicletas",
    "station_id": "PERM_PEA01_PM01",
    "mode": "peatones",
    "measured_at": "2024-06-30T00:00:00+02:00",
    "ingested_at": "2026-08-15T19:43:36.003565+02:00",
    "pedestrian_count": 857,
    "bicycle_count": None,
    "district_code": "1",
    "district": "Centro",
    "address": "Calle Arenal esquina San Martín",
    "address_notes": "Calle peatonal",
    "location": {"lat": 40.417386, "lon": -3.707141, "srid": "EPSG:4326"},
}

VALID_BICYCLE_RECORD = {
    "schema_version": 1,
    "source": "madrid_aforos_peatones_bicicletas",
    "station_id": "PERM_BICI01_PM01",
    "mode": "bicicletas",
    "measured_at": "2024-06-30T00:00:00+02:00",
    "ingested_at": "2026-08-15T19:43:36.003565+02:00",
    "pedestrian_count": None,
    "bicycle_count": 16,
    "district_code": "2",
    "district": "Arganzuela",
    "address": "Calle Toledo  133, 28005 Madrid",
    "address_notes": "Sentido Gta. Pirámides",
    "location": {"lat": 40.405472, "lon": -3.711961, "srid": "EPSG:4326"},
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "aforos_peatones_bicicletas_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_pedestrian_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_PEDESTRIAN_RECORD), [])

    def test_valid_bicycle_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_BICYCLE_RECORD), [])

    def test_missing_station_id_is_rejected(self):
        record = {**VALID_PEDESTRIAN_RECORD, "station_id": None}
        self.assertIn("station_id_missing", validate_record(record))

    def test_missing_mode_is_rejected(self):
        record = {**VALID_PEDESTRIAN_RECORD, "mode": None}
        self.assertIn("mode_missing_or_invalid", validate_record(record))

    def test_unknown_mode_is_rejected(self):
        record = {**VALID_PEDESTRIAN_RECORD, "mode": "coches"}
        self.assertIn("mode_missing_or_invalid", validate_record(record))

    def test_missing_measured_at_is_rejected(self):
        record = {**VALID_PEDESTRIAN_RECORD, "measured_at": None}
        self.assertIn("measured_at_missing_or_unparseable", validate_record(record))

    def test_unparseable_measured_at_is_rejected(self):
        record = {**VALID_PEDESTRIAN_RECORD, "measured_at": "no es una fecha"}
        self.assertIn("measured_at_missing_or_unparseable", validate_record(record))

    def test_naive_measured_at_is_rejected(self):
        record = {**VALID_PEDESTRIAN_RECORD, "measured_at": "2024-06-30T00:00:00"}
        self.assertIn("measured_at_not_timezone_aware", validate_record(record))

    def test_missing_ingested_at_is_rejected(self):
        record = {**VALID_PEDESTRIAN_RECORD, "ingested_at": None}
        self.assertIn("ingested_at_missing_or_unparseable", validate_record(record))

    def test_naive_ingested_at_is_rejected(self):
        record = {**VALID_PEDESTRIAN_RECORD, "ingested_at": "2026-08-15T19:43:36.003565"}
        self.assertIn("ingested_at_not_timezone_aware", validate_record(record))

    def test_missing_pedestrian_count_is_rejected_for_pedestrian_mode(self):
        record = {**VALID_PEDESTRIAN_RECORD, "pedestrian_count": None}
        self.assertIn("count_missing", validate_record(record))

    def test_missing_bicycle_count_is_rejected_for_bicycle_mode(self):
        record = {**VALID_BICYCLE_RECORD, "bicycle_count": None}
        self.assertIn("count_missing", validate_record(record))

    def test_negative_count_is_rejected(self):
        record = {**VALID_BICYCLE_RECORD, "bicycle_count": -3}
        self.assertIn("count_negative", validate_record(record))

    def test_zero_count_is_accepted(self):
        # Un conteo de 0 es un dato real y válido (una estación sin ningún
        # peatón/bicicleta en esa hora), no debe rechazarse.
        record = {**VALID_BICYCLE_RECORD, "bicycle_count": 0}
        self.assertEqual(validate_record(record), [])

    def test_pedestrian_count_present_does_not_rescue_bicycle_mode_without_bicycle_count(self):
        # El campo de conteo que cuenta es el de `mode`, no cualquiera de
        # los dos: un registro de bicicletas con pedestrian_count relleno
        # pero bicycle_count nulo sigue rechazándose.
        record = {**VALID_BICYCLE_RECORD, "pedestrian_count": 857, "bicycle_count": None}
        self.assertIn("count_missing", validate_record(record))

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_PEDESTRIAN_RECORD, "station_id": None, "pedestrian_count": -1}
        reasons = validate_record(record)
        self.assertIn("station_id_missing", reasons)
        self.assertIn("count_negative", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_pedestrian_record(self):
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_PEDESTRIAN_RECORD, processed_at)

        self.assertEqual(silver["station_id"], "PERM_PEA01_PM01")
        self.assertEqual(silver["mode"], "peatones")
        self.assertEqual(silver["count"], 857)
        self.assertEqual(silver["district"], "Centro")
        self.assertEqual(silver["processed_at"], processed_at.isoformat())
        self.assertEqual(silver["location"]["lat"], 40.417386)
        self.assertEqual(silver["location"]["lon"], -3.707141)

    def test_normalizes_bicycle_record(self):
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_BICYCLE_RECORD, processed_at)

        self.assertEqual(silver["station_id"], "PERM_BICI01_PM01")
        self.assertEqual(silver["mode"], "bicicletas")
        self.assertEqual(silver["count"], 16)


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 5 registros reales válidos (3 peatones + 2 bicicletas) + 8 que
        # violan cada regla de rechazo por turnos, ver el fixture.
        self.assertEqual(len(silver_records), 5)
        self.assertEqual(len(rejected), 8)

        modes = {r["mode"] for r in silver_records}
        self.assertEqual(modes, {"peatones", "bicicletas"})

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("station_id_missing", rejection_reasons)
        self.assertIn("mode_missing_or_invalid", rejection_reasons)
        self.assertIn("measured_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("measured_at_not_timezone_aware", rejection_reasons)
        self.assertIn("ingested_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("ingested_at_not_timezone_aware", rejection_reasons)
        self.assertIn("count_missing", rejection_reasons)
        self.assertIn("count_negative", rejection_reasons)


if __name__ == "__main__":
    unittest.main()
