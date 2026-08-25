"""Tests de la carga batch puntual de POIs de OpenStreetMap (tarea 083).

No hacen ninguna llamada de red: usan el fixture
`fixtures/overpass_pois_sample.json` (respuesta Overpass con 7 elementos y
casos límite: un elemento con los 4 campos opcionales presentes, uno con
`shop` en vez de `amenity`, uno sin `opening_hours`, uno sin
`opening_hours` ni `wheelchair`, uno con tag reconocido pero sin `name`, uno
sin ningún tag de interés que debe quedar filtrado, y una `way` sin
`lat`/`lon`).

También verifica que la muestra commiteada en
`ingesta/capturas/samples/enriquecimiento_osm_lugares_sample.json` (captura
real contra Overpass, ver docstring del módulo) cumple el esquema esperado.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.enriquecimiento_osm_lugares import (
    build_overpass_query,
    normalize_record,
    select_sample_pois,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
ELEMENTS_PATH = FIXTURES_DIR / "overpass_pois_sample.json"
SAMPLES_DIR = Path(__file__).parent.parent / "capturas" / "samples"

INGESTED_AT = datetime(2026, 8, 25, 20, 0, 0, tzinfo=timezone.utc)


def _load_elements() -> list:
    payload = json.loads(ELEMENTS_PATH.read_text(encoding="utf-8"))
    return payload["elements"]


class BuildOverpassQueryTests(unittest.TestCase):
    def test_incluye_los_4_tags_y_el_bbox_una_sola_vez_cada_uno(self):
        query = build_overpass_query((40.31, -3.89, 40.64, -3.52), overpass_timeout_seconds=25, limit=100)
        for tag in ("amenity", "shop", "tourism", "leisure"):
            self.assertIn(f'node["{tag}"](40.31,-3.89,40.64,-3.52);', query)
        self.assertIn("[timeout:25]", query)
        self.assertIn("out body 100;", query)


class NormalizeRecordTests(unittest.TestCase):
    def setUp(self):
        self.elements = {e["id"]: e for e in _load_elements()}

    def test_normaliza_elemento_con_los_4_campos_opcionales(self):
        record = normalize_record(self.elements[26065699], INGESTED_AT)

        self.assertEqual(record["osm_id"], 26065699)
        self.assertEqual(record["osm_type"], "node")
        self.assertEqual(record["name"], "Honest Greens")
        self.assertEqual(record["amenity"], "restaurant")
        self.assertEqual(
            record["opening_hours"], "Mo-Th 08:30-23:00, Fr 08:30-24:00, Sa 09:30-24:00, Su,PH 09:30-23:00"
        )
        self.assertEqual(record["wheelchair"], "no")
        self.assertEqual(record["ingested_at"], "2026-08-25T22:00:00+02:00")
        self.assertAlmostEqual(record["location"]["lat"], 40.4270276, places=6)
        self.assertAlmostEqual(record["location"]["lon"], -3.7016997, places=6)
        self.assertEqual(record["location"]["srid"], "EPSG:4326")

    def test_usa_shop_cuando_no_hay_amenity(self):
        record = normalize_record(self.elements[167301935], INGESTED_AT)
        self.assertEqual(record["amenity"], "supermarket")

    def test_campos_opcionales_ausentes_quedan_none(self):
        record = normalize_record(self.elements[150760890], INGESTED_AT)
        self.assertEqual(record["amenity"], "sports_centre")
        self.assertIsNone(record["opening_hours"])
        self.assertIsNone(record["wheelchair"])

    def test_elemento_con_tag_reconocido_pero_sin_name(self):
        record = normalize_record(self.elements[25911220], INGESTED_AT)
        self.assertIsNotNone(record)
        self.assertIsNone(record["name"])
        self.assertEqual(record["amenity"], "parking")

    def test_elemento_sin_ningun_tag_de_interes_devuelve_none(self):
        self.assertIsNone(normalize_record(self.elements[21947483], INGESTED_AT))

    def test_elemento_sin_lat_lon_tiene_location_none(self):
        record = normalize_record(self.elements[999999999], INGESTED_AT)
        self.assertIsNotNone(record)
        self.assertIsNone(record["location"])


class SelectSamplePoisTests(unittest.TestCase):
    def test_filtra_sin_nombre_sin_tag_y_sin_coordenadas(self):
        elements = _load_elements()
        selected = select_sample_pois(elements, sample_size=10)

        ids = {record["osm_id"] for record in selected}
        # 25911220 (sin name), 21947483 (sin tag de interés) y 999999999
        # (sin coordenadas) deben quedar fuera.
        self.assertEqual(ids, {26065699, 167301935, 158849464, 150760890})

    def test_respeta_sample_size(self):
        elements = _load_elements()
        selected = select_sample_pois(elements, sample_size=2)
        self.assertEqual(len(selected), 2)


class CommittedSampleTests(unittest.TestCase):
    EXPECTED_KEYS = {
        "schema_version",
        "source",
        "osm_id",
        "osm_type",
        "name",
        "amenity",
        "opening_hours",
        "wheelchair",
        "ingested_at",
        "location",
    }

    def test_sample_matches_schema(self):
        records = json.loads(
            (SAMPLES_DIR / "enriquecimiento_osm_lugares_sample.json").read_text(encoding="utf-8")
        )
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertEqual(set(record.keys()), self.EXPECTED_KEYS)
            self.assertTrue(record["osm_id"])
            self.assertEqual(record["osm_type"], "node")
            self.assertTrue(record["name"])
            self.assertTrue(record["amenity"])
            self.assertIsNotNone(record["location"])
            self.assertIsNotNone(record["location"]["lat"])
            self.assertIsNotNone(record["location"]["lon"])


if __name__ == "__main__":
    unittest.main()
