import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.bluesky_menciones.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_RECORD = {
    "schema_version": 1,
    "source": "bluesky_menciones_madrid",
    "mode": "bajo_demanda",
    "match_term": "Puerta del Sol",
    "post_hash": "ef5153e1310e12ca",
    "text": "Eclipse en la Puerta del Sol.",
    "lang": "es",
    "created_at": "2026-08-15T01:49:27.253Z",
    "indexed_at": "2026-08-15T01:49:28.066Z",
    "like_count": 0,
    "repost_count": 0,
    "reply_count": 0,
    "quote_count": 0,
    "captured_at": "2026-08-15T12:39:31.300627+02:00",
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "bluesky_menciones_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_mode_is_rejected(self):
        record = {**VALID_RECORD, "mode": None}
        self.assertIn("mode_missing_or_invalid", validate_record(record))

    def test_invalid_mode_is_rejected(self):
        record = {**VALID_RECORD, "mode": "modo_desconocido"}
        self.assertIn("mode_missing_or_invalid", validate_record(record))

    def test_district_sweep_mode_is_also_valid(self):
        record = {**VALID_RECORD, "mode": "distrito_sweep", "match_term": "Centro"}
        self.assertEqual(validate_record(record), [])

    def test_missing_match_term_is_rejected(self):
        record = {**VALID_RECORD, "match_term": None}
        self.assertIn("match_term_missing", validate_record(record))

    def test_blank_match_term_is_rejected(self):
        record = {**VALID_RECORD, "match_term": "   "}
        self.assertIn("match_term_missing", validate_record(record))

    def test_missing_text_is_rejected(self):
        record = {**VALID_RECORD, "text": None}
        self.assertIn("text_missing_or_empty", validate_record(record))

    def test_blank_text_is_rejected(self):
        record = {**VALID_RECORD, "text": "   "}
        self.assertIn("text_missing_or_empty", validate_record(record))

    def test_missing_post_hash_is_rejected(self):
        record = {**VALID_RECORD, "post_hash": None}
        self.assertIn("post_hash_missing", validate_record(record))

    def test_missing_created_at_is_rejected(self):
        record = {**VALID_RECORD, "created_at": None}
        self.assertIn("created_at_missing_or_unparseable", validate_record(record))

    def test_unparseable_created_at_is_rejected(self):
        record = {**VALID_RECORD, "created_at": "no es una fecha"}
        self.assertIn("created_at_missing_or_unparseable", validate_record(record))

    def test_naive_created_at_is_rejected(self):
        record = {**VALID_RECORD, "created_at": "2026-08-15T01:49:27.253"}
        self.assertIn("created_at_not_timezone_aware", validate_record(record))

    def test_created_at_with_z_suffix_is_accepted(self):
        # Bluesky entrega created_at/indexed_at con sufijo "Z" (UTC), no con
        # offset explicito -- ver docstring del modulo sobre Python 3.10 en
        # el runtime real de Glue 4.0.
        record = {**VALID_RECORD, "created_at": "2026-08-15T01:49:27.253Z"}
        self.assertEqual(validate_record(record), [])

    def test_missing_captured_at_is_rejected(self):
        record = {**VALID_RECORD, "captured_at": None}
        self.assertIn("captured_at_missing_or_unparseable", validate_record(record))

    def test_naive_captured_at_is_rejected(self):
        record = {**VALID_RECORD, "captured_at": "2026-08-15T12:39:31.300627"}
        self.assertIn("captured_at_not_timezone_aware", validate_record(record))

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_RECORD, "mode": None, "text": None}
        reasons = validate_record(record)
        self.assertIn("mode_missing_or_invalid", reasons)
        self.assertIn("text_missing_or_empty", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_record(self):
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_RECORD, processed_at)

        self.assertEqual(silver["mode"], "bajo_demanda")
        self.assertEqual(silver["match_term"], "Puerta del Sol")
        self.assertEqual(silver["post_hash"], "ef5153e1310e12ca")
        self.assertEqual(silver["text"], "Eclipse en la Puerta del Sol.")
        self.assertEqual(silver["created_at"], "2026-08-15T01:49:27.253Z")
        # `captured_at` de Bronze se renombra a `ingested_at` en Silver, ver
        # docstring de transform.to_silver_record.
        self.assertEqual(silver["ingested_at"], "2026-08-15T12:39:31.300627+02:00")
        self.assertNotIn("captured_at", silver)
        self.assertEqual(silver["processed_at"], processed_at.isoformat())


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_rejected_and_duplicate_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 5 posts reales válidos + 1 duplicado exacto de uno de ellos (mismo
        # post_hash, otro match_term) + 10 que violan cada regla de rechazo
        # por turnos, ver el fixture.
        self.assertEqual(len(silver_records), 5)
        self.assertEqual(len(rejected), 11)

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("duplicate_exact_content", rejection_reasons)
        self.assertIn("mode_missing_or_invalid", rejection_reasons)
        self.assertIn("match_term_missing", rejection_reasons)
        self.assertIn("text_missing_or_empty", rejection_reasons)
        self.assertIn("post_hash_missing", rejection_reasons)
        self.assertIn("created_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("created_at_not_timezone_aware", rejection_reasons)
        self.assertIn("captured_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("captured_at_not_timezone_aware", rejection_reasons)

    def test_duplicate_keeps_first_occurrence(self):
        first = {**VALID_RECORD, "match_term": "Puerta del Sol"}
        duplicate = {**VALID_RECORD, "match_term": "eventos:recomendación"}
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver([first, duplicate], processed_at)

        self.assertEqual(len(silver_records), 1)
        self.assertEqual(silver_records[0]["match_term"], "Puerta del Sol")
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["reasons"], ["duplicate_exact_content"])

    def test_duplicate_across_different_modes_is_still_detected(self):
        first = {**VALID_RECORD, "mode": "bajo_demanda"}
        duplicate = {**VALID_RECORD, "mode": "distrito_sweep", "match_term": "Centro"}
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver([first, duplicate], processed_at)

        self.assertEqual(len(silver_records), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["reasons"], ["duplicate_exact_content"])


if __name__ == "__main__":
    unittest.main()
