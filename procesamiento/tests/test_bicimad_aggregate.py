import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.bicimad.aggregate import aggregate_silver_to_gold


def _silver_record(
    station_id,
    measured_at,
    bikes_available,
    bikes_disabled,
    docks_available,
    docks_disabled,
    occupancy_ratio,
    docks_total=47,
    name="2 - Metro Callao",
):
    return {
        "schema_version": 1,
        "source": "bicimad_gbfs",
        "station_id": station_id,
        "name": name,
        "address": "Calle Miguel Moya nº 1",
        "measured_at": measured_at,
        "ingested_at": measured_at,
        "processed_at": measured_at,
        "bikes_available": bikes_available,
        "bikes_disabled": bikes_disabled,
        "docks_available": docks_available,
        "docks_disabled": docks_disabled,
        "docks_total": docks_total,
        "status": "IN_SERVICE",
        "is_renting": True,
        "is_returning": True,
        "occupancy_ratio": occupancy_ratio,
        "location": {"lat": 40.4204, "lon": -3.70569, "srid": "EPSG:4326"},
    }


class AggregateSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)
        self.records = [
            _silver_record("1406", "2026-08-15T12:05:00+02:00", 1, 5, 21, 0, 1 / 47),
            _silver_record("1406", "2026-08-15T12:20:00+02:00", 3, 5, 19, 0, 3 / 47),
            _silver_record("1406", "2026-08-15T12:55:00+02:00", 2, 5, 20, 0, 2 / 47),
            # Misma estación, hora distinta.
            _silver_record("1406", "2026-08-15T13:05:00+02:00", 4, 5, 18, 0, 4 / 47),
            # Estación distinta, misma hora.
            _silver_record(
                "1407", "2026-08-15T12:10:00+02:00", 1, 0, 18, 0, 1 / 39, docks_total=39, name="3 - Plaza Conde Suchil"
            ),
        ]

    def test_groups_by_station_and_hour(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)

        keys = {(r["station_id"], r["date"], r["hour"]) for r in gold}
        self.assertEqual(
            keys,
            {
                ("1406", "2026-08-15", 12),
                ("1406", "2026-08-15", 13),
                ("1407", "2026-08-15", 12),
            },
        )

    def test_averages_and_counts_are_correct_for_the_three_sample_bucket(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["station_id"] == "1406" and r["hour"] == 12)

        self.assertEqual(bucket["samples_count"], 3)
        self.assertAlmostEqual(bucket["avg_bikes_available"], (1 + 3 + 2) / 3)
        self.assertAlmostEqual(bucket["avg_bikes_disabled"], 5)
        self.assertAlmostEqual(bucket["avg_docks_available"], (21 + 19 + 20) / 3)
        self.assertAlmostEqual(bucket["avg_occupancy_ratio"], (1 / 47 + 3 / 47 + 2 / 47) / 3)
        self.assertEqual(bucket["docks_total"], 47)
        self.assertEqual(bucket["first_measured_at"], "2026-08-15T12:05:00+02:00")
        self.assertEqual(bucket["last_measured_at"], "2026-08-15T12:55:00+02:00")
        self.assertEqual(bucket["name"], "2 - Metro Callao")
        self.assertEqual(bucket["location"]["lat"], 40.4204)

    def test_single_sample_bucket_matches_its_only_record(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["station_id"] == "1407")

        self.assertEqual(bucket["samples_count"], 1)
        self.assertEqual(bucket["avg_bikes_available"], 1)
        self.assertEqual(bucket["docks_total"], 39)

    def test_records_without_measured_at_are_ignored(self):
        broken = dict(self.records[0])
        broken["measured_at"] = None
        gold = aggregate_silver_to_gold([broken], self.processed_at)
        self.assertEqual(gold, [])

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_silver_to_gold([], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
