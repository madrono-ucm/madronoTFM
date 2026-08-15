import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.trafico.aggregate import aggregate_silver_to_gold


def _silver_record(point_id, measured_at, intensity, occupancy_ratio, load_ratio, service_level, subarea="Centro"):
    return {
        "schema_version": 1,
        "source": "madrid_trafico_intensidad",
        "point_id": point_id,
        "subarea": subarea,
        "measured_at": measured_at,
        "ingested_at": measured_at,
        "processed_at": measured_at,
        "location": {"lat": 40.4725, "lon": -3.7274, "srid_target": "EPSG:4326"},
        "intensity_vph": intensity,
        "occupancy_pct": None,
        "load_pct": None,
        "service_level": service_level,
        "saturation_intensity_vph": None,
        "occupancy_ratio": occupancy_ratio,
        "load_ratio": load_ratio,
        "intensity_ratio": None,
    }


class AggregateSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 15, 12, 30, tzinfo=timezone.utc)
        self.records = [
            _silver_record("1001", "2026-08-15T10:05:00+02:00", 900, 0.12, 0.20, 0),
            _silver_record("1001", "2026-08-15T10:10:00+02:00", 1100, 0.18, 0.25, 1),
            _silver_record("1001", "2026-08-15T10:55:00+02:00", 1000, 0.15, 0.22, 0),
            # Misma hora natural del día siguiente en la Madrid, distinta hora del feed.
            _silver_record("1001", "2026-08-15T11:05:00+02:00", 700, 0.08, 0.10, 0),
            # Punto distinto, misma hora.
            _silver_record("1002", "2026-08-15T10:07:00+02:00", 2200, 0.40, 0.55, 2, subarea="Chamartin"),
        ]

    def test_groups_by_point_and_hour(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)

        keys = {(r["point_id"], r["date"], r["hour"]) for r in gold}
        self.assertEqual(
            keys,
            {
                ("1001", "2026-08-15", 10),
                ("1001", "2026-08-15", 11),
                ("1002", "2026-08-15", 10),
            },
        )

    def test_averages_and_counts_are_correct_for_the_three_sample_bucket(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["point_id"] == "1001" and r["hour"] == 10)

        self.assertEqual(bucket["samples_count"], 3)
        self.assertAlmostEqual(bucket["avg_intensity_vph"], (900 + 1100 + 1000) / 3)
        self.assertEqual(bucket["max_intensity_vph"], 1100)
        self.assertEqual(bucket["min_intensity_vph"], 900)
        self.assertAlmostEqual(bucket["avg_occupancy_ratio"], (0.12 + 0.18 + 0.15) / 3)
        self.assertEqual(bucket["first_measured_at"], "2026-08-15T10:05:00+02:00")
        self.assertEqual(bucket["last_measured_at"], "2026-08-15T10:55:00+02:00")
        self.assertEqual(bucket["subarea"], "Centro")
        self.assertEqual(bucket["location"]["lat"], 40.4725)

    def test_single_sample_bucket_matches_its_only_record(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["point_id"] == "1002")

        self.assertEqual(bucket["samples_count"], 1)
        self.assertEqual(bucket["avg_intensity_vph"], 2200)
        self.assertEqual(bucket["max_intensity_vph"], bucket["min_intensity_vph"])

    def test_records_without_measured_at_are_ignored(self):
        broken = dict(self.records[0])
        broken["measured_at"] = None
        gold = aggregate_silver_to_gold([broken], self.processed_at)
        self.assertEqual(gold, [])

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_silver_to_gold([], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
