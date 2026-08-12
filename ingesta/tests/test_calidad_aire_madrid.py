"""Tests del productor de calidad del aire de Madrid.

No hacen ninguna llamada de red: usan los fixtures
`fixtures/calidad_aire_realtime_sample.json` (copia reducida de una
respuesta real del recurso JSON de tiempo real de datos.madrid.es,
capturada en vivo desde este entorno el 12/08/2026, con un tercer registro
sintético añadido a propósito sin ninguna hora válida) y
`fixtures/calidad_aire_estaciones_sample.csv` (copia reducida y real del
catálogo de estaciones de control, con solo 2 de las 24 estaciones, para
verificar también el caso de una estación sin metadatos conocidos).
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.calidad_aire_madrid import (
    normalize_record,
    parse_realtime_entries,
    parse_stations,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REALTIME_PATH = FIXTURES_DIR / "calidad_aire_realtime_sample.json"
STATIONS_PATH = FIXTURES_DIR / "calidad_aire_estaciones_sample.csv"


class ParseStationsTests(unittest.TestCase):
    def test_parses_known_stations_by_code(self):
        stations = parse_stations(STATIONS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(len(stations), 2)
        station = stations["28079011"]
        self.assertEqual(station["name"], "Ramón y Cajal")
        self.assertAlmostEqual(station["lat"], 40.4514734)
        self.assertAlmostEqual(station["lon"], -3.6773491)


class ParseRealtimeEntriesTests(unittest.TestCase):
    def test_produces_one_entry_per_station_and_magnitude(self):
        entries = parse_realtime_entries(REALTIME_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 3)


class NormalizeRecordTests(unittest.TestCase):
    def setUp(self):
        self.entries = parse_realtime_entries(REALTIME_PATH.read_text(encoding="utf-8"))
        self.stations = parse_stations(STATIONS_PATH.read_text(encoding="utf-8"))
        self.ingested_at = datetime(2026, 8, 12, 9, 15, 30, tzinfo=timezone.utc)

    def test_normalizes_a_reading_with_known_station(self):
        entry = next(e for e in self.entries if e["PUNTO_MUESTREO"] == "28079011_12_8")

        record = normalize_record(entry, self.stations, self.ingested_at)

        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "madrid_calidad_aire")
        self.assertEqual(record["station_id"], "28079011")
        self.assertEqual(record["station_name"], "Ramón y Cajal")
        self.assertEqual(record["magnitude_code"], "12")
        self.assertEqual(record["magnitude_abbr"], "NOx")
        self.assertEqual(record["unit"], "µg/m³")
        # H02/V02 son la lectura horaria válida más reciente de este registro.
        self.assertEqual(record["value"], 37.0)
        self.assertEqual(record["measured_at"], "2026-08-12T00:00:00+00:00")
        self.assertEqual(record["ingested_at"], "2026-08-12T09:15:30+00:00")
        self.assertEqual(record["location"], {"lat": 40.4514734, "lon": -3.6773491, "srid": "EPSG:4326"})

    def test_normalizes_a_reading_with_unpadded_magnitude_code(self):
        entry = next(e for e in self.entries if e["PUNTO_MUESTREO"] == "28079004_1_38")

        record = normalize_record(entry, self.stations, self.ingested_at)

        self.assertEqual(record["magnitude_code"], "01")
        self.assertEqual(record["magnitude_abbr"], "SO2")
        self.assertEqual(record["station_name"], "Plaza de España")

    def test_returns_none_for_a_reading_with_no_valid_hour(self):
        entry = next(e for e in self.entries if e["PUNTO_MUESTREO"] == "28079099_9_47")

        self.assertIsNone(normalize_record(entry, self.stations, self.ingested_at))

    def test_normalizes_a_reading_with_unknown_station_to_null_metadata(self):
        entry = dict(next(e for e in self.entries if e["PUNTO_MUESTREO"] == "28079011_12_8"))
        entry["PUNTO_MUESTREO"] = "28079999_12_8"

        record = normalize_record(entry, self.stations, self.ingested_at)

        self.assertEqual(record["station_id"], "28079999")
        self.assertIsNone(record["station_name"])
        self.assertEqual(record["location"], {"lat": None, "lon": None, "srid": "EPSG:4326"})

    def test_records_are_json_serializable(self):
        records = [normalize_record(e, self.stations, self.ingested_at) for e in self.entries]
        json.dumps(records)


class SampleFixtureTests(unittest.TestCase):
    """Verifica que la muestra commiteada en `capturas/samples/` es válida."""

    def test_committed_sample_matches_schema(self):
        sample_path = (
            Path(__file__).parent.parent / "capturas" / "samples" / "calidad_aire_madrid_sample.json"
        )
        records = json.loads(sample_path.read_text(encoding="utf-8"))

        self.assertGreater(len(records), 0)
        self.assertLessEqual(len(records), 10)
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], "madrid_calidad_aire")
            self.assertIn("station_id", record)
            self.assertIn("magnitude_code", record)
            self.assertIn("value", record)
            self.assertIn("location", record)
            self.assertIn("lat", record["location"])
            self.assertIn("lon", record["location"])


if __name__ == "__main__":
    unittest.main()
