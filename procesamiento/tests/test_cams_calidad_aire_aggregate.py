import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.cams_calidad_aire.aggregate import aggregate_silver_to_gold

PROCESSED_AT = datetime(2026, 8, 16, 3, 0, 0, tzinfo=timezone.utc)


def _silver_record(**overrides) -> dict:
    record = {
        "schema_version": 1,
        "source": "cams",
        "pollutant": "NO2",
        "pollutant_code": "nitrogen_dioxide",
        "value": 10.0,
        "unit": "µg/m3",
        "valid_datetime": "2026-08-15T02:00:00+02:00",
        "forecast_issued_at": "2026-08-15T02:00:00+02:00",
        "leadtime_hour": 0,
        "model": "ensemble",
        "latitude": 40.45,
        "longitude": -3.75,
        "ingested_at": "2026-08-16T02:21:09.151607+02:00",
        "processed_at": "2026-08-16T02:21:09.151607+02:00",
    }
    record.update(overrides)
    return record


class AggregateSilverToGoldTests(unittest.TestCase):
    def test_groups_by_pollutant_and_valid_date_not_by_leadtime(self):
        # Mismo contaminante, mismo día de validez, dos leadtime_hour
        # (0 y 1) y dos corridas distintas de forecast_issued_at -- deben
        # caer en el mismo bucket de Gold: la agregación es por
        # (pollutant, fecha_validez), no por horizonte de antelación.
        records = [
            _silver_record(value=10.0, leadtime_hour=0, valid_datetime="2026-08-15T02:00:00+02:00"),
            _silver_record(
                value=20.0,
                leadtime_hour=1,
                valid_datetime="2026-08-15T03:00:00+02:00",
                forecast_issued_at="2026-08-14T02:00:00+02:00",
            ),
        ]

        gold = aggregate_silver_to_gold(records, PROCESSED_AT)

        self.assertEqual(len(gold), 1)
        row = gold[0]
        self.assertEqual(row["pollutant"], "NO2")
        self.assertEqual(row["fecha_validez"], "2026-08-15")
        self.assertEqual(row["samples_count"], 2)
        self.assertEqual(row["avg_value"], 15.0)
        self.assertEqual(row["max_value"], 20.0)
        self.assertEqual(row["leadtime_hours"], [0, 1])

    def test_different_pollutants_on_same_day_are_separate_rows(self):
        records = [
            _silver_record(pollutant="NO2", pollutant_code="nitrogen_dioxide", value=10.0),
            _silver_record(pollutant="O3", pollutant_code="ozone", value=50.0),
        ]

        gold = aggregate_silver_to_gold(records, PROCESSED_AT)

        pollutants = {row["pollutant"] for row in gold}
        self.assertEqual(pollutants, {"NO2", "O3"})
        self.assertEqual(len(gold), 2)

    def test_different_valid_dates_for_same_pollutant_are_separate_rows(self):
        records = [
            _silver_record(valid_datetime="2026-08-15T02:00:00+02:00"),
            _silver_record(valid_datetime="2026-08-16T02:00:00+02:00", forecast_issued_at="2026-08-16T00:00:00+02:00"),
        ]

        gold = aggregate_silver_to_gold(records, PROCESSED_AT)

        fechas = {row["fecha_validez"] for row in gold}
        self.assertEqual(fechas, {"2026-08-15", "2026-08-16"})
        self.assertEqual(len(gold), 2)

    def test_first_and_last_forecast_issued_at_span_the_bucket(self):
        records = [
            _silver_record(forecast_issued_at="2026-08-15T02:00:00+02:00"),
            _silver_record(forecast_issued_at="2026-08-14T02:00:00+02:00"),
        ]

        gold = aggregate_silver_to_gold(records, PROCESSED_AT)

        self.assertEqual(len(gold), 1)
        self.assertEqual(gold[0]["first_forecast_issued_at"], "2026-08-14T02:00:00+02:00")
        self.assertEqual(gold[0]["last_forecast_issued_at"], "2026-08-15T02:00:00+02:00")

    def test_records_without_pollutant_or_valid_datetime_are_ignored(self):
        records = [
            _silver_record(pollutant=None),
            _silver_record(valid_datetime=None),
            _silver_record(),
        ]

        gold = aggregate_silver_to_gold(records, PROCESSED_AT)

        self.assertEqual(len(gold), 1)
        self.assertEqual(gold[0]["samples_count"], 1)

    def test_empty_input_produces_no_rows(self):
        self.assertEqual(aggregate_silver_to_gold([], PROCESSED_AT), [])

    def test_processed_at_is_stamped_on_every_row(self):
        gold = aggregate_silver_to_gold([_silver_record()], PROCESSED_AT)
        self.assertEqual(gold[0]["processed_at"], PROCESSED_AT.isoformat())


if __name__ == "__main__":
    unittest.main()
