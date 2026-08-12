"""Tests de la carga batch puntual de puntos de interés turístico de Madrid.

No hacen ninguna llamada de red: usan el fixture
`fixtures/poi_turismo_sample.xml` (6 `<service>` con la misma estructura que
el XML real de "Puntos de interés turístico de la ciudad de Madrid", con
casos límite: un nombre con entidades HTML doblemente escapadas, un servicio
con subcategoría, uno con varias categorías donde solo una coincide con la
buscada, uno de una categoría distinta que debe quedar filtrado, uno sin
coordenadas que debe descartarse, y uno con "Servicios de pago"/"Horario"
literalmente "--").

También verifica que la muestra commiteada en
`ingesta/capturas/samples/poi_madrid_sample.json` cumple el esquema
esperado.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.poi_madrid import (
    _strip_html,
    _unescape,
    normalize_record,
    select_sample_pois,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
POIS_PATH = FIXTURES_DIR / "poi_turismo_sample.xml"
SAMPLES_DIR = Path(__file__).parent.parent / "capturas" / "samples"

TARGET_CATEGORY_ID = "7173"
INGESTED_AT = datetime(2026, 8, 12, 23, 0, 0, tzinfo=timezone.utc)


class UnescapeTests(unittest.TestCase):
    def test_resolves_double_encoded_named_entities(self):
        self.assertEqual(_unescape(" Comunidad &eacute;lite &ndash; test"), "Comunidad élite – test")

    def test_blank_returns_none(self):
        self.assertIsNone(_unescape("   "))
        self.assertIsNone(_unescape(None))


class StripHtmlTests(unittest.TestCase):
    def test_removes_tags_and_collapses_whitespace(self):
        raw = "<p><strong>Templo</strong> cerca de   la <a href='x'>Plaza</a>.</p>"
        self.assertEqual(_strip_html(raw), "Templo cerca de la Plaza .")

    def test_blank_returns_none(self):
        self.assertIsNone(_strip_html(""))
        self.assertIsNone(_strip_html(None))


class SelectSamplePoisTests(unittest.TestCase):
    def test_filters_by_category_and_skips_missing_coordinates(self):
        xml_text = POIS_PATH.read_text(encoding="utf-8")
        selected = select_sample_pois(xml_text, TARGET_CATEGORY_ID, sample_size=10)

        ids = [service.get("id") for service, _ in selected]
        # 203 (otra categoría) y 205 (sin coordenadas) deben quedar fuera.
        self.assertEqual(ids, ["201", "202", "204", "206"])

    def test_respects_sample_size(self):
        xml_text = POIS_PATH.read_text(encoding="utf-8")
        selected = select_sample_pois(xml_text, TARGET_CATEGORY_ID, sample_size=2)
        self.assertEqual(len(selected), 2)

    def test_only_target_category_matched_from_multi_category_service(self):
        xml_text = POIS_PATH.read_text(encoding="utf-8")
        selected = select_sample_pois(xml_text, TARGET_CATEGORY_ID, sample_size=10)

        service_204 = next(service for service, _ in selected if service.get("id") == "204")
        _, category = next((s, c) for s, c in selected if s is service_204)
        self.assertEqual(category["name"], "Edificios y monumentos")


class NormalizeRecordTests(unittest.TestCase):
    def _select(self, sample_size=10):
        xml_text = POIS_PATH.read_text(encoding="utf-8")
        return select_sample_pois(xml_text, TARGET_CATEGORY_ID, sample_size=sample_size)

    def test_normalizes_double_encoded_name_and_subcategory(self):
        service, category = self._select()[0]
        record = normalize_record(service, category, INGESTED_AT)

        self.assertEqual(record["poi_id"], "201")
        self.assertEqual(record["name"], "Comunidad Evangélica – Friedenskirche")
        self.assertEqual(record["category"], "Edificios y monumentos")
        self.assertEqual(record["subcategories"], ["Iglesias"])
        self.assertIn("Templo evangélico", record["description"])
        self.assertEqual(record["postal_code"], "28046")
        self.assertEqual(record["district"], None)
        self.assertEqual(record["neighbourhood"], None)
        self.assertEqual(record["schedule"], "Lun - Vier: 10:00 - 14:00 h")
        self.assertEqual(record["price_info"], "--")
        self.assertEqual(record["last_updated"], "2026-06-04")
        self.assertEqual(record["ingested_at"], "2026-08-12T23:00:00+00:00")
        self.assertAlmostEqual(record["location"]["lat"], 40.4272094, places=6)
        self.assertAlmostEqual(record["location"]["lon"], -3.6891476, places=6)
        self.assertEqual(record["location"]["srid"], "EPSG:4326")

    def test_normalizes_service_without_optional_fields(self):
        selected = self._select()
        service, category = next((s, c) for s, c in selected if s.get("id") == "202")

        record = normalize_record(service, category, INGESTED_AT)

        self.assertEqual(record["name"], "Huerta de la Salud")
        self.assertEqual(record["subcategories"], [])
        self.assertIsNone(record["phone"])
        self.assertIsNone(record["email"])
        self.assertIsNone(record["schedule"])
        self.assertIsNone(record["price_info"])

    def test_normalizes_multi_category_service_keeps_only_target_category(self):
        selected = self._select()
        service, category = next((s, c) for s, c in selected if s.get("id") == "204")

        record = normalize_record(service, category, INGESTED_AT)

        self.assertEqual(record["category"], "Edificios y monumentos")
        self.assertEqual(record["locality"], "Fuencarral - El Pardo")
        self.assertEqual(record["price_info"], "Visita gratuita a los jardines.")


class CommittedSampleTests(unittest.TestCase):
    EXPECTED_KEYS = {
        "schema_version",
        "source",
        "poi_id",
        "name",
        "category",
        "subcategories",
        "description",
        "address",
        "postal_code",
        "locality",
        "country",
        "district",
        "neighbourhood",
        "website",
        "phone",
        "email",
        "schedule",
        "price_info",
        "last_updated",
        "ingested_at",
        "location",
    }

    def test_sample_matches_schema(self):
        records = json.loads((SAMPLES_DIR / "poi_madrid_sample.json").read_text())
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertEqual(set(record.keys()), self.EXPECTED_KEYS)
            self.assertTrue(record["poi_id"])
            self.assertTrue(record["name"])
            self.assertEqual(record["category"], "Edificios y monumentos")
            self.assertIn("lat", record["location"])
            self.assertIn("lon", record["location"])
            self.assertIsNotNone(record["location"]["lat"])
            self.assertIsNotNone(record["location"]["lon"])


if __name__ == "__main__":
    unittest.main()
