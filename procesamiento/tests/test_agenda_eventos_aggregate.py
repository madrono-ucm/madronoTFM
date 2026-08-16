import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.agenda_eventos.aggregate import (
    UNKNOWN_CATEGORY,
    UNKNOWN_DISTRICT,
    aggregate_silver_to_gold,
)


def _silver_record(
    event_id,
    start_datetime,
    category="Exposiciones",
    district="Centro",
    source="agenda_eventos_madrid_municipal",
    free=True,
    title="Evento de prueba",
):
    return {
        "schema_version": 1,
        "source": source,
        "event_id": event_id,
        "title": title,
        "description": None,
        "category": category,
        "start_datetime": start_datetime,
        "end_datetime": start_datetime,
        "schedule_text": None,
        "free": free,
        "price_info": None,
        "venue_name": "Centro Cultural",
        "address": "CALLE FICTICIA 1",
        "district": district,
        "neighborhood": "Palacio",
        "postal_code": "28005",
        "lat": 40.41,
        "lon": -3.70,
        "url": "http://example.org/evento",
        "ingested_at": "2026-08-15T12:39:24+02:00",
        "processed_at": "2026-08-15T12:39:25+02:00",
    }


class AggregateSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)

    def test_groups_by_category_district_and_date(self):
        records = [
            _silver_record("e1", "2026-09-15T18:00:00", category="Exposiciones", district="Centro"),
            _silver_record("e2", "2026-09-15T20:00:00", category="Exposiciones", district="Centro"),
            _silver_record("e3", "2026-09-15T20:00:00", category="Música", district="Centro"),
            _silver_record("e4", "2026-09-15T20:00:00", category="Exposiciones", district="Retiro"),
            _silver_record("e5", "2026-09-16T20:00:00", category="Exposiciones", district="Centro"),
        ]

        gold = aggregate_silver_to_gold(records, self.processed_at)

        keys = {(r["category"], r["district"], r["date"]) for r in gold}
        self.assertEqual(
            keys,
            {
                ("Exposiciones", "Centro", "2026-09-15"),
                ("Música", "Centro", "2026-09-15"),
                ("Exposiciones", "Retiro", "2026-09-15"),
                ("Exposiciones", "Centro", "2026-09-16"),
            },
        )

    def test_events_count_deduplicates_reingested_event_id(self):
        records = [
            _silver_record("e1", "2026-09-15T18:00:00"),
            # Reingesta del mismo evento -- no debe contar dos veces.
            _silver_record("e1", "2026-09-15T18:00:00"),
            _silver_record("e2", "2026-09-15T20:00:00"),
        ]

        gold = aggregate_silver_to_gold(records, self.processed_at)
        self.assertEqual(len(gold), 1)
        bucket = gold[0]

        self.assertEqual(bucket["samples_count"], 3)
        self.assertEqual(bucket["events_count"], 2)
        self.assertEqual(bucket["first_start_datetime"], "2026-09-15T18:00:00")
        self.assertEqual(bucket["last_start_datetime"], "2026-09-15T20:00:00")

    def test_free_events_count_only_counts_distinct_free_events(self):
        records = [
            _silver_record("e1", "2026-09-15T18:00:00", free=True),
            _silver_record("e2", "2026-09-15T18:00:00", free=False),
            _silver_record("e3", "2026-09-15T18:00:00", free=None),
        ]

        gold = aggregate_silver_to_gold(records, self.processed_at)
        bucket = gold[0]

        self.assertEqual(bucket["events_count"], 3)
        self.assertEqual(bucket["free_events_count"], 1)

    def test_missing_category_and_district_use_sentinel_bucket(self):
        records = [_silver_record("e1", "2026-09-15T18:00:00", category=None, district=None)]

        gold = aggregate_silver_to_gold(records, self.processed_at)
        bucket = gold[0]

        self.assertEqual(bucket["category"], UNKNOWN_CATEGORY)
        self.assertEqual(bucket["district"], UNKNOWN_DISTRICT)

    def test_sources_lists_distinct_sources_present_in_bucket(self):
        records = [
            _silver_record("e1", "2026-09-15T18:00:00", source="agenda_eventos_madrid_municipal"),
            _silver_record("e2", "2026-09-15T18:00:00", source="agenda_turismo_esmadrid"),
        ]

        gold = aggregate_silver_to_gold(records, self.processed_at)
        bucket = gold[0]

        self.assertEqual(bucket["sources"], ["agenda_eventos_madrid_municipal", "agenda_turismo_esmadrid"])

    def test_date_only_start_datetime_is_bucketed_correctly(self):
        # Formato propio de esMadrid, sin hora.
        records = [_silver_record("e1", "2026-11-15", source="agenda_turismo_esmadrid")]

        gold = aggregate_silver_to_gold(records, self.processed_at)
        self.assertEqual(gold[0]["date"], "2026-11-15")

    def test_records_without_start_datetime_are_ignored(self):
        no_start = _silver_record("e1", None)
        gold = aggregate_silver_to_gold([no_start], self.processed_at)
        self.assertEqual(gold, [])

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_silver_to_gold([], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
