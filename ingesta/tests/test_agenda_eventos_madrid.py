"""Tests del productor de la agenda de eventos culturales de Madrid.

No hacen ninguna llamada de red: usan los fixtures
`fixtures/agenda_eventos_madrid_municipal_sample.json` (un subconjunto real
de 3 eventos del catálogo JSON-LD de datos.madrid.es, incluyendo un evento
sin `@type` ni `address`/`location`, para probar los casos ausentes) y
`fixtures/agenda_turismo_esmadrid_sample.xml` (2 `<service>` reales del XML
de esmadrid.com, uno con recurrencia con exclusión/inclusión de fechas).
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.agenda_eventos_madrid import (
    SOURCE_ESMADRID,
    SOURCE_MUNICIPAL,
    normalize_esmadrid_event,
    normalize_municipal_event,
    parse_esmadrid_xml,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MUNICIPAL_FIXTURE_PATH = FIXTURES_DIR / "agenda_eventos_madrid_municipal_sample.json"
ESMADRID_FIXTURE_PATH = FIXTURES_DIR / "agenda_turismo_esmadrid_sample.xml"


class NormalizeMunicipalEventTests(unittest.TestCase):
    def setUp(self):
        payload = json.loads(MUNICIPAL_FIXTURE_PATH.read_text(encoding="utf-8"))
        self.raw_events = payload["@graph"]
        self.captured_at = datetime(2026, 8, 13, 18, 0, 0, tzinfo=timezone.utc)

    def test_normalizes_a_full_event_with_subcategory_type(self):
        record = normalize_municipal_event(self.raw_events[0], self.captured_at)
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], SOURCE_MUNICIPAL)
        self.assertEqual(record["event_id"], "50369523")
        self.assertEqual(record["title"], "35 edición del Festival de Cine de Madrid")
        self.assertEqual(record["category"], "ProgramacionDestacadaAgendaCultura")
        self.assertEqual(record["start_datetime"], "2026-09-15T00:00:00")
        self.assertEqual(record["end_datetime"], "2026-09-20T23:59:00")
        self.assertEqual(record["free"], False)
        self.assertEqual(record["location"]["venue_name"], "Cineteca Madrid")
        self.assertEqual(record["location"]["address"], "PLAZA LEGAZPI 8")
        self.assertEqual(record["location"]["district"], "Arganzuela")
        self.assertEqual(record["location"]["neighborhood"], "Chopera")
        self.assertEqual(record["location"]["postal_code"], "28045")
        self.assertAlmostEqual(record["location"]["lat"], 40.39130985242181)
        self.assertEqual(record["location"]["srid"], "EPSG:4326")
        self.assertEqual(record["captured_at"], "2026-08-13T18:00:00+00:00")

    def test_normalizes_an_event_without_type_or_location(self):
        record = normalize_municipal_event(self.raw_events[1], self.captured_at)
        self.assertEqual(record["event_id"], "50324218")
        self.assertIsNone(record["category"])
        self.assertEqual(record["free"], True)
        self.assertIsNone(record["location"]["district"])
        self.assertIsNone(record["location"]["lat"])
        self.assertIsNone(record["location"]["srid"])
        self.assertIn("Fiesta de Vuelta al Cole", record["description"])

    def test_normalizes_a_nested_category_type(self):
        record = normalize_municipal_event(self.raw_events[2], self.captured_at)
        self.assertEqual(record["category"], "ComediaMonologo")
        self.assertEqual(record["location"]["district"], "PuenteDeVallecas")

    def test_records_are_json_serializable(self):
        records = [normalize_municipal_event(raw, self.captured_at) for raw in self.raw_events]
        json.dumps(records)


class NormalizeEsmadridEventTests(unittest.TestCase):
    def setUp(self):
        self.services = parse_esmadrid_xml(ESMADRID_FIXTURE_PATH.read_bytes())
        self.captured_at = datetime(2026, 8, 13, 18, 0, 0, tzinfo=timezone.utc)

    def test_parses_expected_number_of_services(self):
        self.assertEqual(len(self.services), 2)

    def test_normalizes_a_recurring_event(self):
        record = normalize_esmadrid_event(self.services[0], self.captured_at)
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], SOURCE_ESMADRID)
        self.assertEqual(record["event_id"], "109461")
        self.assertEqual(record["title"], "Miguel Lago - Miserable")
        self.assertEqual(record["category"], "Eventos > Teatro y danza > Humor")
        self.assertEqual(record["start_datetime"], "2026-09-19")
        self.assertEqual(record["end_datetime"], "2026-12-12")
        self.assertIn("Sábados: 22:30 h", record["schedule_text"])
        self.assertNotIn("&nbsp;", record["schedule_text"])
        self.assertNotIn("<", record["schedule_text"])
        self.assertIsNone(record["free"])
        self.assertEqual(record["price_info"], "Desde 20 €")
        self.assertEqual(record["location"]["venue_name"], "Teatro Alcázar")
        self.assertEqual(record["location"]["postal_code"], "28014")
        self.assertAlmostEqual(record["location"]["lat"], 40.4174616)
        self.assertEqual(record["location"]["srid"], "EPSG:4326")
        # esMadrid no da distrito/barrio administrativo, a diferencia del dataset municipal
        self.assertIsNone(record["location"]["district"])
        self.assertNotIn("<strong>", record["description"])

    def test_normalizes_a_single_day_event(self):
        record = normalize_esmadrid_event(self.services[1], self.captured_at)
        self.assertEqual(record["start_datetime"], record["end_datetime"])
        self.assertIn("Fútbol", record["category"])

    def test_records_are_json_serializable(self):
        records = [normalize_esmadrid_event(s, self.captured_at) for s in self.services]
        json.dumps(records)


class SampleFixtureTests(unittest.TestCase):
    """Verifica que la muestra commiteada en `capturas/samples/` es válida y ambas fuentes están presentes."""

    def test_committed_sample_matches_schema_and_both_sources_present(self):
        sample_path = (
            Path(__file__).parent.parent / "capturas" / "samples" / "agenda_eventos_madrid_sample.json"
        )
        records = json.loads(sample_path.read_text(encoding="utf-8"))

        self.assertGreater(len(records), 0)
        sources = {record["source"] for record in records}
        self.assertEqual(sources, {SOURCE_MUNICIPAL, SOURCE_ESMADRID})

        required_keys = {
            "schema_version",
            "source",
            "event_id",
            "title",
            "description",
            "category",
            "start_datetime",
            "end_datetime",
            "schedule_text",
            "free",
            "price_info",
            "location",
            "url",
            "captured_at",
        }
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertTrue(required_keys.issubset(record.keys()))
            self.assertIn("lat", record["location"])
            self.assertIn("lon", record["location"])


if __name__ == "__main__":
    unittest.main()
