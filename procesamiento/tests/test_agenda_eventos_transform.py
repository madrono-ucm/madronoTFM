import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.agenda_eventos.transform import (
    bronze_to_silver,
    to_silver_record,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_MUNICIPAL_RECORD = {
    "schema_version": 1,
    "source": "agenda_eventos_madrid_municipal",
    "event_id": "50334065",
    "title": "10 vidas",
    "description": "Una película de animación.",
    "category": "CineActividadesAudiovisuales",
    "start_datetime": "2026-08-21T22:00:00",
    "end_datetime": "2026-08-21T23:59:00",
    "schedule_text": "22:00",
    "free": True,
    "price_info": None,
    "location": {
        "venue_name": "Parque de Villa Rosa-Paco Caño",
        "address": "CALLE ACONCAGUA 2",
        "district": "Hortaleza",
        "neighborhood": "Canillas",
        "postal_code": "28043",
        "lat": 40.468674190501815,
        "lon": -3.631588640594873,
        "srid": "EPSG:4326",
    },
    "url": "http://www.madrid.es/evento",
    "captured_at": "2026-08-15T12:39:24.904227+02:00",
}

VALID_ESMADRID_RECORD = {
    "schema_version": 1,
    "source": "agenda_turismo_esmadrid",
    "event_id": "109464",
    "title": "Ed Maverick",
    "description": "Concierto en La Riviera.",
    "category": "Eventos > Música > Pop-rock",
    "start_datetime": "2026-11-15",
    "end_datetime": "2026-11-15",
    "schedule_text": "21:00 h",
    "free": None,
    "price_info": "Desde 35 €",
    "location": {
        "venue_name": "La Riviera",
        "address": "Bajo de la Virgen del Puerto, s/n",
        "district": None,
        "neighborhood": None,
        "postal_code": "28005",
        "lat": 40.4133013,
        "lon": -3.7219371,
        "srid": "EPSG:4326",
    },
    "url": "https://www.esmadrid.com/agenda/ed-maverick-riviera",
    "captured_at": "2026-08-15T12:39:26.252067+02:00",
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "agenda_eventos_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_municipal_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_MUNICIPAL_RECORD), [])

    def test_valid_esmadrid_record_has_no_rejection_reasons(self):
        # Fecha sin hora (esMadrid solo publica el día, ver transform.py) --
        # sigue siendo válida.
        self.assertEqual(validate_record(VALID_ESMADRID_RECORD), [])

    def test_unknown_source_is_rejected(self):
        record = {**VALID_MUNICIPAL_RECORD, "source": "otra_fuente"}
        self.assertIn("source_missing_or_unknown", validate_record(record))

    def test_missing_source_is_rejected(self):
        record = {**VALID_MUNICIPAL_RECORD, "source": None}
        self.assertIn("source_missing_or_unknown", validate_record(record))

    def test_missing_event_id_is_rejected(self):
        record = {**VALID_MUNICIPAL_RECORD, "event_id": None}
        self.assertIn("event_id_missing", validate_record(record))

    def test_missing_title_is_rejected(self):
        record = {**VALID_MUNICIPAL_RECORD, "title": None}
        self.assertIn("title_missing", validate_record(record))

    def test_missing_start_datetime_is_rejected(self):
        record = {**VALID_MUNICIPAL_RECORD, "start_datetime": None}
        self.assertIn("start_datetime_missing_or_unparseable", validate_record(record))

    def test_unparseable_start_datetime_is_rejected(self):
        record = {**VALID_MUNICIPAL_RECORD, "start_datetime": "fecha no disponible"}
        self.assertIn("start_datetime_missing_or_unparseable", validate_record(record))

    def test_date_only_start_datetime_is_accepted(self):
        # Formato propio de esMadrid (solo fecha, sin hora) -- válido, ver
        # docstring del módulo.
        record = {**VALID_MUNICIPAL_RECORD, "start_datetime": "2026-11-15"}
        self.assertEqual(validate_record(record), [])

    def test_missing_captured_at_is_rejected(self):
        record = {**VALID_MUNICIPAL_RECORD, "captured_at": None}
        self.assertIn("captured_at_missing_or_unparseable", validate_record(record))

    def test_naive_captured_at_is_rejected(self):
        record = {**VALID_MUNICIPAL_RECORD, "captured_at": "2026-08-15T12:39:24.904227"}
        self.assertIn("captured_at_not_timezone_aware", validate_record(record))

    def test_start_datetime_already_past_captured_at_is_accepted(self):
        # A diferencia de cartelera_cines_estrenos: un evento de varios
        # días que ya empezó respecto a la captura sigue siendo válido (ver
        # docstring del módulo).
        record = {
            **VALID_MUNICIPAL_RECORD,
            "start_datetime": "2026-07-01T00:00:00",
            "captured_at": "2026-08-15T12:39:24.904227+02:00",
        }
        self.assertEqual(validate_record(record), [])

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_MUNICIPAL_RECORD, "title": None, "event_id": None}
        reasons = validate_record(record)
        self.assertIn("title_missing", reasons)
        self.assertIn("event_id_missing", reasons)


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_municipal_record_flattening_location(self):
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_MUNICIPAL_RECORD, processed_at)

        self.assertEqual(silver["event_id"], "50334065")
        self.assertEqual(silver["title"], "10 vidas")
        self.assertEqual(silver["district"], "Hortaleza")
        self.assertEqual(silver["neighborhood"], "Canillas")
        self.assertEqual(silver["lat"], 40.468674190501815)
        self.assertEqual(silver["lon"], -3.631588640594873)
        # `captured_at` de Bronze se renombra a `ingested_at` en Silver, ver
        # docstring de transform.to_silver_record.
        self.assertEqual(silver["ingested_at"], "2026-08-15T12:39:24.904227+02:00")
        self.assertNotIn("captured_at", silver)
        self.assertNotIn("location", silver)
        self.assertEqual(silver["processed_at"], processed_at.isoformat())

    def test_normalizes_esmadrid_record_with_null_district(self):
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_ESMADRID_RECORD, processed_at)

        self.assertEqual(silver["source"], "agenda_turismo_esmadrid")
        self.assertIsNone(silver["district"])
        self.assertIsNone(silver["neighborhood"])
        self.assertEqual(silver["start_datetime"], "2026-11-15")


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 10 eventos reales válidos (5 municipales + 5 esMadrid) + 7
        # sintéticos que violan cada regla de rechazo por turnos, ver el
        # fixture.
        self.assertEqual(len(silver_records), 10)
        self.assertEqual(len(rejected), 7)

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("source_missing_or_unknown", rejection_reasons)
        self.assertIn("event_id_missing", rejection_reasons)
        self.assertIn("title_missing", rejection_reasons)
        self.assertIn("start_datetime_missing_or_unparseable", rejection_reasons)
        self.assertIn("captured_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("captured_at_not_timezone_aware", rejection_reasons)


if __name__ == "__main__":
    unittest.main()
