"""Tests de la carga batch puntual del callejero/grafo viario de Madrid.

No hacen ninguna llamada de red: usan los fixtures
`fixtures/callejero_vias_sample.csv` (4 viales con la misma estructura de
columnas que el CSV real de "Viales oficiales y topónimos", incluyendo un
vial con varios distritos separados por "-", uno con código postal
"varios", y uno sin coordenadas conocidas para verificar que se descarta) y
`fixtures/callejero_cruces_sample.csv` (cruces de esos viales, incluyendo la
entrada recíproca de un cruce -para verificar que no se duplica-, y un cruce
de un vial no seleccionado en la muestra -para verificar el filtrado-).

También verifica que la muestra commiteada en
`ingesta/capturas/samples/callejero_madrid_vias_sample.json` y
`callejero_madrid_cruces_sample.json` cumple el esquema esperado.
"""

import json
import unittest
from pathlib import Path

from ingesta.capturas.callejero_madrid import (
    _parse_dms,
    _parse_district_codes,
    normalize_crossing_record,
    normalize_vial_record,
    select_crossings_for_vias,
    select_sample_vias,
)

from datetime import datetime, timezone

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VIAS_PATH = FIXTURES_DIR / "callejero_vias_sample.csv"
CROSSINGS_PATH = FIXTURES_DIR / "callejero_cruces_sample.csv"
SAMPLES_DIR = Path(__file__).parent.parent / "capturas" / "samples"

INGESTED_AT = datetime(2026, 8, 12, 22, 0, 0, tzinfo=timezone.utc)


class ParseDmsTests(unittest.TestCase):
    def test_parses_west_and_north_hemispheres(self):
        self.assertAlmostEqual(_parse_dms("3º40'16.72'' W"), -3.671311, places=6)
        self.assertAlmostEqual(_parse_dms("40º30'55.78'' N"), 40.515494, places=6)

    def test_blank_or_malformed_returns_none(self):
        self.assertIsNone(_parse_dms("   "))
        self.assertIsNone(_parse_dms(None))
        self.assertIsNone(_parse_dms("not a coordinate"))


class ParseDistrictCodesTests(unittest.TestCase):
    def test_single_code(self):
        self.assertEqual(_parse_district_codes("08                    "), ["08"])

    def test_multiple_codes_separated_by_dash(self):
        self.assertEqual(_parse_district_codes("18-20-21              "), ["18", "20", "21"])

    def test_blank_returns_empty_list(self):
        self.assertEqual(_parse_district_codes("   "), [])


class SelectSampleViasTests(unittest.TestCase):
    def test_skips_vial_without_coordinates(self):
        csv_text = VIAS_PATH.read_text(encoding="utf-8")
        rows = select_sample_vias(csv_text, sample_size=3)

        codes = [row["Codigo de vía"] for row in rows]
        self.assertEqual(codes, ["00000127", "00000150", "00000400"])
        self.assertNotIn("00000999", codes)

    def test_respects_sample_size(self):
        csv_text = VIAS_PATH.read_text(encoding="utf-8")
        rows = select_sample_vias(csv_text, sample_size=1)
        self.assertEqual(len(rows), 1)


class NormalizeVialRecordTests(unittest.TestCase):
    def test_normalizes_single_district_and_postal_code(self):
        csv_text = VIAS_PATH.read_text(encoding="utf-8")
        row = select_sample_vias(csv_text, sample_size=1)[0]

        record = normalize_vial_record(row, INGESTED_AT)

        self.assertEqual(record["source"], "madrid_callejero_vias")
        self.assertEqual(record["vial_id"], "00000127")
        self.assertEqual(record["class"], "CALLE")
        self.assertEqual(record["name"], "ISABEL COLBRAND")
        self.assertEqual(record["full_name"], "CALLE DE ISABEL COLBRAND")
        self.assertEqual(record["type"], "Vía")
        self.assertEqual(record["district_codes"], ["08"])
        self.assertEqual(record["postal_code"], "28050")
        self.assertEqual(record["ingested_at"], "2026-08-13T00:00:00+02:00")
        self.assertAlmostEqual(record["start_node"]["lat"], 40.515494, places=6)
        self.assertAlmostEqual(record["start_node"]["lon"], -3.671311, places=6)
        self.assertEqual(record["start_node"]["srid"], "EPSG:4326")

    def test_normalizes_multiple_districts_and_varios_postal_code(self):
        csv_text = VIAS_PATH.read_text(encoding="utf-8")
        row = select_sample_vias(csv_text, sample_size=2)[1]

        record = normalize_vial_record(row, INGESTED_AT)

        self.assertEqual(record["vial_id"], "00000150")
        self.assertEqual(record["district_codes"], ["18", "20", "21"])
        self.assertEqual(record["postal_code"], "varios")


