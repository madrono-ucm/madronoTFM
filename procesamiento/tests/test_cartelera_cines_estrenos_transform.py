import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.cartelera_cines_estrenos.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_SESSION_RECORD = {
    "schema_version": 1,
    "source": "cartelera_cines_madrid",
    "cinema_id": "cinesa_proyecciones",
    "chain": "cinesa",
    "cinema_name": "Cinesa Proyecciones",
    "address": "Calle de Fuencarral 136",
    "postal_code": "28001",
    "locality": "Madrid",
    "screen_count": 8,
    "movie_title": "Minions & Monsters",
    "movie_url": "https://www.sensacine.com/peliculas/pelicula-315380/",
    "language_version": "En Versión doblada",
    "experiences": ["Format.Projection.Digital"],
    "showtime_datetime": "2026-08-15T15:45:00+02:00",
    "showtime_id": "80287958749",
    "captured_at": "2026-08-15T12:39:30.369461+02:00",
}

PREMIERE_RECORD = {
    "schema_version": 1,
    "source": "cartelera_cines_madrid",
    "record_type": "estreno_semana",
    "movie_title": "El final de Oak Street",
    "movie_url": "https://www.sensacine.com/peliculas/pelicula-314503/",
    "release_date": "2026-08-14",
    "duration_minutes": 100,
    "genres": ["Acción", "Aventura", "Ciencia ficción"],
    "captured_at": "2026-08-15T12:39:30.369461+02:00",
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "cartelera_cines_estrenos_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_session_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_SESSION_RECORD), [])

    def test_premiere_record_is_rejected_as_not_a_screening_session(self):
        self.assertIn("not_a_screening_session", validate_record(PREMIERE_RECORD))

    def test_missing_movie_title_is_rejected(self):
        record = {**VALID_SESSION_RECORD, "movie_title": None}
        self.assertIn("movie_title_missing", validate_record(record))

    def test_missing_cinema_id_is_rejected(self):
        record = {**VALID_SESSION_RECORD, "cinema_id": None}
        self.assertIn("cinema_id_missing", validate_record(record))

    def test_missing_showtime_id_is_rejected(self):
        record = {**VALID_SESSION_RECORD, "showtime_id": None}
        self.assertIn("showtime_id_missing", validate_record(record))

    def test_missing_showtime_datetime_is_rejected(self):
        record = {**VALID_SESSION_RECORD, "showtime_datetime": None}
        self.assertIn("showtime_datetime_missing_or_unparseable", validate_record(record))

    def test_unparseable_showtime_datetime_is_rejected(self):
        record = {**VALID_SESSION_RECORD, "showtime_datetime": "no es una fecha"}
        self.assertIn("showtime_datetime_missing_or_unparseable", validate_record(record))

    def test_naive_showtime_datetime_is_rejected(self):
        record = {**VALID_SESSION_RECORD, "showtime_datetime": "2026-08-15T15:45:00"}
        self.assertIn("showtime_datetime_not_timezone_aware", validate_record(record))

    def test_missing_captured_at_is_rejected(self):
        record = {**VALID_SESSION_RECORD, "captured_at": None}
        self.assertIn("captured_at_missing_or_unparseable", validate_record(record))

    def test_naive_captured_at_is_rejected(self):
        record = {**VALID_SESSION_RECORD, "captured_at": "2026-08-15T12:39:30.369461"}
        self.assertIn("captured_at_not_timezone_aware", validate_record(record))

    def test_showtime_already_passed_is_rejected(self):
        record = {**VALID_SESSION_RECORD, "showtime_datetime": "2026-08-15T10:00:00+02:00"}
        self.assertIn("showtime_already_passed", validate_record(record))

    def test_showtime_exactly_at_capture_instant_is_accepted(self):
        # showtime_datetime == captured_at: la sesión empieza justo cuando
        # se captura la cartelera, no es un dato ya pasado (comparación
        # estricta "<", no "<=").
        record = {**VALID_SESSION_RECORD, "showtime_datetime": VALID_SESSION_RECORD["captured_at"]}
        self.assertEqual(validate_record(record), [])

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_SESSION_RECORD, "movie_title": None, "cinema_id": None}
        reasons = validate_record(record)
        self.assertIn("movie_title_missing", reasons)
        self.assertIn("cinema_id_missing", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_session_record(self):
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_SESSION_RECORD, processed_at)

        self.assertEqual(silver["cinema_id"], "cinesa_proyecciones")
        self.assertEqual(silver["movie_title"], "Minions & Monsters")
        self.assertEqual(silver["showtime_id"], "80287958749")
        self.assertEqual(silver["showtime_datetime"], "2026-08-15T15:45:00+02:00")
        # `captured_at` de Bronze se renombra a `ingested_at` en Silver, ver
        # docstring de transform.to_silver_record.
        self.assertEqual(silver["ingested_at"], "2026-08-15T12:39:30.369461+02:00")
        self.assertNotIn("captured_at", silver)
        self.assertEqual(silver["processed_at"], processed_at.isoformat())
        self.assertEqual(silver["experiences"], ["Format.Projection.Digital"])

    def test_missing_experiences_defaults_to_empty_list(self):
        record = {**VALID_SESSION_RECORD, "experiences": None}
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(record, processed_at)

        self.assertEqual(silver["experiences"], [])


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 6 sesiones reales válidas + 1 estreno semanal + 8 que violan cada
        # regla de rechazo por turnos, ver el fixture.
        self.assertEqual(len(silver_records), 6)
        self.assertEqual(len(rejected), 9)

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("not_a_screening_session", rejection_reasons)
        self.assertIn("movie_title_missing", rejection_reasons)
        self.assertIn("cinema_id_missing", rejection_reasons)
        self.assertIn("showtime_id_missing", rejection_reasons)
        self.assertIn("showtime_datetime_missing_or_unparseable", rejection_reasons)
        self.assertIn("showtime_datetime_not_timezone_aware", rejection_reasons)
        self.assertIn("captured_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("captured_at_not_timezone_aware", rejection_reasons)
        self.assertIn("showtime_already_passed", rejection_reasons)


if __name__ == "__main__":
    unittest.main()
