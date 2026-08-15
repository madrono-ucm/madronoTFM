"""Tests del productor de aforos de peatones y bicicletas de Madrid.

No hacen ninguna llamada de red: usan los fixtures
`fixtures/aforos_peatones_sample.csv` y `fixtures/aforos_bicicletas_sample.csv`
(copias reducidas y reales de filas de los CSV anuales de la fuente, tal
como los devolvió esta el 13/08/2026). Cada fixture reproduce a propósito la
estructura real del fichero de origen (agrupado por estación, no por fecha):
una fila de una fecha anterior (29/06/2024, debe descartarse) seguida de las
filas del último día real (30/06/2024), y en el caso de peatones una segunda
estación sin distrito asignado (para verificar el caso de metadatos vacíos).

`DownloadTests`/`FetchWithRetriesTests` sí sustituyen `requests.get` (sin red
real): cubren el arreglo del timeout de la tarea 040 (descarga en streaming
con un límite de tiempo total, ver docstring del módulo, "Timeout en
Lambda").
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import requests

from ingesta.capturas.aforos_peatones_bicicletas_madrid import (
    CaptureConfig,
    MODE_BICYCLE,
    MODE_PEDESTRIAN,
    _download,
    _fetch_with_retries,
    normalize_record,
    parse_latest_day_rows,
    select_sample_rows,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PEDESTRIAN_PATH = FIXTURES_DIR / "aforos_peatones_sample.csv"
BICYCLE_PATH = FIXTURES_DIR / "aforos_bicicletas_sample.csv"


def _make_config(**overrides) -> CaptureConfig:
    defaults = dict(
        pedestrian_url="https://example.invalid/peatones.csv",
        bicycle_url="https://example.invalid/bicicletas.csv",
        timeout_seconds=5.0,
        download_timeout_seconds=10.0,
        max_retries=2,
        retry_backoff_seconds=0.0,
        sample_stations=3,
        sample_hours_per_station=6,
    )
    defaults.update(overrides)
    return CaptureConfig(**defaults)


def _fake_streamed_response(chunks: "list[bytes]"):
    response = mock.MagicMock()
    response.raise_for_status = mock.Mock()
    response.iter_content = mock.Mock(return_value=iter(chunks))
    response.__enter__ = mock.Mock(return_value=response)
    response.__exit__ = mock.Mock(return_value=False)
    return response


class DownloadTests(unittest.TestCase):
    """Prueba `_download`, sustituyendo `requests.get` y `time.monotonic`."""

    def test_returns_concatenated_content_within_the_deadline(self):
        config = _make_config(download_timeout_seconds=10.0)
        response = _fake_streamed_response([b"chunk-1", b"chunk-2"])
        # Cada trozo llega 1s después del anterior: muy por debajo del plazo.
        with mock.patch(
            "ingesta.capturas.aforos_peatones_bicicletas_madrid.requests.get",
            return_value=response,
        ), mock.patch(
            "ingesta.capturas.aforos_peatones_bicicletas_madrid.time.monotonic",
            side_effect=[0.0, 1.0, 2.0],
        ):
            content = _download(config, config.pedestrian_url)

        self.assertEqual(content, b"chunk-1chunk-2")

    def test_raises_timeout_when_total_download_time_exceeds_the_deadline(self):
        # Simula el caso real diagnosticado en la tarea 040: cada trozo llega
        # dentro del timeout por lectura de `requests` (aquí no se simula
        # siquiera esa parte), pero la suma de trozos supera con creces el
        # límite total configurado, sin que `requests` levante nada por su
        # cuenta -- debe ser este código el que lo detecte y lo convierta en
        # un error explícito.
        config = _make_config(download_timeout_seconds=5.0)
        response = _fake_streamed_response([b"chunk-1", b"chunk-2", b"chunk-3"])
        with mock.patch(
            "ingesta.capturas.aforos_peatones_bicicletas_madrid.requests.get",
            return_value=response,
        ), mock.patch(
            "ingesta.capturas.aforos_peatones_bicicletas_madrid.time.monotonic",
            side_effect=[0.0, 2.0, 4.0, 6.0],
        ):
            with self.assertRaises(requests.exceptions.Timeout):
                _download(config, config.pedestrian_url)


class FetchWithRetriesTests(unittest.TestCase):
    """Prueba que un fallo de `_download` (p.ej. el timeout de arriba) entra
    en el mismo bucle de reintentos con backoff que ya usaba este módulo."""

    def test_retries_after_a_download_timeout_and_succeeds(self):
        config = _make_config(max_retries=2, retry_backoff_seconds=0.0)
        with mock.patch(
            "ingesta.capturas.aforos_peatones_bicicletas_madrid._download",
            side_effect=[requests.exceptions.Timeout("descarga demasiado lenta"), b"contenido-ok"],
        ) as fake_download:
            content = _fetch_with_retries(config, config.pedestrian_url)

        self.assertEqual(content, b"contenido-ok")
        self.assertEqual(fake_download.call_count, 2)

    def test_raises_runtime_error_after_exhausting_retries(self):
        config = _make_config(max_retries=2, retry_backoff_seconds=0.0)
        with mock.patch(
            "ingesta.capturas.aforos_peatones_bicicletas_madrid._download",
            side_effect=requests.exceptions.Timeout("descarga demasiado lenta"),
        ):
            with self.assertRaises(RuntimeError):
                _fetch_with_retries(config, config.pedestrian_url)


class ParseLatestDayRowsTests(unittest.TestCase):
    def test_keeps_only_rows_from_the_last_date_across_all_station_blocks(self):
        rows = parse_latest_day_rows(PEDESTRIAN_PATH.read_text(encoding="utf-8"))

        # 2 filas de PERM_PEA01_PM01 (30/06) + 1 de PERM_PEA21_PM01 (30/06);
        # se descarta la fila de PERM_PEA01_PM01 del 29/06, aunque aparezca
        # antes en el fichero que el bloque de la otra estación.
        self.assertEqual(len(rows), 3)
        dates = {row["fecha"].split(" ")[0] for row in rows}
        self.assertEqual(dates, {"30/06/2024"})
        stations = {row["identificador"] for row in rows}
        self.assertEqual(stations, {"PERM_PEA01_PM01", "PERM_PEA21_PM01"})


class SelectSampleRowsTests(unittest.TestCase):
    def test_caps_stations_and_hours_per_station(self):
        rows = parse_latest_day_rows(PEDESTRIAN_PATH.read_text(encoding="utf-8"))

        sample = select_sample_rows(rows, max_stations=1, max_hours_per_station=1)

        self.assertEqual(len(sample), 1)
        self.assertEqual(sample[0]["identificador"], "PERM_PEA01_PM01")


class NormalizeRecordTests(unittest.TestCase):
    def setUp(self):
        self.ingested_at = datetime(2026, 8, 13, 9, 15, 30, tzinfo=timezone.utc)

    def test_normalizes_a_pedestrian_reading(self):
        rows = parse_latest_day_rows(PEDESTRIAN_PATH.read_text(encoding="utf-8"))
        row = next(r for r in rows if r["identificador"] == "PERM_PEA01_PM01" and r["hora"] == "0:00")

        record = normalize_record(row, MODE_PEDESTRIAN, self.ingested_at)

        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "madrid_aforos_peatones_bicicletas")
        self.assertEqual(record["station_id"], "PERM_PEA01_PM01")
        self.assertEqual(record["mode"], "peatones")
        self.assertEqual(record["measured_at"], "2024-06-30T00:00:00+02:00")
        self.assertEqual(record["ingested_at"], "2026-08-13T11:15:30+02:00")
        self.assertEqual(record["pedestrian_count"], 857)
        self.assertIsNone(record["bicycle_count"])
        self.assertEqual(record["district_code"], "1")
        self.assertEqual(record["district"], "Centro")
        self.assertEqual(record["address"], "Calle Arenal esquina San Martín")
        self.assertEqual(record["address_notes"], "Calle peatonal")
        self.assertEqual(
            record["location"], {"lat": 40.417386, "lon": -3.707141, "srid": "EPSG:4326"}
        )

    def test_normalizes_a_station_without_district(self):
        rows = parse_latest_day_rows(PEDESTRIAN_PATH.read_text(encoding="utf-8"))
        row = next(r for r in rows if r["identificador"] == "PERM_PEA21_PM01")

        record = normalize_record(row, MODE_PEDESTRIAN, self.ingested_at)

        self.assertIsNone(record["district_code"])
        self.assertIsNone(record["district"])
        self.assertEqual(record["pedestrian_count"], 2)

    def test_normalizes_a_bicycle_reading(self):
        rows = parse_latest_day_rows(BICYCLE_PATH.read_text(encoding="utf-8"))
        row = next(r for r in rows if r["identificador"] == "PERM_BICI01_PM01")

        record = normalize_record(row, MODE_BICYCLE, self.ingested_at)

        self.assertEqual(record["mode"], "bicicletas")
        self.assertIsNone(record["pedestrian_count"])
        self.assertEqual(record["bicycle_count"], 16)
        self.assertEqual(record["district"], "Arganzuela")

    def test_records_are_json_serializable(self):
        rows = parse_latest_day_rows(PEDESTRIAN_PATH.read_text(encoding="utf-8"))
        records = [normalize_record(r, MODE_PEDESTRIAN, self.ingested_at) for r in rows]
        json.dumps(records)


class SampleFixtureTests(unittest.TestCase):
    """Verifica que la muestra commiteada en `capturas/samples/` es válida."""

    def test_committed_sample_matches_schema(self):
        sample_path = (
            Path(__file__).parent.parent
            / "capturas"
            / "samples"
            / "aforos_peatones_bicicletas_madrid_sample.json"
        )
        records = json.loads(sample_path.read_text(encoding="utf-8"))

        self.assertGreater(len(records), 0)
        modes = set()
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], "madrid_aforos_peatones_bicicletas")
            self.assertIn(record["mode"], ("peatones", "bicicletas"))
            self.assertIn("station_id", record)
            self.assertIn("measured_at", record)
            self.assertIn("pedestrian_count", record)
            self.assertIn("bicycle_count", record)
            self.assertIn("location", record)
            self.assertIn("lat", record["location"])
            self.assertIn("lon", record["location"])
            # Solo uno de los dos conteos está relleno por registro (dos
            # redes de estaciones distintas, ver docstring del módulo).
            self.assertTrue(
                (record["pedestrian_count"] is None) != (record["bicycle_count"] is None)
            )
            modes.add(record["mode"])

        self.assertEqual(modes, {"peatones", "bicicletas"})


if __name__ == "__main__":
    unittest.main()
