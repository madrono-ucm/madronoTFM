import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.transporte_publico_emt.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_RECORD = {
    "schema_version": 1,
    "source": "madrid_emt_llegadas",
    "stop_id": "71",
    "line": "203",
    "bus_id": 5138,
    "destination": "AEROPUERTO",
    "ingested_at": "2026-08-15T10:05:00+02:00",
    "estimate_arrive_sec": 300,
    "distance_bus_m": 1200,
    "is_head": False,
    "deviation_sec": 0,
    "position_type_bus": "0",
    "location": {"lon": -3.6895817064857424, "lat": 40.40654799269596, "srid": "EPSG:4326"},
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "transporte_publico_emt_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_stop_id_is_rejected(self):
        record = {**VALID_RECORD, "stop_id": None}
        self.assertIn("stop_id_missing", validate_record(record))

    def test_missing_line_is_rejected(self):
        record = {**VALID_RECORD, "line": None}
        self.assertIn("line_missing", validate_record(record))

    def test_unparseable_ingested_at_is_rejected(self):
        record = {**VALID_RECORD, "ingested_at": "no es una fecha"}
        self.assertIn("ingested_at_missing_or_unparseable", validate_record(record))

    def test_naive_ingested_at_is_rejected(self):
        record = {**VALID_RECORD, "ingested_at": "2026-08-15T10:05:00"}
        self.assertIn("ingested_at_not_timezone_aware", validate_record(record))

    def test_excessive_wait_estimate_is_rejected(self):
        record = {**VALID_RECORD, "estimate_arrive_sec": 999999}
        self.assertIn("estimate_arrive_sec_out_of_range", validate_record(record))

    def test_negative_wait_estimate_is_rejected(self):
        record = {**VALID_RECORD, "estimate_arrive_sec": -1}
        self.assertIn("estimate_arrive_sec_out_of_range", validate_record(record))

    def test_negative_distance_is_rejected(self):
        record = {**VALID_RECORD, "distance_bus_m": -50}
        self.assertIn("distance_bus_m_negative", validate_record(record))

    def test_leaked_auth_payload_is_rejected(self):
        record = {**VALID_RECORD, "accessToken": "LEAKED-TOKEN-SHOULD-NOT-APPEAR"}
        self.assertIn("unexpected_auth_error_payload", validate_record(record))

    def test_missing_optional_fields_are_accepted(self):
        record = {
            **VALID_RECORD,
            "bus_id": None,
            "destination": None,
            "distance_bus_m": None,
            "estimate_arrive_sec": None,
        }
        self.assertEqual(validate_record(record), [])

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_RECORD, "stop_id": None, "line": None}
        reasons = validate_record(record)
        self.assertIn("stop_id_missing", reasons)
        self.assertIn("line_missing", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_a_valid_record(self):
        processed_at = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_RECORD, processed_at)

        self.assertEqual(silver["stop_id"], "71")
        self.assertEqual(silver["line"], "203")
        self.assertEqual(silver["processed_at"], processed_at.isoformat())
        self.assertEqual(silver["estimate_arrive_sec"], 300)
        self.assertEqual(silver["distance_bus_m"], 1200)
        self.assertAlmostEqual(silver["location"]["lat"], 40.40654799269596)
        self.assertAlmostEqual(silver["location"]["lon"], -3.6895817064857424)
        self.assertEqual(silver["location"]["srid"], "EPSG:4326")

    def test_missing_location_yields_null_lat_lon(self):
        record = {**VALID_RECORD, "location": {"lon": None, "lat": None, "srid": "EPSG:4326"}}
        processed_at = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(record, processed_at)

        self.assertIsNone(silver["location"]["lat"])
        self.assertIsNone(silver["location"]["lon"])


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 5 registros válidos (parada 71 x4, parada 70 x1); 5 rechazados
        # (stop_id nulo, line nula, espera fuera de rango, distancia
        # negativa, payload de autenticación filtrado).
        self.assertEqual(len(silver_records), 5)
        self.assertEqual(len(rejected), 5)

        silver_stop_ids = {r["stop_id"] for r in silver_records}
        self.assertEqual(silver_stop_ids, {"71", "70"})

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("stop_id_missing", rejection_reasons)
        self.assertIn("line_missing", rejection_reasons)
        self.assertIn("estimate_arrive_sec_out_of_range", rejection_reasons)
        self.assertIn("distance_bus_m_negative", rejection_reasons)
        self.assertIn("unexpected_auth_error_payload", rejection_reasons)

    def test_every_silver_record_has_stop_and_line(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

        silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)

        for record in silver_records:
            self.assertIsNotNone(record["stop_id"])
            self.assertIsNotNone(record["line"])


if __name__ == "__main__":
    unittest.main()
