import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.afluencia_lugares.aggregate import aggregate_silver_to_gold

PROCESSED_AT = datetime(2026, 8, 13, 15, 0, 0, tzinfo=timezone.utc)

# 2026-08-13 es jueves.
TYPICAL_BY_HOUR = {
    "lunes": [0] * 24,
    "martes": [0] * 24,
    "miercoles": [0] * 24,
    "jueves": [0] * 14 + [48, 58, 63, 61, 53, 51, 55, 63, 68, 63],
    "viernes": [0] * 24,
    "sabado": [0] * 24,
    "domingo": [0] * 24,
}


def _silver_record(**overrides) -> dict:
    record = {
        "schema_version": 1,
        "source": "google_populartimes",
        "place_id": "ChIJi7xhMz0nQg0RVeMHylTfhY4",
        "name": "Puerta del Sol",
        "query": "Puerta del Sol, Madrid",
        "address": "Puerta del Sol, 28013 Madrid, Spain",
        "lat": 40.4169473,
        "lon": -3.7035285,
        "live_pct": 72,
        "typical_by_hour": TYPICAL_BY_HOUR,
        "ingested_at": "2026-08-13T14:30:00+02:00",
        "processed_at": "2026-08-13T14:30:00+02:00",
    }
    record.update(overrides)
    return record


class AggregateSilverToGoldTests(unittest.TestCase):
    def test_groups_by_place_date_and_hour(self):
        gold = aggregate_silver_to_gold([_silver_record()], PROCESSED_AT)

        self.assertEqual(len(gold), 1)
        row = gold[0]
        self.assertEqual(row["place_id"], "ChIJi7xhMz0nQg0RVeMHylTfhY4")
        self.assertEqual(row["name"], "Puerta del Sol")
        self.assertEqual(row["date"], "2026-08-13")
        self.assertEqual(row["hour"], 14)
        self.assertEqual(row["day_of_week"], "jueves")
        self.assertEqual(row["samples_count"], 1)
        self.assertEqual(row["avg_live_pct"], 72)
        # typical_by_hour["jueves"][14] == 48 (ver TYPICAL_BY_HOUR arriba).
        self.assertEqual(row["typical_pct"], 48)
        self.assertEqual(row["lat"], 40.4169473)
        self.assertEqual(row["lon"], -3.7035285)

    def test_averages_live_pct_and_typical_pct_across_bucket(self):
        records = [
            _silver_record(live_pct=72, ingested_at="2026-08-13T14:10:00+02:00"),
            _silver_record(live_pct=88, ingested_at="2026-08-13T14:50:00+02:00"),
        ]

        gold = aggregate_silver_to_gold(records, PROCESSED_AT)

        self.assertEqual(len(gold), 1)
        self.assertEqual(gold[0]["samples_count"], 2)
        self.assertEqual(gold[0]["avg_live_pct"], 80)
        self.assertEqual(gold[0]["typical_pct"], 48)

    def test_null_live_pct_is_excluded_from_average_not_the_whole_bucket(self):
        records = [
            _silver_record(live_pct=72),
            _silver_record(live_pct=None, ingested_at="2026-08-13T14:45:00+02:00"),
        ]

        gold = aggregate_silver_to_gold(records, PROCESSED_AT)

        self.assertEqual(len(gold), 1)
        self.assertEqual(gold[0]["samples_count"], 2)
        self.assertEqual(gold[0]["avg_live_pct"], 72)

    def test_null_live_pct_and_typical_by_hour_produce_null_metrics_not_a_dropped_bucket(self):
        # Caso real de muestra: "Plaza Mayor" (live_pct y typical_by_hour
        # ambos null) -- sigue produciendo una fila de Gold, con las
        # métricas a null en vez de descartarse.
        record = _silver_record(name="Plaza Mayor", live_pct=None, typical_by_hour=None)

        gold = aggregate_silver_to_gold([record], PROCESSED_AT)

        self.assertEqual(len(gold), 1)
        self.assertEqual(gold[0]["samples_count"], 1)
        self.assertIsNone(gold[0]["avg_live_pct"])
        self.assertIsNone(gold[0]["typical_pct"])

    def test_different_hours_for_same_place_are_separate_rows(self):
        records = [
            _silver_record(ingested_at="2026-08-13T14:30:00+02:00"),
            _silver_record(ingested_at="2026-08-13T20:30:00+02:00"),
        ]

        gold = aggregate_silver_to_gold(records, PROCESSED_AT)

        hours = {row["hour"] for row in gold}
        self.assertEqual(hours, {14, 20})
        self.assertEqual(len(gold), 2)

    def test_different_places_on_same_date_and_hour_are_separate_rows(self):
        records = [
            _silver_record(place_id="place-a", name="Lugar A"),
            _silver_record(place_id="place-b", name="Lugar B"),
        ]

        gold = aggregate_silver_to_gold(records, PROCESSED_AT)

        place_ids = {row["place_id"] for row in gold}
        self.assertEqual(place_ids, {"place-a", "place-b"})
        self.assertEqual(len(gold), 2)

    def test_first_and_last_ingested_at_span_the_bucket(self):
        records = [
            _silver_record(ingested_at="2026-08-13T14:50:00+02:00"),
            _silver_record(ingested_at="2026-08-13T14:10:00+02:00"),
        ]

        gold = aggregate_silver_to_gold(records, PROCESSED_AT)

        self.assertEqual(len(gold), 1)
        self.assertEqual(gold[0]["first_ingested_at"], "2026-08-13T14:10:00+02:00")
        self.assertEqual(gold[0]["last_ingested_at"], "2026-08-13T14:50:00+02:00")

    def test_records_without_place_id_or_ingested_at_are_ignored(self):
        records = [
            _silver_record(place_id=None),
            _silver_record(ingested_at=None),
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
