import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from procesamiento.silver_gold.meteorologia.transform import (
    MAGNITUDE_FIELDS,
    bronze_to_silver,
    to_silver_record,
    validate_magnitude_value,
    validate_record,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

VALID_RECORD = {
    "schema_version": 1,
    "source": "madrid_meteorologia",
    "station_id": "28079102",
    "station_name": "J.M.D. Moratalaz",
    "station_address": "C/ Fuente Carantona, 8",
    "measured_at": "2026-08-15T12:00:00+02:00",
    "ingested_at": "2026-08-15T12:32:18.147036+02:00",
    "temperature_c": 21.6,
    "humidity_pct": 43.0,
    "wind_speed_ms": 3.2,
    "wind_direction_deg": 120.0,
    "pressure_mb": 940.0,
    "solar_radiation_wm2": 313.0,
    "uv_radiation_mwm2": None,
    "precipitation_lm2": 0.0,
    "location": {"lat": 40.398611, "lon": -3.636944, "srid": "EPSG:4326", "altitude_m": 686},
}


def _load_fixture() -> list:
    with (FIXTURES_DIR / "meteorologia_bronze_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record_has_no_rejection_reasons(self):
        self.assertEqual(validate_record(VALID_RECORD), [])

    def test_missing_station_id_is_rejected(self):
        record = {**VALID_RECORD, "station_id": None}
        self.assertIn("station_id_missing", validate_record(record))

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
        record = {**VALID_RECORD, "ingested_at": "2026-08-15T12:32:18.147036"}
        self.assertIn("ingested_at_not_timezone_aware", validate_record(record))

    def test_multiple_reasons_can_accumulate(self):
        record = {**VALID_RECORD, "station_id": None, "measured_at": None}
        reasons = validate_record(record)
        self.assertIn("station_id_missing", reasons)
        self.assertIn("measured_at_missing_or_unparseable", reasons)

    def test_record_with_no_magnitudes_present_still_passes_record_level_checks(self):
        # No es un caso que la fuente real produzca (ver
        # `_latest_valid_hour` en `ingesta/capturas/meteorologia_madrid.py`,
        # que ya descarta estaciones sin ninguna lectura válida), pero
        # `validate_record` solo comprueba estación/instante -- no exige que
        # haya al menos una magnitud presente.
        record = {**VALID_RECORD, **{field: None for field in MAGNITUDE_FIELDS}}
        self.assertEqual(validate_record(record), [])


class ValidateMagnitudeValueTests(unittest.TestCase):
    def test_value_within_range_is_accepted(self):
        self.assertIsNone(validate_magnitude_value("temperature_c", 21.6))

    def test_value_at_lower_bound_is_accepted(self):
        self.assertIsNone(validate_magnitude_value("temperature_c", -20.0))

    def test_value_at_upper_bound_is_accepted(self):
        self.assertIsNone(validate_magnitude_value("humidity_pct", 100.0))

    def test_value_below_lower_bound_is_rejected(self):
        self.assertEqual(validate_magnitude_value("temperature_c", -20.1), "value_out_of_plausible_range")

    def test_value_above_upper_bound_is_rejected(self):
        self.assertEqual(validate_magnitude_value("temperature_c", 500.0), "value_out_of_plausible_range")

    def test_same_value_is_accepted_for_a_magnitude_with_a_wider_plausible_range(self):
        # 500 se rechaza para temperature_c (máx 50) pero es plausible para
        # uv_radiation_mwm2 (máx 5000) -- el rango es por magnitud, no global.
        self.assertIsNone(validate_magnitude_value("uv_radiation_mwm2", 500.0))

    def test_negative_humidity_is_rejected(self):
        self.assertEqual(validate_magnitude_value("humidity_pct", -1.0), "value_out_of_plausible_range")


class ToSilverRecordTests(unittest.TestCase):
    def test_normalizes_expected_fields_for_a_single_magnitude(self):
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver = to_silver_record(VALID_RECORD, "temperature_c", 21.6, processed_at)

        self.assertEqual(silver["station_id"], "28079102")
        self.assertEqual(silver["magnitude"], "temperature_c")
        self.assertEqual(silver["value"], 21.6)
        self.assertEqual(silver["processed_at"], processed_at.isoformat())
        self.assertEqual(silver["location"]["lat"], 40.398611)
        self.assertEqual(silver["location"]["lon"], -3.636944)
        self.assertEqual(silver["location"]["altitude_m"], 686)


class BronzeToSilverTests(unittest.TestCase):
    def test_fixture_splits_valid_and_rejected_records(self):
        bronze_records = _load_fixture()
        processed_at = datetime(2026, 8, 15, 12, 30, 0, tzinfo=timezone.utc)

        silver_records, rejected = bronze_to_silver(bronze_records, processed_at)

        # 5 estaciones reales (con distinto nº de magnitudes presentes cada
        # una: 7+2+7+7+7 = 30) + 2 magnitudes válidas de la 10ª estación
        # (humedad y viento; su temperatura se rechaza sola) = 32 filas
        # Silver. 5 items rechazados: 4 a nivel de registro (estación sin id,
        # sin measured_at, con measured_at sin zona horaria, sin ingested_at)
        # + 1 a nivel de magnitud (temperatura disparada) -- ver el fixture.
        self.assertEqual(len(silver_records), 32)
        self.assertEqual(len(rejected), 5)

        magnitudes = {r["magnitude"] for r in silver_records}
        self.assertIn("temperature_c", magnitudes)
        self.assertIn("humidity_pct", magnitudes)
        self.assertIn("wind_speed_ms", magnitudes)

        rejection_reasons = {reason for item in rejected for reason in item["reasons"]}
        self.assertIn("station_id_missing", rejection_reasons)
        self.assertIn("measured_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("measured_at_not_timezone_aware", rejection_reasons)
        self.assertIn("ingested_at_missing_or_unparseable", rejection_reasons)
        self.assertIn("value_out_of_plausible_range", rejection_reasons)

    def test_a_single_out_of_range_magnitude_does_not_reject_the_whole_station_record(self):
        record = {**VALID_RECORD, "station_id": "28079999", "temperature_c": 500.0}
        silver_records, rejected = bronze_to_silver([record], datetime(2026, 8, 15, tzinfo=timezone.utc))

        magnitudes = {r["magnitude"] for r in silver_records}
        self.assertNotIn("temperature_c", magnitudes)
        self.assertIn("humidity_pct", magnitudes)
        self.assertIn("wind_speed_ms", magnitudes)

        magnitude_level_rejections = [item for item in rejected if item.get("magnitude") == "temperature_c"]
        self.assertEqual(len(magnitude_level_rejections), 1)
        self.assertEqual(magnitude_level_rejections[0]["reasons"], ["value_out_of_plausible_range"])

    def test_a_station_level_rejection_drops_all_its_magnitudes(self):
        record = {**VALID_RECORD, "station_id": None}
        silver_records, rejected = bronze_to_silver([record], datetime(2026, 8, 15, tzinfo=timezone.utc))

        self.assertEqual(silver_records, [])
        self.assertEqual(len(rejected), 1)
        self.assertNotIn("magnitude", rejected[0])


if __name__ == "__main__":
    unittest.main()
