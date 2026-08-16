import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.meteorologia.aggregate import aggregate_silver_to_gold


def _silver_record(
    station_id,
    magnitude,
    measured_at,
    value,
    station_name="J.M.D. Moratalaz",
):
    return {
        "schema_version": 1,
        "source": "madrid_meteorologia",
        "station_id": station_id,
        "station_name": station_name,
        "station_address": "C/ Fuente Carantona, 8",
        "magnitude": magnitude,
        "value": value,
        "measured_at": measured_at,
        "ingested_at": measured_at,
        "processed_at": measured_at,
        "location": {"lat": 40.398611, "lon": -3.636944, "srid": "EPSG:4326", "altitude_m": 686},
    }


class AggregateSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)
        self.records = [
            _silver_record("28079102", "temperature_c", "2026-08-15T12:00:00+02:00", 21.6),
            _silver_record("28079102", "temperature_c", "2026-08-15T12:20:00+02:00", 22.4),
            _silver_record("28079102", "temperature_c", "2026-08-15T12:55:00+02:00", 21.0),
            # Misma estación y magnitud, hora distinta.
            _silver_record("28079102", "temperature_c", "2026-08-15T13:05:00+02:00", 23.0),
            # Misma estación y hora, magnitud distinta: no debe mezclarse
            # con las muestras de temperatura (unidades/escalas distintas).
            _silver_record("28079102", "humidity_pct", "2026-08-15T12:10:00+02:00", 43.0),
            # Estación distinta, misma hora y magnitud.
            _silver_record(
                "28079104",
                "temperature_c",
                "2026-08-15T12:15:00+02:00",
                20.0,
                station_name="E.D.A.R. La China",
            ),
        ]

    def test_groups_by_station_magnitude_and_hour(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)

        keys = {(r["station_id"], r["magnitude"], r["date"], r["hour"]) for r in gold}
        self.assertEqual(
            keys,
            {
                ("28079102", "temperature_c", "2026-08-15", 12),
                ("28079102", "temperature_c", "2026-08-15", 13),
                ("28079102", "humidity_pct", "2026-08-15", 12),
                ("28079104", "temperature_c", "2026-08-15", 12),
            },
        )

    def test_averages_and_extremes_are_correct_for_the_three_sample_bucket(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(
            r
            for r in gold
            if r["station_id"] == "28079102" and r["magnitude"] == "temperature_c" and r["hour"] == 12
        )

        self.assertEqual(bucket["samples_count"], 3)
        self.assertAlmostEqual(bucket["avg_value"], (21.6 + 22.4 + 21.0) / 3)
        self.assertEqual(bucket["max_value"], 22.4)
        self.assertEqual(bucket["min_value"], 21.0)
        self.assertEqual(bucket["first_measured_at"], "2026-08-15T12:00:00+02:00")
        self.assertEqual(bucket["last_measured_at"], "2026-08-15T12:55:00+02:00")
        self.assertEqual(bucket["station_name"], "J.M.D. Moratalaz")
        self.assertEqual(bucket["location"]["lat"], 40.398611)
        self.assertEqual(bucket["location"]["altitude_m"], 686)

    def test_magnitude_bucket_does_not_mix_with_other_magnitude_same_station_and_hour(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        humidity_bucket = next(r for r in gold if r["magnitude"] == "humidity_pct")

        self.assertEqual(humidity_bucket["samples_count"], 1)
        self.assertEqual(humidity_bucket["avg_value"], 43.0)

    def test_single_sample_bucket_matches_its_only_record(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["station_id"] == "28079104")

        self.assertEqual(bucket["samples_count"], 1)
        self.assertEqual(bucket["avg_value"], 20.0)
        self.assertEqual(bucket["station_name"], "E.D.A.R. La China")

    def test_records_without_measured_at_are_ignored(self):
        no_measured_at = _silver_record("28079199", "temperature_c", None, 21.0)
        gold = aggregate_silver_to_gold([no_measured_at], self.processed_at)
        self.assertEqual(gold, [])

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_silver_to_gold([], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
