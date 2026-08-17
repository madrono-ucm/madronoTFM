import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.bluesky_menciones.aggregate import (
    aggregate_silver_to_gold,
)


def _silver_record(
    mode,
    match_term,
    created_at,
    post_hash,
    text="Un post cualquiera sobre Madrid.",
    lang="es",
    like_count=0,
    repost_count=0,
    reply_count=0,
    quote_count=0,
):
    return {
        "schema_version": 1,
        "source": "bluesky_menciones_madrid",
        "mode": mode,
        "match_term": match_term,
        "post_hash": post_hash,
        "text": text,
        "lang": lang,
        "created_at": created_at,
        "indexed_at": created_at,
        "like_count": like_count,
        "repost_count": repost_count,
        "reply_count": reply_count,
        "quote_count": quote_count,
        "ingested_at": "2026-08-15T12:39:31+02:00",
        "processed_at": "2026-08-15T12:39:32+02:00",
    }


class AggregateSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
        self.records = [
            # Mismo modo/término/hora, tres posts distintos.
            _silver_record(
                "bajo_demanda",
                "Puerta del Sol",
                "2026-08-15T10:05:00Z",
                "p1",
                like_count=10,
                repost_count=2,
            ),
            _silver_record(
                "bajo_demanda",
                "Puerta del Sol",
                "2026-08-15T10:40:00Z",
                "p2",
                lang="en",
                like_count=5,
            ),
            _silver_record("bajo_demanda", "Puerta del Sol", "2026-08-15T10:58:00Z", "p3"),
            # Reingesta del post "p1" (mismo post_hash) en el mismo bucket --
            # no debe contar como una cuarta mención distinta.
            _silver_record("bajo_demanda", "Puerta del Sol", "2026-08-15T10:05:00Z", "p1"),
            # Mismo término, otra hora: bucket separado.
            _silver_record("bajo_demanda", "Puerta del Sol", "2026-08-15T11:10:00Z", "p4"),
            # Mismo término/hora, pero otro modo: bucket separado (el
            # enunciado pide "separado por mode").
            _silver_record("distrito_sweep", "Puerta del Sol", "2026-08-15T10:15:00Z", "p5"),
            # Otro término, misma hora.
            _silver_record("distrito_sweep", "Centro", "2026-08-15T10:20:00Z", "p6"),
        ]

    def test_groups_by_mode_match_term_date_and_hour(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)

        keys = {(r["mode"], r["match_term"], r["date"], r["hour"]) for r in gold}
        self.assertEqual(
            keys,
            {
                ("bajo_demanda", "Puerta del Sol", "2026-08-15", 10),
                ("bajo_demanda", "Puerta del Sol", "2026-08-15", 11),
                ("distrito_sweep", "Puerta del Sol", "2026-08-15", 10),
                ("distrito_sweep", "Centro", "2026-08-15", 10),
            },
        )

    def test_mentions_count_deduplicates_reingested_post_hash(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(
            r
            for r in gold
            if r["mode"] == "bajo_demanda" and r["match_term"] == "Puerta del Sol" and r["hour"] == 10
        )

        # 4 filas Silver (p1 reingestado + p2 + p3), pero solo 3 posts
        # distintos (p1, p2, p3).
        self.assertEqual(bucket["samples_count"], 4)
        self.assertEqual(bucket["mentions_count"], 3)
        self.assertEqual(bucket["langs"], ["en", "es"])
        self.assertEqual(bucket["first_created_at"], "2026-08-15T10:05:00+00:00")
        self.assertEqual(bucket["last_created_at"], "2026-08-15T10:58:00+00:00")

    def test_engagement_counts_are_summed_per_bucket(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(
            r
            for r in gold
            if r["mode"] == "bajo_demanda" and r["match_term"] == "Puerta del Sol" and r["hour"] == 10
        )

        # p1 (like=10, repost=2) + p2 (like=5) + p3 (0) + p1 reingestado (sin
        # contadores propios en este fixture, cuenta como 0/0): la suma no
        # deduplica por post_hash, a diferencia de mentions_count -- cada
        # fila Silver aporta su propio engagement, incluidas reingestas.
        self.assertEqual(bucket["total_like_count"], 15)
        self.assertEqual(bucket["total_repost_count"], 2)
        self.assertEqual(bucket["total_reply_count"], 0)
        self.assertEqual(bucket["total_quote_count"], 0)

    def test_same_term_different_mode_is_a_separate_bucket(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["mode"] == "distrito_sweep" and r["match_term"] == "Puerta del Sol")

        self.assertEqual(bucket["mentions_count"], 1)

    def test_records_without_created_at_are_ignored(self):
        no_created_at = _silver_record("bajo_demanda", "Retiro", None, "p99")
        gold = aggregate_silver_to_gold([no_created_at], self.processed_at)
        self.assertEqual(gold, [])

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_silver_to_gold([], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
