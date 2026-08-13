"""Tests del productor de previsión y avisos de AEMET para Madrid.

No hacen ninguna llamada de red: usan los fixtures
`fixtures/aemet_prediccion_diaria_sample.json` (payload en el esquema real
de OpenData, construido con valores reales de Madrid capturados en vivo del
feed público legado de AEMET, ver docstring del módulo bajo prueba) y
`fixtures/aemet_avisos_cap_sample.xml` (documento CAP 1.2 de ejemplo, dos
bloques `<info>` -es-ES y en-GB- para probar el filtrado por idioma).
"""

import io
import json
import tarfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.aemet_prevision_avisos import (
    SOURCE_AVISOS,
    SOURCE_PREDICCION,
    _extract_cap_xml_documents,
    _period_value,
    normalize_aviso,
    normalize_prediccion_dia,
    parse_cap_alert,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PREDICCION_FIXTURE_PATH = FIXTURES_DIR / "aemet_prediccion_diaria_sample.json"
AVISOS_FIXTURE_PATH = FIXTURES_DIR / "aemet_avisos_cap_sample.xml"


class NormalizePrediccionDiaTests(unittest.TestCase):
    def setUp(self):
        payload = json.loads(PREDICCION_FIXTURE_PATH.read_text(encoding="utf-8"))
        self.municipio_raw = payload[0]
        self.dias = self.municipio_raw["prediccion"]["dia"]
        self.captured_at = datetime(2026, 8, 13, 22, 0, 0, tzinfo=timezone.utc)

    def test_normalizes_a_full_day_with_wind_gust(self):
        record = normalize_prediccion_dia(self.dias[1], self.municipio_raw, self.captured_at)
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], SOURCE_PREDICCION)
        self.assertEqual(record["municipio_code"], "28079")
        self.assertEqual(record["municipio_name"], "Madrid")
        self.assertEqual(record["province"], "Madrid")
        self.assertEqual(record["elaborated_at"], "2026-08-13T21:19:10")
        self.assertEqual(record["valid_date"], "2026-08-15")
        self.assertEqual(record["sky_state"], "Intervalos nubosos con lluvia")
        self.assertEqual(record["sky_state_code"], "23")
        self.assertEqual(record["precipitation_probability_pct"], "95")
        self.assertEqual(record["temperature_max_c"], 34)
        self.assertEqual(record["temperature_min_c"], 22)
        self.assertEqual(record["thermal_sensation_max_c"], 31)
        self.assertEqual(record["humidity_max_pct"], 65)
        self.assertEqual(record["wind_direction"], "SE")
        self.assertEqual(record["wind_speed_kmh"], "20")
        self.assertEqual(record["wind_gust_max_kmh"], "40")
        self.assertEqual(record["uv_max"], 8)
        self.assertEqual(record["captured_at"], "2026-08-13T22:00:00+00:00")
        self.assertFalse(record["is_mock"])

    def test_missing_gust_for_the_day_period_is_none(self):
        # Día 08-14 real: rachaMax con periodo="00-24" viene vacío en la fuente.
        record = normalize_prediccion_dia(self.dias[0], self.municipio_raw, self.captured_at)
        self.assertIsNone(record["wind_gust_max_kmh"])
        self.assertEqual(record["temperature_max_c"], 38)

    def test_records_are_json_serializable(self):
        records = [normalize_prediccion_dia(dia, self.municipio_raw, self.captured_at) for dia in self.dias]
        json.dumps(records)
        self.assertEqual(len(records), 3)


class PeriodValueTests(unittest.TestCase):
    def test_returns_none_when_entries_missing(self):
        self.assertIsNone(_period_value(None))
        self.assertIsNone(_period_value([]))

    def test_returns_none_for_empty_string_value(self):
        self.assertIsNone(_period_value([{"periodo": "00-24", "value": ""}]))

    def test_finds_requested_period(self):
        entries = [{"periodo": "00-12", "value": 1}, {"periodo": "00-24", "value": 2}]
        self.assertEqual(_period_value(entries), 2)


class ParseCapAlertTests(unittest.TestCase):
    def setUp(self):
        self.infos = parse_cap_alert(AVISOS_FIXTURE_PATH.read_bytes())

    def test_parses_both_info_blocks(self):
        self.assertEqual(len(self.infos), 2)
        languages = {info["language"] for info in self.infos}
        self.assertEqual(languages, {"es-ES", "en-GB"})

    def test_extracts_aemet_parameters_and_areas(self):
        es_info = next(info for info in self.infos if info["language"] == "es-ES")
        self.assertEqual(es_info["identifier"], "es-aemet-CAP-2026-08-14-00-72-01")
        self.assertEqual(es_info["parameters"]["AEMET-Meteoalerta nivel"], "amarillo")
        self.assertEqual(es_info["parameters"]["AEMET-Meteoalerta fenomeno"], "Altas temperaturas")
        self.assertEqual(es_info["parameters"]["AEMET-Meteoalerta zona"], "Madrid")
        self.assertEqual(es_info["areas"], ["Madrid"])
        self.assertEqual(es_info["onset"], "2026-08-14T13:00:00+02:00")
        self.assertEqual(es_info["expires"], "2026-08-14T21:00:00+02:00")


