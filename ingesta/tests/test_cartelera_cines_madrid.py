"""Tests del productor de cartelera y horarios de cines de Madrid.

No hacen ninguna llamada de red: usan los fixtures
`fixtures/sensacine_cine_showtimes_sample.html` (extracto real de la ficha
de Cinesa Proyecciones en sensacine.com, incluyendo el defecto real de la
fuente de una versión de idioma duplicada) y
`fixtures/sensacine_estrenos_sample.html` (extracto real de la página de
estrenos de la semana), ambos descargados en vivo durante la sesión de la
tarea 023.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from ingesta.capturas.cartelera_cines_madrid import (
    CINEMAS,
    DEFAULT_SAMPLE_PATH,
    SOURCE_NAME,
    _parse_duration_minutes,
    _parse_language_version,
    _parse_spanish_date,
    fetch_cinema_showtimes,
    normalize_premiere,
    sweep_premieres,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SHOWTIMES_FIXTURE_PATH = FIXTURES_DIR / "sensacine_cine_showtimes_sample.html"
PREMIERES_FIXTURE_PATH = FIXTURES_DIR / "sensacine_estrenos_sample.html"

CAPTURED_AT = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)


def _load_showtimes_html() -> str:
    return SHOWTIMES_FIXTURE_PATH.read_text(encoding="utf-8")


def _load_premieres_html() -> str:
    return PREMIERES_FIXTURE_PATH.read_text(encoding="utf-8")


class ParseLanguageVersionTests(unittest.TestCase):
    def test_extracts_version_after_date(self):
        text = "13 de agosto de 2026 -\n                En Versión doblada"
        self.assertEqual(_parse_language_version(text), "En Versión doblada")

    def test_handles_text_without_separator(self):
        self.assertEqual(_parse_language_version("  En V.O.S.E.  "), "En V.O.S.E.")


class ParseDurationMinutesTests(unittest.TestCase):
    def test_hours_and_minutes(self):
        self.assertEqual(_parse_duration_minutes("14 de agosto de 2026 | 1h 40min | Acción"), 100)

    def test_minutes_only(self):
        self.assertEqual(_parse_duration_minutes("45min"), 45)

    def test_no_duration_present(self):
        self.assertIsNone(_parse_duration_minutes("sin duración aquí"))


class ParseSpanishDateTests(unittest.TestCase):
    def test_parses_real_format(self):
        self.assertEqual(_parse_spanish_date("14 de agosto de 2026"), "2026-08-14")

    def test_unknown_format_returns_none(self):
        self.assertIsNone(_parse_spanish_date("2026-08-14"))


class FetchCinemaShowtimesTests(unittest.TestCase):
    def setUp(self):
        self.html = _load_showtimes_html()

    def test_parses_theater_info_from_jsonld(self):
        records = fetch_cinema_showtimes("cinesa_proyecciones", html=self.html, captured_at=CAPTURED_AT)
        self.assertTrue(records)
        first = records[0]
        self.assertEqual(first["cinema_name"], "Cinesa Proyecciones")
        self.assertEqual(first["address"], "Calle de Fuencarral 136")
        self.assertEqual(first["postal_code"], "28001")
        self.assertEqual(first["locality"], "Madrid")
        self.assertEqual(first["screen_count"], 8)
        self.assertEqual(first["chain"], "cinesa")
        self.assertEqual(first["source"], SOURCE_NAME)

    def test_deduplicates_repeated_showtime_id_from_source_defect(self):
        # El fixture reproduce a propósito la duplicación real de la fuente
        # (mismo bloque V.O.S.E. de Spider-Man repetido dos veces, mismo
        # data-showtime-id="78986207474"). Debe aparecer una sola vez.
        records = fetch_cinema_showtimes("cinesa_proyecciones", html=self.html, captured_at=CAPTURED_AT)
        showtime_ids = [r["showtime_id"] for r in records]
        self.assertEqual(len(showtime_ids), len(set(showtime_ids)))
        self.assertEqual(showtime_ids.count("78986207474"), 1)

    def test_records_sorted_by_showtime_datetime(self):
        records = fetch_cinema_showtimes("cinesa_proyecciones", html=self.html, captured_at=CAPTURED_AT)
        datetimes = [r["showtime_datetime"] for r in records]
        self.assertEqual(datetimes, sorted(datetimes))

    def test_includes_both_movies_from_fixture(self):
        records = fetch_cinema_showtimes("cinesa_proyecciones", html=self.html, captured_at=CAPTURED_AT)
        titles = {r["movie_title"] for r in records}
        self.assertEqual(titles, {"El último mono", "Spider-Man: Brand New Day"})

    def test_limit_truncates_results(self):
        records = fetch_cinema_showtimes("cinesa_proyecciones", html=self.html, captured_at=CAPTURED_AT, limit=1)
        self.assertEqual(len(records), 1)

    def test_unknown_cinema_raises(self):
        with self.assertRaises(ValueError):
            fetch_cinema_showtimes("cine_inexistente", html=self.html)

    def test_records_are_json_serializable(self):
        records = fetch_cinema_showtimes("cinesa_proyecciones", html=self.html, captured_at=CAPTURED_AT)
        json.dumps(records, ensure_ascii=False)


class SweepPremieresTests(unittest.TestCase):
    def setUp(self):
        self.html = _load_premieres_html()

    def test_parses_all_premieres_in_fixture(self):
        records = sweep_premieres(html=self.html, captured_at=CAPTURED_AT)
        self.assertEqual(len(records), 3)
        titles = {r["movie_title"] for r in records}
        self.assertEqual(titles, {"El final de Oak Street", "Cuentra atrás", "Días de agosto"})

    def test_multi_genre_movie(self):
        records = sweep_premieres(html=self.html, captured_at=CAPTURED_AT)
        by_title = {r["movie_title"]: r for r in records}
        self.assertEqual(by_title["Cuentra atrás"]["genres"], ["Acción", "Suspense"])
        self.assertEqual(by_title["Cuentra atrás"]["duration_minutes"], 97)
        self.assertEqual(by_title["Cuentra atrás"]["release_date"], "2026-08-14")

    def test_single_genre_movie(self):
        records = sweep_premieres(html=self.html, captured_at=CAPTURED_AT)
        by_title = {r["movie_title"]: r for r in records}
        self.assertEqual(by_title["Días de agosto"]["genres"], ["Drama"])

    def test_limit_truncates_results(self):
        records = sweep_premieres(html=self.html, captured_at=CAPTURED_AT, limit=1)
        self.assertEqual(len(records), 1)

    def test_records_are_json_serializable(self):
        records = sweep_premieres(html=self.html, captured_at=CAPTURED_AT)
        json.dumps(records, ensure_ascii=False)


class NormalizePremiereTests(unittest.TestCase):
    def test_card_without_title_link_returns_none(self):
        soup = BeautifulSoup("<div class='card entity-card'></div>", "html.parser")
        card = soup.select_one(".card")
        self.assertIsNone(normalize_premiere(card, CAPTURED_AT))


class SampleFixtureTests(unittest.TestCase):
    def test_committed_sample_matches_schema_and_covers_both_chains(self):
        records = json.loads(DEFAULT_SAMPLE_PATH.read_text(encoding="utf-8"))
        self.assertGreater(len(records), 0)

        showtimes = [r for r in records if "showtime_id" in r]
        premieres = [r for r in records if r.get("record_type") == "estreno_semana"]
        self.assertTrue(showtimes)
        self.assertTrue(premieres)

        chains = {r["chain"] for r in showtimes}
        self.assertEqual(chains, {"cinesa", "yelmo"})

        for record in showtimes:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], SOURCE_NAME)
            self.assertIn(record["cinema_id"], CINEMAS)
            self.assertTrue(record["movie_title"])
            self.assertTrue(record["showtime_datetime"])
            self.assertTrue(record["showtime_id"])

        for record in premieres:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], SOURCE_NAME)
            self.assertTrue(record["movie_title"])
            self.assertTrue(record["release_date"])


if __name__ == "__main__":
    unittest.main()
