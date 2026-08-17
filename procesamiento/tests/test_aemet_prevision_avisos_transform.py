import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.aemet_prevision_avisos.transform import (
    bronze_to_silver_avisos,
    bronze_to_silver_prevision,
    to_silver_aviso_record,
    to_silver_prevision_record,
    validate_aviso_record,
    validate_prevision_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_PREVISION_RECORD = {
    "schema_version": 1,
    "source": "aemet_prediccion_municipio",
    "municipio_code": "28079",
    "municipio_name": "Madrid",
    "province": "Madrid",
    "elaborated_at": "2026-08-13T21:19:10",
    "valid_date": "2026-08-15",
    "sky_state": "Intervalos nubosos con lluvia",
    "sky_state_code": "23",
    "precipitation_probability_pct": "95",
    "temperature_max_c": 34,
    "temperature_min_c": 22,
    "thermal_sensation_max_c": 31,
    "thermal_sensation_min_c": 21,
    "humidity_max_pct": 65,
    "humidity_min_pct": 25,
    "wind_direction": "SE",
    "wind_speed_kmh": "20",
    "wind_gust_max_kmh": "40",
    "uv_max": 8,
    "captured_at": "2026-08-14T00:32:05.022443+02:00",
    "is_mock": True,
}

VALID_AVISO_RECORD = {
    "schema_version": 1,
    "source": "aemet_avisos_cap",
    "identifier": "es-aemet-CAP-2026-08-14-00-72-01",
    "sent_at": "2026-08-14T07:45:00+02:00",
    "zone": "Madrid",
    "level": "amarillo",
    "phenomenon": "Altas temperaturas",
    "probability": "100%",
    "severity": "Moderate",
    "urgency": "Expected",
    "certainty": "Likely",
    "effective_from": "2026-08-14T13:00:00+02:00",
    "effective_until": "2026-08-14T21:00:00+02:00",
    "headline": "Aviso amarillo por altas temperaturas en Madrid",
    "description": "Temperaturas máximas en torno a 38-39 grados en la Comunidad de Madrid.",
    "captured_at": "2026-08-14T00:32:05.022443+02:00",
    "is_mock": True,
}


def _load_fixture(name: str) -> list:
    with (FIXTURES_DIR / name).open(encoding="utf-8") as f:
        return json.load(f)


class ValidatePrevisionRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_prevision_record(VALID_PREVISION_RECORD), [])

    def test_missing_municipio_code_is_rejected(self):
        record = {**VALID_PREVISION_RECORD, "municipio_code": None}
        self.assertIn("municipio_code_missing", validate_prevision_record(record))

    def test_missing_valid_date_is_rejected(self):
        record = {**VALID_PREVISION_RECORD, "valid_date": None}
        self.assertIn("valid_date_missing_or_unparseable", validate_prevision_record(record))

    def test_unparseable_valid_date_is_rejected(self):
        record = {**VALID_PREVISION_RECORD, "valid_date": "no es una fecha"}
        self.assertIn("valid_date_missing_or_unparseable", validate_prevision_record(record))

    def test_missing_ingested_at_is_rejected(self):
        record = {**VALID_PREVISION_RECORD, "captured_at": None}
        self.assertIn("ingested_at_missing_or_unparseable", validate_prevision_record(record))

    def test_naive_ingested_at_is_rejected(self):
        record = {**VALID_PREVISION_RECORD, "captured_at": "2026-08-14T00:32:05.022443"}
        self.assertIn("ingested_at_not_timezone_aware", validate_prevision_record(record))

    def test_valid_date_already_passed_is_rejected(self):
        record = {**VALID_PREVISION_RECORD, "valid_date": "2026-08-10"}
        self.assertIn("valid_date_already_passed", validate_prevision_record(record))

    def test_valid_date_same_day_as_ingested_at_is_accepted(self):
        # "Futura" incluye hoy mismo (leadtime_days == 0) -- ver docstring
        # del módulo, "Previsión: rangos plausibles y fecha de validez futura".
        record = {**VALID_PREVISION_RECORD, "valid_date": "2026-08-14"}
        self.assertEqual(validate_prevision_record(record), [])

    def test_missing_temperature_max_c_is_rejected(self):
        record = {**VALID_PREVISION_RECORD, "temperature_max_c": None}
        self.assertIn("temperature_max_c_missing_or_out_of_range", validate_prevision_record(record))

    def test_out_of_range_temperature_max_c_is_rejected(self):
        record = {**VALID_PREVISION_RECORD, "temperature_max_c": 65}
        self.assertIn("temperature_max_c_missing_or_out_of_range", validate_prevision_record(record))

    def test_out_of_range_temperature_min_c_is_rejected(self):
        record = {**VALID_PREVISION_RECORD, "temperature_min_c": -40}
        self.assertIn("temperature_min_c_missing_or_out_of_range", validate_prevision_record(record))

    def test_out_of_range_precipitation_probability_pct_is_rejected(self):
        record = {**VALID_PREVISION_RECORD, "precipitation_probability_pct": "150"}
        self.assertIn(
            "precipitation_probability_pct_missing_or_out_of_range", validate_prevision_record(record)
        )

    def test_precipitation_probability_as_string_is_accepted(self):
        # Bronze conserva probPrecipitacion como string (ver ingesta/README.md).
        record = {**VALID_PREVISION_RECORD, "precipitation_probability_pct": "0"}
        self.assertEqual(validate_prevision_record(record), [])


