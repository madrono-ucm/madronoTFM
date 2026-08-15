"""Tests del productor de datos meteorológicos de Madrid.

No hacen ninguna llamada de red: usan los fixtures
`fixtures/meteorologia_realtime_sample.json` (basado en valores reales de 2
estaciones —J.M.D. Moratalaz y E.D.A.R. La China—, capturados en vivo desde
este entorno el 12/08/2026, con una magnitud no reconocida y una estación
sin ninguna hora válida añadidas a propósito) y
`fixtures/meteorologia_estaciones_sample.csv` (copia reducida y real del
catálogo de estaciones, con solo esas 2 estaciones, para verificar también
el caso de una estación sin metadatos conocidos).
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.meteorologia_madrid import (
    group_by_station,
    normalize_station_record,
    parse_realtime_entries,
    parse_stations,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REALTIME_PATH = FIXTURES_DIR / "meteorologia_realtime_sample.json"
STATIONS_PATH = FIXTURES_DIR / "meteorologia_estaciones_sample.csv"


class ParseStationsTests(unittest.TestCase):
    def test_parses_known_stations_by_short_code(self):
        stations = parse_stations(STATIONS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(len(stations), 2)
        station = stations["102"]
        self.assertEqual(station["code"], "28079102")
        self.assertEqual(station["name"], "J.M.D. Moratalaz")
        self.assertAlmostEqual(station["lat"], 40.398611)
        self.assertAlmostEqual(station["lon"], -3.636944)
        self.assertEqual(station["altitude_m"], 686)


class ParseRealtimeEntriesTests(unittest.TestCase):
    def test_produces_one_entry_per_station_and_magnitude(self):
        entries = parse_realtime_entries(REALTIME_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 11)


class GroupByStationTests(unittest.TestCase):
    def test_groups_entries_by_station_code(self):
        entries = parse_realtime_entries(REALTIME_PATH.read_text(encoding="utf-8"))
        groups = group_by_station(entries)

        self.assertEqual(set(groups.keys()), {"102", "104", "999"})
        self.assertEqual(len(groups["102"]), 8)  # 7 magnitudes conocidas + 1 desconocida
        self.assertEqual(len(groups["104"]), 2)
        self.assertEqual(len(groups["999"]), 1)


class NormalizeStationRecordTests(unittest.TestCase):
    def setUp(self):
        entries = parse_realtime_entries(REALTIME_PATH.read_text(encoding="utf-8"))
        self.groups = group_by_station(entries)
        self.stations = parse_stations(STATIONS_PATH.read_text(encoding="utf-8"))
        self.ingested_at = datetime(2026, 8, 12, 9, 15, 30, tzinfo=timezone.utc)

    def test_normalizes_a_station_combining_all_its_magnitudes(self):
        record = normalize_station_record("102", self.groups["102"], self.stations, self.ingested_at)

        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "madrid_meteorologia")
        self.assertEqual(record["station_id"], "28079102")
        self.assertEqual(record["station_name"], "J.M.D. Moratalaz")
        # H02/V02 es la lectura horaria válida más reciente de esta estación.
        self.assertEqual(record["temperature_c"], 25.6)
        self.assertEqual(record["humidity_pct"], 19.0)
        self.assertEqual(record["wind_speed_ms"], 1.0)
        self.assertEqual(record["wind_direction_deg"], 73.0)
        self.assertEqual(record["pressure_mb"], 941.0)
        self.assertEqual(record["solar_radiation_wm2"], 0.0)
        self.assertEqual(record["precipitation_lm2"], 0.0)
        # La magnitud 80 (UV) no está presente en la fuente para esta estación.
        self.assertIsNone(record["uv_radiation_mwm2"])
        self.assertEqual(record["measured_at"], "2026-08-12T02:00:00+02:00")
        self.assertEqual(record["ingested_at"], "2026-08-12T11:15:30+02:00")
        self.assertEqual(
            record["location"],
            {"lat": 40.398611, "lon": -3.636944, "srid": "EPSG:4326", "altitude_m": 686},
        )

    def test_ignores_unknown_magnitude_codes(self):
        record = normalize_station_record("102", self.groups["102"], self.stations, self.ingested_at)

        # La magnitud "99" (no reconocida en MAGNITUDES) no debe colarse como campo.
        self.assertNotIn("99", record)
        self.assertEqual(len(record), 16)  # esquema fijo, sin campos extra

    def test_normalizes_a_station_with_only_some_magnitudes(self):
        record = normalize_station_record("104", self.groups["104"], self.stations, self.ingested_at)

        self.assertEqual(record["station_id"], "28079104")
        self.assertEqual(record["wind_speed_ms"], 0.1)
        self.assertEqual(record["wind_direction_deg"], 156.0)
        self.assertIsNone(record["temperature_c"])
        self.assertIsNone(record["humidity_pct"])
        self.assertIsNone(record["pressure_mb"])

    def test_returns_none_for_a_station_with_no_valid_hour(self):
        record = normalize_station_record("999", self.groups["999"], self.stations, self.ingested_at)

        self.assertIsNone(record)

    def test_normalizes_a_station_unknown_in_catalog_to_null_metadata(self):
        unknown_entries = [dict(e, ESTACION="500") for e in self.groups["104"]]

        record = normalize_station_record("500", unknown_entries, self.stations, self.ingested_at)

        self.assertEqual(record["station_id"], "28079500")
        self.assertIsNone(record["station_name"])
        self.assertEqual(
            record["location"], {"lat": None, "lon": None, "srid": "EPSG:4326", "altitude_m": None}
        )

    def test_records_are_json_serializable(self):
        records = [
            normalize_station_record(code, entries, self.stations, self.ingested_at)
            for code, entries in self.groups.items()
        ]
        json.dumps(records)


class SampleFixtureTests(unittest.TestCase):
    """Verifica que la muestra commiteada en `capturas/samples/` es válida."""

    def test_committed_sample_matches_schema(self):
        sample_path = (
            Path(__file__).parent.parent / "capturas" / "samples" / "meteorologia_madrid_sample.json"
        )
        records = json.loads(sample_path.read_text(encoding="utf-8"))

        self.assertGreater(len(records), 0)
        self.assertLessEqual(len(records), 10)
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], "madrid_meteorologia")
            self.assertIn("station_id", record)
            self.assertIn("measured_at", record)
            self.assertIn("temperature_c", record)
            self.assertIn("humidity_pct", record)
            self.assertIn("wind_speed_ms", record)
            self.assertIn("precipitation_lm2", record)
            self.assertIn("location", record)
            self.assertIn("lat", record["location"])
            self.assertIn("lon", record["location"])


if __name__ == "__main__":
    unittest.main()
