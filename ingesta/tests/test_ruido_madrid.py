"""Tests del productor de ruido de Madrid.

No hacen ninguna llamada de red: usan los fixtures
`fixtures/ruido_diario_sample.csv` (copia reducida y real de filas del CSV
histórico diario de contaminación acústica, con la estación 1 y 2 tal como
las devolvió la fuente el 12/08/2026 para el último día disponible
[2026-08-10], más una fila de la estación 1 de un día anterior (2026-08-09)
para verificar el filtrado al último día, y una fila sintética de una
estación 99 que no existe en el catálogo, para verificar el caso de
metadatos desconocidos) y `fixtures/ruido_estaciones_sample.csv` (copia
reducida y real del catálogo de estaciones, con solo RF-01 y RF-02).
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.ruido_madrid import (
    normalize_record,
    parse_latest_day_entries,
    parse_stations,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DAILY_PATH = FIXTURES_DIR / "ruido_diario_sample.csv"
STATIONS_PATH = FIXTURES_DIR / "ruido_estaciones_sample.csv"


class ParseStationsTests(unittest.TestCase):
    def test_parses_known_stations_by_code(self):
        stations = parse_stations(STATIONS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(len(stations), 2)
        station = stations["RF-01"]
        self.assertEqual(station["name"], "Paseo de Recoletos")
        self.assertEqual(station["district"], "Centro")
        self.assertEqual(station["neighbourhood"], "Justicia")
        self.assertAlmostEqual(station["lat"], 40.422599)
        self.assertAlmostEqual(station["lon"], -3.691877)
        self.assertEqual(station["altitude_m"], 648)


class ParseLatestDayEntriesTests(unittest.TestCase):
    def test_keeps_only_rows_from_the_last_date_in_the_file(self):
        entries = parse_latest_day_entries(DAILY_PATH.read_text(encoding="utf-8"))

        # 4 periodos para la estación 1 + 4 para la estación 2 + 1 para la
        # estación 99, todas del 2026-08-10; se descarta la fila del
        # 2026-08-09 (fecha anterior).
        self.assertEqual(len(entries), 9)
        dates = {(e["Año"], e["Mes"], e["Día"]) for e in entries}
        self.assertEqual(dates, {("2026", "8", "10")})


class NormalizeRecordTests(unittest.TestCase):
    def setUp(self):
        self.stations = parse_stations(STATIONS_PATH.read_text(encoding="utf-8"))
        self.entries = parse_latest_day_entries(DAILY_PATH.read_text(encoding="utf-8"))
        self.ingested_at = datetime(2026, 8, 12, 9, 15, 30, tzinfo=timezone.utc)

    def test_normalizes_a_reading_with_known_station(self):
        entry = next(e for e in self.entries if e["Estación"] == "1" and e["Periodo"] == "D")

        record = normalize_record(entry, self.stations, self.ingested_at)

        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "madrid_ruido_diario")
        self.assertEqual(record["station_id"], "RF-01")
        self.assertEqual(record["station_name"], "Paseo de Recoletos")
        self.assertEqual(record["period"], "D")
        self.assertEqual(record["period_name"], "diurno")
        self.assertEqual(record["measured_date"], "2026-08-10")
        self.assertEqual(record["ingested_at"], "2026-08-12T09:15:30+00:00")
        self.assertEqual(record["laeq_db"], 62.9)
        self.assertEqual(record["l1_db"], 69.7)
        self.assertEqual(record["l99_db"], 52.2)
        self.assertEqual(
            record["location"],
            {"lat": 40.422599, "lon": -3.691877, "srid": "EPSG:4326", "altitude_m": 648},
        )

    def test_normalizes_a_reading_with_unknown_station_to_null_metadata(self):
        entry = next(e for e in self.entries if e["Estación"] == "99")

        record = normalize_record(entry, self.stations, self.ingested_at)

        self.assertEqual(record["station_id"], "RF-99")
        self.assertIsNone(record["station_name"])
        self.assertEqual(
            record["location"],
            {"lat": None, "lon": None, "srid": "EPSG:4326", "altitude_m": None},
        )

    def test_records_are_json_serializable(self):
        records = [normalize_record(e, self.stations, self.ingested_at) for e in self.entries]
        json.dumps(records)


class SampleFixtureTests(unittest.TestCase):
    """Verifica que la muestra commiteada en `capturas/samples/` es válida."""

    def test_committed_sample_matches_schema(self):
        sample_path = Path(__file__).parent.parent / "capturas" / "samples" / "ruido_madrid_sample.json"
        records = json.loads(sample_path.read_text(encoding="utf-8"))

        self.assertGreater(len(records), 0)
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], "madrid_ruido_diario")
            self.assertIn("station_id", record)
            self.assertIn("period", record)
            self.assertIn("laeq_db", record)
            self.assertIn("location", record)
            self.assertIn("lat", record["location"])
            self.assertIn("lon", record["location"])

        stations = {record["station_id"] for record in records}
        self.assertLessEqual(len(stations), 5)


if __name__ == "__main__":
    unittest.main()
