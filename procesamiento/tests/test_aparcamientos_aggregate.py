import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.aparcamientos.aggregate import aggregate_silver_to_gold


def _silver_record(
    parking_id,
    measured_at,
    free_spaces,
    total_spaces,
    occupancy_ratio,
    name="Nuestra Señora del Recuerdo",
):
    return {
        "schema_version": 1,
        "source": "madrid_aparcamientos_rotacionales",
        "parking_id": parking_id,
        "name": name,
        "address": "Calle de la Hiedra",
        "measured_at": measured_at,
        "ingested_at": measured_at,
        "processed_at": measured_at,
        "free_spaces": free_spaces,
        "total_spaces": total_spaces,
        "occupancy_ratio": occupancy_ratio,
        "location": {"lat": 40.472181, "lon": -3.67916, "srid": "EPSG:4326"},
    }


class AggregateSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)
        self.records = [
            _silver_record("5", "2026-08-15T12:05:00+02:00", 300, 832, 300 / 832),
            _silver_record("5", "2026-08-15T12:20:00+02:00", 320, 832, 320 / 832),
            _silver_record("5", "2026-08-15T12:55:00+02:00", 333, 832, 333 / 832),
            # Mismo aparcamiento, hora distinta.
            _silver_record("5", "2026-08-15T13:05:00+02:00", 340, 832, 340 / 832),
            # Aparcamiento distinto, misma hora.
            _silver_record(
                "7", "2026-08-15T12:10:00+02:00", 301, 432, 301 / 432, name="Avenida de Portugal"
            ),
        ]

    def test_groups_by_parking_and_hour(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)

        keys = {(r["parking_id"], r["date"], r["hour"]) for r in gold}
        self.assertEqual(
            keys,
            {
                ("5", "2026-08-15", 12),
                ("5", "2026-08-15", 13),
                ("7", "2026-08-15", 12),
            },
        )

    def test_averages_and_counts_are_correct_for_the_three_sample_bucket(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["parking_id"] == "5" and r["hour"] == 12)

        self.assertEqual(bucket["samples_count"], 3)
        self.assertAlmostEqual(bucket["avg_free_spaces"], (300 + 320 + 333) / 3)
        self.assertAlmostEqual(
            bucket["avg_occupancy_ratio"], (300 / 832 + 320 / 832 + 333 / 832) / 3
        )
        self.assertEqual(bucket["total_spaces"], 832)
        self.assertEqual(bucket["first_measured_at"], "2026-08-15T12:05:00+02:00")
        self.assertEqual(bucket["last_measured_at"], "2026-08-15T12:55:00+02:00")
        self.assertEqual(bucket["name"], "Nuestra Señora del Recuerdo")
        self.assertEqual(bucket["location"]["lat"], 40.472181)

    def test_single_sample_bucket_matches_its_only_record(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["parking_id"] == "7")

        self.assertEqual(bucket["samples_count"], 1)
        self.assertEqual(bucket["avg_free_spaces"], 301)
        self.assertEqual(bucket["total_spaces"], 432)

    def test_records_without_measured_at_are_ignored(self):
        no_occupancy = _silver_record("8", None, None, None, None)
        gold = aggregate_silver_to_gold([no_occupancy], self.processed_at)
        self.assertEqual(gold, [])

    def test_bucket_with_partial_occupancy_samples_averages_only_present_values(self):
        partial = [
            _silver_record("9", "2026-08-15T12:05:00+02:00", 100, 200, 100 / 200),
            # Ocupación no compartida en esta muestra concreta.
            _silver_record("9", "2026-08-15T12:40:00+02:00", None, None, None),
        ]

        gold = aggregate_silver_to_gold(partial, self.processed_at)
        bucket = next(r for r in gold if r["parking_id"] == "9")

        self.assertEqual(bucket["samples_count"], 2)
        self.assertEqual(bucket["avg_free_spaces"], 100)
        self.assertAlmostEqual(bucket["avg_occupancy_ratio"], 100 / 200)
        self.assertEqual(bucket["total_spaces"], 200)

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_silver_to_gold([], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