class NormalizeAvisoTests(unittest.TestCase):
    def setUp(self):
        self.infos = parse_cap_alert(AVISOS_FIXTURE_PATH.read_bytes())
        self.captured_at = datetime(2026, 8, 14, 8, 0, 0, tzinfo=timezone.utc)

    def test_normalizes_the_spanish_info_block(self):
        es_info = next(info for info in self.infos if info["language"] == "es-ES")
        record = normalize_aviso(es_info, self.captured_at)
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], SOURCE_AVISOS)
        self.assertEqual(record["level"], "amarillo")
        self.assertEqual(record["phenomenon"], "Altas temperaturas")
        self.assertEqual(record["zone"], "Madrid")
        self.assertEqual(record["probability"], "100%")
        self.assertEqual(record["severity"], "Moderate")
        self.assertEqual(record["effective_from"], "2026-08-14T13:00:00+02:00")
        self.assertEqual(record["effective_until"], "2026-08-14T21:00:00+02:00")
        self.assertEqual(record["captured_at"], "2026-08-14T08:00:00+00:00")
        self.assertFalse(record["is_mock"])

    def test_falls_back_to_cap_event_and_areadesc_without_aemet_parameters(self):
        info = {
            "identifier": "x",
            "sent": "2026-08-14T07:00:00+02:00",
            "language": "es-ES",
            "event": "Tormentas",
            "severity": "Minor",
            "urgency": "Future",
            "certainty": "Possible",
            "onset": None,
            "expires": None,
            "headline": None,
            "description": None,
            "parameters": {},
            "areas": ["Sierra de Madrid"],
        }
        record = normalize_aviso(info, self.captured_at)
        self.assertIsNone(record["level"])
        self.assertEqual(record["phenomenon"], "Tormentas")
        self.assertEqual(record["zone"], "Sierra de Madrid")

    def test_records_are_json_serializable(self):
        records = [normalize_aviso(info, self.captured_at) for info in self.infos]
        json.dumps(records)


class ExtractCapXmlDocumentsTests(unittest.TestCase):
    def test_extracts_xml_members_from_tar(self):
        xml_bytes = AVISOS_FIXTURE_PATH.read_bytes()
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="72/CAP_72_20260814.xml")
            info.size = len(xml_bytes)
            tar.addfile(info, io.BytesIO(xml_bytes))
        documents = _extract_cap_xml_documents(buffer.getvalue())
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0], xml_bytes)

    def test_empty_tar_returns_no_documents(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz"):
            pass
        self.assertEqual(_extract_cap_xml_documents(buffer.getvalue()), [])


class SampleFixtureTests(unittest.TestCase):
    """Verifica que las muestras commiteadas en `capturas/samples/` son válidas."""

    def test_prevision_sample_matches_schema(self):
        sample_path = (
            Path(__file__).parent.parent / "capturas" / "samples" / "aemet_prevision_madrid_sample.json"
        )
        records = json.loads(sample_path.read_text(encoding="utf-8"))
        self.assertGreater(len(records), 0)
        required_keys = {
            "schema_version",
            "source",
            "municipio_code",
            "municipio_name",
            "valid_date",
            "temperature_max_c",
            "temperature_min_c",
            "precipitation_probability_pct",
            "wind_direction",
            "wind_speed_kmh",
            "is_mock",
        }
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], SOURCE_PREDICCION)
            self.assertTrue(required_keys.issubset(record.keys()))
            self.assertTrue(record["is_mock"])

    def test_avisos_sample_matches_schema(self):
        sample_path = (
            Path(__file__).parent.parent / "capturas" / "samples" / "aemet_avisos_madrid_sample.json"
        )
        records = json.loads(sample_path.read_text(encoding="utf-8"))
        required_keys = {
            "schema_version",
            "source",
            "zone",
            "level",
            "phenomenon",
            "effective_from",
            "effective_until",
            "is_mock",
        }
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], SOURCE_AVISOS)
            self.assertTrue(required_keys.issubset(record.keys()))
            self.assertTrue(record["is_mock"])


if __name__ == "__main__":
    unittest.main()
