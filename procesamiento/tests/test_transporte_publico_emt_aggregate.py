import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.transporte_publico_emt.aggregate import aggregate_silver_to_gold


def _silver_record(stop_id, line, ingested_at, estimate_arrive_sec, bus_id=1234):
    return {
        "schema_version": 1,
        "source": "madrid_emt_llegadas",
        "stop_id": stop_id,
        "line": line,
        "bus_id": bus_id,
        "destination": "AEROPUERTO",
        "ingested_at": ingested_at,
        "processed_at": ingested_at,
        "estimate_arrive_sec": estimate_arrive_sec,
        "distance_bus_m": 1000,
        "is_head": False,
        "deviation_sec": 0,
        "position_type_bus": "0",
        "location": {"lat": 40.4, "lon": -3.7, "srid": "EPSG:4326"},
    }


class AggregateSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 15, 12, 30, tzinfo=timezone.utc)
        self.records = [
            _silver_record("71", "203", "2026-08-15T10:05:00+02:00", 300),
            _silver_record("71", "203", "2026-08-15T10:10:00+02:00", 900),
            _silver_record("71", "203", "2026-08-15T10:55:00+02:00", 120),
            # Misma hora natural del día siguiente en Madrid, distinta hora del feed.
            _silver_record("71", "203", "2026-08-15T11:05:00+02:00", 480),
            # Misma parada, línea distinta, misma hora: no debe mezclarse.
            _silver_record("71", "N1", "2026-08-15T10:07:00+02:00", 600),
        ]

    def test_groups_by_stop_line_and_hour(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)

        keys = {(r["stop_id"], r["line"], r["date"], r["hour"]) for r in gold}
        self.assertEqual(
            keys,
            {
                ("71", "203", "2026-08-15", 10),
                ("71", "203", "2026-08-15", 11),
                ("71", "N1", "2026-08-15", 10),
            },
        )

    def test_averages_and_counts_are_correct_for_the_three_sample_bucket(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["line"] == "203" and r["hour"] == 10)

        self.assertEqual(bucket["samples_count"], 3)
        self.assertAlmostEqual(bucket["avg_estimate_arrive_sec"], (300 + 900 + 120) / 3)
        self.assertEqual(bucket["max_estimate_arrive_sec"], 900)
        self.assertEqual(bucket["min_estimate_arrive_sec"], 120)
        self.assertEqual(bucket["first_ingested_at"], "2026-08-15T10:05:00+02:00")
        self.assertEqual(bucket["last_ingested_at"], "2026-08-15T10:55:00+02:00")

    def test_different_lines_at_the_same_stop_are_not_mixed(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["line"] == "N1")

        self.assertEqual(bucket["samples_count"], 1)
        self.assertEqual(bucket["avg_estimate_arrive_sec"], 600)
        self.assertEqual(bucket["max_estimate_arrive_sec"], bucket["min_estimate_arrive_sec"])

    def test_records_without_ingested_at_are_ignored(self):
        broken = dict(self.records[0])
        broken["ingested_at"] = None
        gold = aggregate_silver_to_gold([broken], self.processed_at)
        self.assertEqual(gold, [])

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_silver_to_gold([], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
