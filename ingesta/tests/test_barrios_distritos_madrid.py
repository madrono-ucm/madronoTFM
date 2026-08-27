"""Tests de la carga batch puntual de límites de barrios y distritos de Madrid.

No hacen ninguna llamada de red: usan los fixtures
`fixtures/barrios_distritos_distritos_sample.json` (2 features estilo
respuesta GeoJSON del MapServer, una `Polygon` y una `MultiPolygon`, con un
anillo con puntos exactamente colineales para poder verificar la
simplificación Douglas-Peucker de forma determinista) y
`fixtures/barrios_distritos_barrios_sample.json` (4 barrios repartidos en 2
distritos, para verificar el tope de barrios por distrito).

También verifica que la muestra commiteada en
`ingesta/capturas/samples/barrios_distritos_madrid_distritos_sample.json` y
`barrios_distritos_madrid_barrios_sample.json` cumple el esquema esperado.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.barrios_distritos_madrid import (
    _cap_features_per_district,
    _douglas_peucker,
    normalize_district_record,
    normalize_neighbourhood_record,
    simplify_geometry,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DISTRICTS_PATH = FIXTURES_DIR / "barrios_distritos_distritos_sample.json"
NEIGHBOURHOODS_PATH = FIXTURES_DIR / "barrios_distritos_barrios_sample.json"
SAMPLES_DIR = Path(__file__).parent.parent / "capturas" / "samples"

INGESTED_AT = datetime(2026, 8, 12, 22, 0, 0, tzinfo=timezone.utc)


def _load_features(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


class DouglasPeuckerTests(unittest.TestCase):
    def test_collapses_a_bump_within_tolerance(self):
        points = [[0, 0], [5, 0.5], [10, 0]]
        self.assertEqual(_douglas_peucker(points, 1), [[0, 0], [10, 0]])

    def test_keeps_a_bump_beyond_tolerance(self):
        points = [[0, 0], [5, 0.5], [10, 0]]
        self.assertEqual(_douglas_peucker(points, 0.1), [[0, 0], [5, 0.5], [10, 0]])

    def test_short_lines_returned_unchanged(self):
        points = [[0, 0], [1, 1]]
        self.assertEqual(_douglas_peucker(points, 100), points)


class SimplifyGeometryTests(unittest.TestCase):
    def setUp(self):
        # Los tres primeros puntos (y el último, que cierra el anillo) son
        # exactamente colineales con el cuarto: cualquier tolerancia > 0 los
        # colapsa, dejando solo los tres vértices "reales" del triángulo.
        self.ring = [
            [-3.7, 40.40],
            [-3.6995, 40.4005],
            [-3.699, 40.401],
            [-3.65, 40.45],
            [-3.6, 40.40],
            [-3.7, 40.40],
        ]
        self.expected_simplified_ring = [
            [-3.7, 40.4],
            [-3.65, 40.45],
            [-3.6, 40.4],
            [-3.7, 40.4],
        ]

    def test_simplifies_polygon_ring(self):
        geometry = {"type": "Polygon", "coordinates": [self.ring]}
        simplified, was_simplified = simplify_geometry(geometry, 0.0001)
        self.assertTrue(was_simplified)
        self.assertEqual(simplified["coordinates"][0], self.expected_simplified_ring)

    def test_simplifies_each_polygon_of_a_multipolygon(self):
        geometry = {"type": "MultiPolygon", "coordinates": [[self.ring]]}
        simplified, was_simplified = simplify_geometry(geometry, 0.0001)
        self.assertTrue(was_simplified)
        self.assertEqual(simplified["coordinates"][0][0], self.expected_simplified_ring)

    def test_zero_tolerance_disables_simplification(self):
        geometry = {"type": "Polygon", "coordinates": [self.ring]}
        unchanged, was_simplified = simplify_geometry(geometry, 0)
        self.assertFalse(was_simplified)
        self.assertEqual(unchanged["coordinates"][0], self.ring)


class NormalizeDistrictRecordTests(unittest.TestCase):
    def test_normalizes_polygon_feature(self):
        feature = _load_features(DISTRICTS_PATH)[0]
        record = normalize_district_record(feature, INGESTED_AT, 0.0001)

        self.assertEqual(record["source"], "madrid_distritos")
        self.assertEqual(record["district_id"], "01")
        self.assertEqual(record["name"], "Centro")
        self.assertAlmostEqual(record["area_m2"], 5228245.50873203)
        self.assertEqual(record["ingested_at"], "2026-08-13T00:00:00+02:00")
        self.assertTrue(record["simplified"])
        self.assertEqual(record["simplify_tolerance_deg"], 0.0001)
        self.assertEqual(record["geometry"]["type"], "Polygon")
        self.assertEqual(record["geometry"]["srid"], "EPSG:4326")
        # 6 puntos en la fuente -> 4 tras colapsar los 3 colineales.
        self.assertEqual(len(record["geometry"]["coordinates"][0]), 4)

    def test_normalizes_multipolygon_feature_without_simplifying_at_zero_tolerance(self):
        feature = _load_features(DISTRICTS_PATH)[1]
        record = normalize_district_record(feature, INGESTED_AT, 0)

        self.assertEqual(record["district_id"], "02")
        self.assertFalse(record["simplified"])
        self.assertIsNone(record["simplify_tolerance_deg"])
        self.assertEqual(record["geometry"]["type"], "MultiPolygon")
        self.assertEqual(len(record["geometry"]["coordinates"][0][0]), 6)


class NormalizeNeighbourhoodRecordTests(unittest.TestCase):
    def test_normalizes_neighbourhood(self):
        feature = _load_features(NEIGHBOURHOODS_PATH)[0]
        record = normalize_neighbourhood_record(feature, INGESTED_AT, 0.0001)

        self.assertEqual(record["source"], "madrid_barrios")
        self.assertEqual(record["neighbourhood_id"], "011")
        self.assertEqual(record["name"], "Palacio")
        self.assertEqual(record["district_id"], "01")
        self.assertEqual(record["district_name"], "Centro")
        self.assertAlmostEqual(record["area_m2"], 1469905.932620575)
        self.assertEqual(record["geometry"]["type"], "Polygon")
        self.assertEqual(record["geometry"]["srid"], "EPSG:4326")


class CapFeaturesPerDistrictTests(unittest.TestCase):
    def test_caps_features_per_district_code(self):
        features = _load_features(NEIGHBOURHOODS_PATH)
        selected = _cap_features_per_district(features, max_per_district=2)

        codes = [f["properties"]["COD_BAR"] for f in selected]
        # Distrito 01 tiene 3 barrios en el fixture, se corta a 2; distrito
        # 02 solo tiene 1, se conserva entero.
        self.assertEqual(codes, ["011", "012", "021"])

    def test_zero_cap_returns_nothing(self):
        features = _load_features(NEIGHBOURHOODS_PATH)
        self.assertEqual(_cap_features_per_district(features, max_per_district=0), [])


class CommittedSampleTests(unittest.TestCase):
    EXPECTED_DISTRICT_KEYS = {
        "schema_version",
        "source",
        "district_id",
        "name",
        "area_m2",
        "ingested_at",
        "simplified",
        "simplify_tolerance_deg",
        "geometry",
    }
    EXPECTED_NEIGHBOURHOOD_KEYS = {
        "schema_version",
        "source",
        "neighbourhood_id",
        "name",
        "district_id",
        "district_name",
        "area_m2",
        "ingested_at",
        "simplified",
        "simplify_tolerance_deg",
        "geometry",
    }

    def test_districts_sample_matches_schema(self):
        records = json.loads(
            (SAMPLES_DIR / "barrios_distritos_madrid_distritos_sample.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertGreater(len(records), 0)
        self.assertLessEqual(len(records), 5)
        for record in records:
            self.assertEqual(set(record.keys()), self.EXPECTED_DISTRICT_KEYS)
            self.assertTrue(record["district_id"])
            self.assertTrue(record["name"])
            self.assertEqual(record["geometry"]["type"], "Polygon")
            self.assertEqual(record["geometry"]["srid"], "EPSG:4326")
            self.assertGreater(len(record["geometry"]["coordinates"][0]), 0)

    def test_neighbourhoods_sample_matches_schema(self):
        records = json.loads(
            (SAMPLES_DIR / "barrios_distritos_madrid_barrios_sample.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertGreater(len(records), 0)
        district_ids = set()
        for record in records:
            self.assertEqual(set(record.keys()), self.EXPECTED_NEIGHBOURHOOD_KEYS)
            self.assertTrue(record["neighbourhood_id"])
            self.assertTrue(record["district_id"])
            self.assertEqual(record["geometry"]["type"], "Polygon")
            district_ids.add(record["district_id"])

        # Todos los barrios de la muestra deben pertenecer a alguno de los
        # distritos también incluidos en la muestra (fixture/sample coherente
        # como grafo padre-hijo, mismo criterio que viales/cruces en la tarea 009).
        districts = json.loads(
            (SAMPLES_DIR / "barrios_distritos_madrid_distritos_sample.json").read_text(
                encoding="utf-8"
            )
        )
        sampled_district_ids = {d["district_id"] for d in districts}
        self.assertTrue(district_ids.issubset(sampled_district_ids))


if __name__ == "__main__":
    unittest.main()
