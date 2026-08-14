"""Tests del productor de la agenda de grandes recintos de Madrid.

No hacen ninguna llamada de red: usan el fixture
`fixtures/agenda_recintos_madrid_sample.xml`, un extracto de 7 `<service>`
reales del feed de esMadrid (uno por cada uno de los 6 recintos cubiertos,
más `"Teatro de la Zarzuela"` como señuelo para comprobar que el filtro del
Hipódromo de la Zarzuela no lo confunde con otro recinto).
"""

import json
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.agenda_recintos_madrid import (
    SOURCE_NAME,
    UNAVAILABLE_VENUES,
    VENUES,
    _infer_event_type,
    fetch_venue_agenda,
    normalize_venue_event,
)
from ingesta.capturas.agenda_eventos_madrid import SOURCE_ESMADRID

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_PATH = FIXTURES_DIR / "agenda_recintos_madrid_sample.xml"


def _load_services():
    root = ET.parse(FIXTURE_PATH).getroot()
    return root.findall("service")


class InferEventTypeTests(unittest.TestCase):
    def test_deporte(self):
        self.assertEqual(_infer_event_type("Eventos > Deporte > Fútbol"), "deporte")

    def test_concierto(self):
        self.assertEqual(_infer_event_type("Eventos > Música > Pop-rock"), "concierto")

    def test_otro(self):
        self.assertEqual(_infer_event_type("Eventos > Ferias > Moda y complementos"), "otro")

    def test_none_category(self):
        self.assertIsNone(_infer_event_type(None))

    def test_single_segment_category(self):
        self.assertEqual(_infer_event_type("Eventos"), "otro")


class NormalizeVenueEventTests(unittest.TestCase):
    def setUp(self):
        self.services = {
            (s.find("basicData/nombrert").text or "").strip(): s for s in _load_services()
        }
        self.captured_at = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)

    def test_normalizes_a_football_match_at_bernabeu(self):
        service = self.services["Estadio Bernabéu"]
        record = normalize_venue_event(service, VENUES["bernabeu"], self.captured_at)
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], SOURCE_NAME)
        self.assertEqual(record["upstream_source"], SOURCE_ESMADRID)
        self.assertEqual(record["venue_id"], "bernabeu")
        self.assertIn("Bernabéu", record["venue_name"])
        self.assertIn("Real Madrid", record["title"])
        self.assertEqual(record["event_type"], "deporte")
        self.assertIsNotNone(record["start_datetime"])
        self.assertIsNone(record["capacity"])
        self.assertEqual(record["captured_at"], "2026-08-14T12:00:00+00:00")

    def test_normalizes_a_concert_at_movistar_arena(self):
        service = self.services["Movistar Arena"]
        record = normalize_venue_event(service, VENUES["movistar_arena"], self.captured_at)
        self.assertEqual(record["venue_id"], "movistar_arena")

    def test_normalizes_a_fair_at_ifema(self):
        service = self.services["IFEMA MADRID"]
        record = normalize_venue_event(service, VENUES["ifema_madrid"], self.captured_at)
        self.assertEqual(record["venue_id"], "ifema_madrid")

    def test_records_are_json_serializable(self):
        for name, venue in [
            ("Estadio Bernabéu", VENUES["bernabeu"]),
            ("Estadio Riyadh Air Metropolitano", VENUES["metropolitano"]),
            ("Caja Mágica", VENUES["caja_magica"]),
        ]:
            record = normalize_venue_event(self.services[name], venue, self.captured_at)
            json.dumps(record)


class FetchVenueAgendaTests(unittest.TestCase):
    """Ejercita `fetch_venue_agenda` completo (filtrado incluido) pasando `services` en memoria."""

    def setUp(self):
        self.services = _load_services()
        self.captured_at = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)

    def test_filters_only_matching_venue(self):
        records = fetch_venue_agenda(
            "metropolitano", services=self.services, captured_at=self.captured_at
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["venue_id"], "metropolitano")

    def test_hipodromo_filter_does_not_match_teatro_de_la_zarzuela(self):
        """El fixture incluye 'Teatro de la Zarzuela' como señuelo: no debe colarse en el Hipódromo."""
        records = fetch_venue_agenda(
            "hipodromo_zarzuela", services=self.services, captured_at=self.captured_at
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["venue_id"], "hipodromo_zarzuela")

    def test_unknown_venue_raises(self):
        with self.assertRaises(ValueError):
            fetch_venue_agenda("recinto-inventado", services=self.services)

    def test_wizink_center_raises_with_redirect_message(self):
        with self.assertRaises(ValueError) as ctx:
            fetch_venue_agenda("wizink_center", services=self.services)
        self.assertIn("movistar_arena", str(ctx.exception))

    def test_limit_truncates_results(self):
        records = fetch_venue_agenda(
            "ifema_madrid", services=self.services, captured_at=self.captured_at, limit=0
        )
        self.assertEqual(records, [])


class SweepAllVenuesTests(unittest.TestCase):
    def test_sweep_covers_every_venue_present_in_fixture(self):
        services = _load_services()
        captured_at = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)
        # sweep_all_venues siempre re-descarga el feed completo; para el test se
        # ejercita fetch_venue_agenda por recinto con los mismos `services`, que es
        # exactamente lo que hace sweep_all_venues internamente.
        records = []
        for venue_id in VENUES:
            records.extend(fetch_venue_agenda(venue_id, services=services, captured_at=captured_at))

        found_venue_ids = {r["venue_id"] for r in records}
        self.assertEqual(found_venue_ids, set(VENUES))
        self.assertEqual(len(records), 6)  # uno por cada recinto presente en el fixture


class UnavailableVenuesTests(unittest.TestCase):
    def test_wizink_center_documented_as_unavailable(self):
        self.assertIn("wizink_center", UNAVAILABLE_VENUES)
        self.assertNotIn("wizink_center", VENUES)


class SampleFixtureTests(unittest.TestCase):
    """Verifica que la muestra commiteada en `capturas/samples/` es válida."""

    def test_committed_sample_matches_schema_and_covers_several_venues(self):
        sample_path = (
            Path(__file__).parent.parent / "capturas" / "samples" / "agenda_recintos_madrid_sample.json"
        )
        records = json.loads(sample_path.read_text(encoding="utf-8"))

        self.assertGreater(len(records), 0)
        venue_ids = {record["venue_id"] for record in records}
        self.assertGreaterEqual(len(venue_ids), 2)
        self.assertTrue(venue_ids.issubset(set(VENUES)))

        required_keys = {
            "schema_version",
            "source",
            "upstream_source",
            "venue_id",
            "venue_name",
            "event_id",
            "title",
            "event_type",
            "category",
            "start_datetime",
            "end_datetime",
            "schedule_text",
            "capacity",
            "url",
            "captured_at",
        }
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], SOURCE_NAME)
            self.assertTrue(required_keys.issubset(record.keys()))


if __name__ == "__main__":
    unittest.main()
