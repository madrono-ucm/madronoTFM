import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.cartelera_cines_estrenos.aggregate import (
    aggregate_silver_to_gold,
)


def _silver_record(
    movie_url,
    cinema_id,
    showtime_datetime,
    showtime_id,
    movie_title="Toy Story 5",
    chain="cinesa",
    cinema_name="Cinesa Proyecciones",
    language_version="En Versión doblada",
):
    return {
        "schema_version": 1,
        "source": "cartelera_cines_madrid",
        "cinema_id": cinema_id,
        "chain": chain,
        "cinema_name": cinema_name,
        "address": "Calle de Fuencarral 136",
        "postal_code": "28001",
        "locality": "Madrid",
        "screen_count": 8,
        "movie_title": movie_title,
        "movie_url": movie_url,
        "language_version": language_version,
        "experiences": ["Format.Projection.Digital"],
        "showtime_datetime": showtime_datetime,
        "showtime_id": showtime_id,
        "ingested_at": "2026-08-15T12:39:30+02:00",
        "processed_at": "2026-08-15T12:39:31+02:00",
    }


TOY_STORY_URL = "https://www.sensacine.com/peliculas/pelicula-313256/"
SPIDERMAN_URL = "https://www.sensacine.com/peliculas/pelicula-276608/"


class AggregateSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
        self.records = [
            # Misma película/cine/día, tres sesiones distintas.
            _silver_record(TOY_STORY_URL, "cinesa_proyecciones", "2026-08-15T16:15:00+02:00", "s1"),
            _silver_record(
                TOY_STORY_URL,
                "cinesa_proyecciones",
                "2026-08-15T19:00:00+02:00",
                "s2",
                language_version="En V.O.S.E.",
            ),
            _silver_record(TOY_STORY_URL, "cinesa_proyecciones", "2026-08-15T21:30:00+02:00", "s3"),
            # Misma película, mismo cine, mismo día, pero reingesta de la
            # sesión "s1" (mismo showtime_id) -- no debe contar como una
            # cuarta sesión distinta.
            _silver_record(TOY_STORY_URL, "cinesa_proyecciones", "2026-08-15T16:15:00+02:00", "s1"),
            # Misma película, otro cine, mismo día: no debe mezclarse con
            # las sesiones de "cinesa_proyecciones".
            _silver_record(
                TOY_STORY_URL,
                "yelmo_ideal",
                "2026-08-15T13:10:00+02:00",
                "s4",
                cinema_name="Yelmo Cines Ideal",
                chain="yelmo",
            ),
            # Otra película, mismo cine, mismo día.
            _silver_record(
                SPIDERMAN_URL,
                "cinesa_proyecciones",
                "2026-08-15T15:50:00+02:00",
                "s5",
                movie_title="Spider-Man: Brand New Day",
            ),
        ]

    def test_groups_by_movie_cinema_and_date(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)

        keys = {(r["movie_url"], r["cinema_id"], r["date"]) for r in gold}
        self.assertEqual(
            keys,
            {
                (TOY_STORY_URL, "cinesa_proyecciones", "2026-08-15"),
                (TOY_STORY_URL, "yelmo_ideal", "2026-08-15"),
                (SPIDERMAN_URL, "cinesa_proyecciones", "2026-08-15"),
            },
        )

    def test_sessions_count_deduplicates_reingested_showtime_id(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(
            r for r in gold if r["movie_url"] == TOY_STORY_URL and r["cinema_id"] == "cinesa_proyecciones"
        )

        # 4 filas Silver (s1 reingestada + s2 + s3), pero solo 3 sesiones
        # distintas (s1, s2, s3).
        self.assertEqual(bucket["samples_count"], 4)
        self.assertEqual(bucket["sessions_count"], 3)
        self.assertEqual(bucket["first_showtime_datetime"], "2026-08-15T16:15:00+02:00")
        self.assertEqual(bucket["last_showtime_datetime"], "2026-08-15T21:30:00+02:00")
        self.assertEqual(bucket["language_versions"], ["En V.O.S.E.", "En Versión doblada"])
        self.assertEqual(bucket["movie_title"], "Toy Story 5")

    def test_same_movie_different_cinema_is_a_separate_bucket(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["cinema_id"] == "yelmo_ideal")

        self.assertEqual(bucket["sessions_count"], 1)
        self.assertEqual(bucket["cinema_name"], "Yelmo Cines Ideal")

    def test_different_movie_same_cinema_is_a_separate_bucket(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["movie_url"] == SPIDERMAN_URL)

        self.assertEqual(bucket["sessions_count"], 1)
        self.assertEqual(bucket["movie_title"], "Spider-Man: Brand New Day")

    def test_records_without_showtime_datetime_are_ignored(self):
        no_showtime = _silver_record(TOY_STORY_URL, "cinesa_proyecciones", None, "s99")
        gold = aggregate_silver_to_gold([no_showtime], self.processed_at)
        self.assertEqual(gold, [])

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_silver_to_gold([], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