class SelectCrossingsForViasTests(unittest.TestCase):
    def test_filters_by_treated_vial_and_avoids_reciprocal_duplicates(self):
        csv_text = CROSSINGS_PATH.read_text(encoding="utf-8")
        rows = select_crossings_for_vias(csv_text, vial_ids={"00000127"}, max_per_vial=10)

        treated_codes = {row["Codigo de vía tratado"] for row in rows}
        self.assertEqual(treated_codes, {"00000127"})
        self.assertEqual(len(rows), 2)
        # El cruce recíproco (tratado="00002792") y el cruce de un vial no
        # seleccionado (tratado="00000999") no deben aparecer.
        crossed_codes = {row["Codigo de via que cruza o enlaza"] for row in rows}
        self.assertEqual(crossed_codes, {"00002792", "00001837"})

    def test_caps_crossings_per_vial(self):
        csv_text = CROSSINGS_PATH.read_text(encoding="utf-8")
        rows = select_crossings_for_vias(csv_text, vial_ids={"00000150"}, max_per_vial=2)

        self.assertEqual(len(rows), 2)


class NormalizeCrossingRecordTests(unittest.TestCase):
    def test_normalizes_crossing(self):
        csv_text = CROSSINGS_PATH.read_text(encoding="utf-8")
        row = select_crossings_for_vias(csv_text, vial_ids={"00000127"}, max_per_vial=10)[0]

        record = normalize_crossing_record(row, INGESTED_AT)

        self.assertEqual(record["source"], "madrid_callejero_cruces")
        self.assertEqual(record["from_vial_id"], "00000127")
        self.assertEqual(record["from_vial_name"], "CALLE DE ISABEL COLBRAND")
        self.assertEqual(record["to_vial_id"], "00002792")
        self.assertEqual(record["to_vial_name"], "CALLE DE CASTIELLO DE JACA")
        self.assertEqual(record["ingested_at"], "2026-08-13T00:00:00+02:00")
        self.assertIsNotNone(record["location"]["lat"])
        self.assertIsNotNone(record["location"]["lon"])
        self.assertEqual(record["location"]["srid"], "EPSG:4326")


class CommittedSampleTests(unittest.TestCase):
    EXPECTED_VIA_KEYS = {
        "schema_version",
        "source",
        "vial_id",
        "class",
        "particle",
        "name",
        "full_name",
        "type",
        "situation",
        "district_codes",
        "postal_code",
        "ine_code",
        "address_count",
        "ingested_at",
        "start_node",
        "end_node",
    }
    EXPECTED_CROSSING_KEYS = {
        "schema_version",
        "source",
        "from_vial_id",
        "from_vial_name",
        "to_vial_id",
        "to_vial_name",
        "ingested_at",
        "location",
    }

    def test_vias_sample_matches_schema(self):
        records = json.loads((SAMPLES_DIR / "callejero_madrid_vias_sample.json").read_text(encoding="utf-8"))
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertEqual(set(record.keys()), self.EXPECTED_VIA_KEYS)
            self.assertTrue(record["vial_id"])
            self.assertIn("lat", record["start_node"])
            self.assertIn("lon", record["start_node"])

    def test_cruces_sample_matches_schema(self):
        records = json.loads((SAMPLES_DIR / "callejero_madrid_cruces_sample.json").read_text(encoding="utf-8"))
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertEqual(set(record.keys()), self.EXPECTED_CROSSING_KEYS)
            self.assertTrue(record["from_vial_id"])
            self.assertTrue(record["to_vial_id"])


if __name__ == "__main__":
    unittest.main()