class ToSilverPrevisionRecordTests(unittest.TestCase):
    def test_normalizes_record_and_casts_numeric_fields_to_float(self):
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_prevision_record(VALID_PREVISION_RECORD, processed_at)

        self.assertEqual(silver["municipio_code"], "28079")
        self.assertEqual(silver["valid_date"], "2026-08-15")
        # `captured_at` de Bronze se renombra a `ingested_at` en Silver.
        self.assertEqual(silver["ingested_at"], "2026-08-14T00:32:05.022443+02:00")
        self.assertNotIn("captured_at", silver)
        # Campos numéricos que Bronze conserva como string (ver
        # ingesta/README.md) se normalizan a float en Silver.
        self.assertEqual(silver["precipitation_probability_pct"], 95.0)
        self.assertIsInstance(silver["precipitation_probability_pct"], float)
        self.assertEqual(silver["wind_speed_kmh"], 20.0)
        self.assertEqual(silver["wind_gust_max_kmh"], 40.0)
        self.assertEqual(silver["temperature_max_c"], 34.0)
        self.assertEqual(silver["processed_at"], processed_at.isoformat())

    def test_null_wind_gust_stays_none(self):
        record = {**VALID_PREVISION_RECORD, "wind_gust_max_kmh": None}
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_prevision_record(record, processed_at)

        self.assertIsNone(silver["wind_gust_max_kmh"])


class BronzeToSilverPrevisionTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture("aemet_prevision_bronze_sample.json")
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver_prevision(bronze_records, processed_at)

        # 3 días reales válidos + 8 sintéticos que violan cada regla de
        # rechazo por turnos, ver el fixture.
        self.assertEqual(len(silver_records), 3)
        self.assertEqual(len(rejected), 8)

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("municipio_code_missing", rejection_reasons)
        self.assertIn("valid_date_missing_or_unparseable", rejection_reasons)
        self.assertIn("ingested_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("ingested_at_not_timezone_aware", rejection_reasons)
        self.assertIn("valid_date_already_passed", rejection_reasons)
        self.assertIn("temperature_max_c_missing_or_out_of_range", rejection_reasons)
        self.assertIn("temperature_min_c_missing_or_out_of_range", rejection_reasons)
        self.assertIn("precipitation_probability_pct_missing_or_out_of_range", rejection_reasons)


class ValidateAvisoRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_aviso_record(VALID_AVISO_RECORD), [])

    def test_missing_identifier_is_rejected(self):
        record = {**VALID_AVISO_RECORD, "identifier": None}
        self.assertIn("identifier_missing", validate_aviso_record(record))

    def test_missing_zone_is_rejected(self):
        record = {**VALID_AVISO_RECORD, "zone": None}
        self.assertIn("zone_missing", validate_aviso_record(record))

    def test_missing_level_is_rejected(self):
        record = {**VALID_AVISO_RECORD, "level": None}
        self.assertIn("level_missing_or_invalid", validate_aviso_record(record))

    def test_invalid_level_is_rejected(self):
        record = {**VALID_AVISO_RECORD, "level": "morado"}
        self.assertIn("level_missing_or_invalid", validate_aviso_record(record))

    def test_naranja_and_rojo_are_also_valid(self):
        for level in ("naranja", "rojo"):
            record = {**VALID_AVISO_RECORD, "level": level}
            self.assertEqual(validate_aviso_record(record), [])

    def test_missing_phenomenon_is_rejected(self):
        record = {**VALID_AVISO_RECORD, "phenomenon": None}
        self.assertIn("phenomenon_missing", validate_aviso_record(record))

    def test_missing_effective_from_is_rejected(self):
        record = {**VALID_AVISO_RECORD, "effective_from": None}
        self.assertIn("effective_from_missing_or_unparseable", validate_aviso_record(record))

    def test_missing_ingested_at_is_rejected(self):
        record = {**VALID_AVISO_RECORD, "captured_at": None}
        self.assertIn("ingested_at_missing_or_unparseable", validate_aviso_record(record))

    def test_naive_ingested_at_is_rejected(self):
        record = {**VALID_AVISO_RECORD, "captured_at": "2026-08-14T00:32:05.022443"}
        self.assertIn("ingested_at_not_timezone_aware", validate_aviso_record(record))


class ToSilverAvisoRecordTests(unittest.TestCase):
    def test_normalizes_record(self):
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver = to_silver_aviso_record(VALID_AVISO_RECORD, processed_at)

        self.assertEqual(silver["identifier"], "es-aemet-CAP-2026-08-14-00-72-01")
        self.assertEqual(silver["zone"], "Madrid")
        self.assertEqual(silver["level"], "amarillo")
        self.assertEqual(silver["ingested_at"], "2026-08-14T00:32:05.022443+02:00")
        self.assertNotIn("captured_at", silver)
        self.assertEqual(silver["processed_at"], processed_at.isoformat())


class BronzeToSilverAvisosTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture("aemet_avisos_bronze_sample.json")
        processed_at = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver_avisos(bronze_records, processed_at)

        # 1 aviso real válido + 7 sintéticos que violan cada regla de
        # rechazo por turnos, ver el fixture.
        self.assertEqual(len(silver_records), 1)
        self.assertEqual(len(rejected), 7)

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("identifier_missing", rejection_reasons)
        self.assertIn("zone_missing", rejection_reasons)
        self.assertIn("level_missing_or_invalid", rejection_reasons)
        self.assertIn("phenomenon_missing", rejection_reasons)
        self.assertIn("effective_from_missing_or_unparseable", rejection_reasons)
        self.assertIn("ingested_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("ingested_at_not_timezone_aware", rejection_reasons)


if __name__ == "__main__":
    unittest.main()
