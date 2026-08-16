import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.calidad_aire.aggregate import aggregate_silver_to_gold


def _silver_record(
    station_id,
    pollutant,
    measured_at,
    value,
    station_name="Ramón y Cajal",
    magnitude_code="08",
    pollutant_name="Dióxido de Nitrógeno",
    unit="µg/m³",
):
    return {
        "schema_version": 1,
        "source": "madrid_calidad_aire",
        "station_id": station_id,
        "station_name": station_name,
        "station_address": "Avda. Ramón y Cajal",
        "magnitude_code": magnitude_code,
        "pollutant": pollutant,
        "pollutant_name": pollutant_name,
        "unit": unit,
        "value": value,
        "measured_at": measured_at,
        "ingested_at": measured_at,
        "processed_at": measured_at,
        "location": {"lat": 40.4514734, "lon": -3.6773491, "srid": "EPSG:4326"},
    }


class AggregateSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)
        self.records = [
            _silver_record("28079011", "NO2", "2026-08-15T12:00:00+02:00", 25.0),
            _silver_record("28079011", "NO2", "2026-08-15T12:20:00+02:00", 27.0),
            _silver_record("28079011", "NO2", "2026-08-15T12:55:00+02:00", 23.0),
            # Misma estación, hora distinta.
            _silver_record("28079011", "NO2", "2026-08-15T13:05:00+02:00", 30.0),
            # Misma estación y hora, contaminante distinto: no debe
            # mezclarse con las muestras de NO2 (unidades/escalas
            # distintas).
            _silver_record(
                "28079011",
                "O3",
                "2026-08-15T12:10:00+02:00",
                68.0,
                magnitude_code="14",
                pollutant_name="Ozono",
            ),
            # Estación distinta, misma hora y contaminante.
            _silver_record(
                "28079016",
                "NO2",
                "2026-08-15T12:15:00+02:00",
                27.0,
                station_name="Arturo Soria",
            ),
        ]

    def test_groups_by_station_pollutant_and_hour(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)

        keys = {(r["station_id"], r["pollutant"], r["date"], r["hour"]) for r in gold}
        self.assertEqual(
            keys,
            {
                ("28079011", "NO2", "2026-08-15", 12),
                ("28079011", "NO2", "2026-08-15", 13),
                ("28079011", "O3", "2026-08-15", 12),
                ("28079016", "NO2", "2026-08-15", 12),
            },
        )

    def test_averages_and_extremes_are_correct_for_the_three_sample_bucket(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(
            r for r in gold if r["station_id"] == "28079011" and r["pollutant"] == "NO2" and r["hour"] == 12
        )

        self.assertEqual(bucket["samples_count"], 3)
        self.assertAlmostEqual(bucket["avg_value"], (25.0 + 27.0 + 23.0) / 3)
        self.assertEqual(bucket["max_value"], 27.0)
        self.assertEqual(bucket["min_value"], 23.0)
        self.assertEqual(bucket["first_measured_at"], "2026-08-15T12:00:00+02:00")
        self.assertEqual(bucket["last_measured_at"], "2026-08-15T12:55:00+02:00")
        self.assertEqual(bucket["station_name"], "Ramón y Cajal")
        self.assertEqual(bucket["unit"], "µg/m³")
        self.assertEqual(bucket["location"]["lat"], 40.4514734)

    def test_pollutant_bucket_does_not_mix_with_other_pollutant_same_station_and_hour(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        o3_bucket = next(r for r in gold if r["pollutant"] == "O3")

        self.assertEqual(o3_bucket["samples_count"], 1)
        self.assertEqual(o3_bucket["avg_value"], 68.0)
        self.assertEqual(o3_bucket["pollutant_name"], "Ozono")

    def test_single_sample_bucket_matches_its_only_record(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["station_id"] == "28079016")

        self.assertEqual(bucket["samples_count"], 1)
        self.assertEqual(bucket["avg_value"], 27.0)
        self.assertEqual(bucket["station_name"], "Arturo Soria")

    def test_records_without_measured_at_are_ignored(self):
        no_measured_at = _silver_record("28079099", "NO2", None, 25.0)
        gold = aggregate_silver_to_gold([no_measured_at], self.processed_at)
        self.assertEqual(gold, [])

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_silver_to_gold([], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
