import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.ruido.aggregate import aggregate_silver_to_gold


def _silver_record(
    station_id,
    period,
    measured_date,
    laeq_db,
    station_name="Paseo de Recoletos",
    period_name="diurno",
    l90_db=54.8,
):
    return {
        "schema_version": 1,
        "source": "madrid_ruido_diario",
        "station_id": station_id,
        "station_name": station_name,
        "station_address": "Frente al n23 del Paseo de Recoletos",
        "district": "Centro",
        "neighbourhood": "Justicia",
        "period": period,
        "period_name": period_name,
        "measured_date": measured_date,
        "ingested_at": "2026-08-15T12:32:21.270994+02:00",
        "processed_at": "2026-08-15T12:32:21.270994+02:00",
        "laeq_db": laeq_db,
        "l1_db": 69.4,
        "l10_db": 65.9,
        "l50_db": 60.4,
        "l90_db": l90_db,
        "l99_db": 52.2,
        "location": {"lat": 40.422599, "lon": -3.691877, "srid": "EPSG:4326", "altitude_m": 648},
    }


class AggregateSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)

    def test_groups_by_station_period_and_date(self):
        records = [
            _silver_record("RF-01", "D", "2026-08-13", 62.6),
            _silver_record("RF-01", "E", "2026-08-13", 62.3, period_name="vespertino"),
            _silver_record("RF-02", "D", "2026-08-13", 67.1, station_name="Carlos V"),
        ]

        gold = aggregate_silver_to_gold(records, self.processed_at)

        keys = {(r["station_id"], r["period"], r["date"]) for r in gold}
        self.assertEqual(
            keys,
            {("RF-01", "D", "2026-08-13"), ("RF-01", "E", "2026-08-13"), ("RF-02", "D", "2026-08-13")},
        )

    def test_duplicate_ingestion_same_day_is_averaged(self):
        records = [
            _silver_record("RF-01", "D", "2026-08-13", 60.0),
            _silver_record("RF-01", "D", "2026-08-13", 64.0),
        ]

        gold = aggregate_silver_to_gold(records, self.processed_at)

        self.assertEqual(len(gold), 1)
        bucket = gold[0]
        self.assertEqual(bucket["samples_count"], 2)
        self.assertAlmostEqual(bucket["avg_laeq_db"], 62.0)
        self.assertEqual(bucket["max_laeq_db"], 64.0)
        self.assertEqual(bucket["min_laeq_db"], 60.0)

    def test_single_reading_matches_source_value(self):
        records = [_silver_record("RF-01", "D", "2026-08-13", 62.6)]

        gold = aggregate_silver_to_gold(records, self.processed_at)

        bucket = gold[0]
        self.assertEqual(bucket["avg_laeq_db"], 62.6)
        self.assertEqual(bucket["laeq_rolling_7d_avg_db"], 62.6)
        self.assertEqual(bucket["laeq_rolling_7d_days"], 1)
        self.assertEqual(bucket["location"]["altitude_m"], 648)

    def test_rolling_7_day_average_only_includes_days_within_the_calendar_window(self):
        records = [
            _silver_record("RF-01", "D", "2026-08-01", 40.0),  # fuera de ventana (>6 dias antes)
            _silver_record("RF-01", "D", "2026-08-07", 60.0),  # dentro (7 dias antes, incluido)
            _silver_record("RF-01", "D", "2026-08-10", 70.0),  # dentro (3 dias antes)
            _silver_record("RF-01", "D", "2026-08-13", 80.0),  # dia actual
        ]

        gold = aggregate_silver_to_gold(records, self.processed_at)
        bucket = next(r for r in gold if r["date"] == "2026-08-13")

        # Ventana de 7 dias naturales: 2026-08-07 .. 2026-08-13. La lectura
        # del 2026-08-01 (12 dias antes) queda fuera.
        self.assertEqual(bucket["laeq_rolling_7d_days"], 3)
        self.assertAlmostEqual(bucket["laeq_rolling_7d_avg_db"], (60.0 + 70.0 + 80.0) / 3)

    def test_rolling_average_does_not_mix_different_periods(self):
        records = [
            _silver_record("RF-01", "D", "2026-08-12", 40.0),
            _silver_record("RF-01", "N", "2026-08-13", 90.0, period_name="nocturno"),
        ]

        gold = aggregate_silver_to_gold(records, self.processed_at)
        night_bucket = next(r for r in gold if r["period"] == "N")

        self.assertEqual(night_bucket["laeq_rolling_7d_days"], 1)
        self.assertEqual(night_bucket["laeq_rolling_7d_avg_db"], 90.0)

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_silver_to_gold([], self.processed_at), [])

    def test_records_without_measured_date_are_ignored(self):
        record = _silver_record("RF-01", "D", None, 62.6)
        self.assertEqual(aggregate_silver_to_gold([record], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
