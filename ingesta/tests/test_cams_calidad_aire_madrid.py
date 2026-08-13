"""Tests del productor de previsión de calidad del aire de CAMS para Madrid.

No hacen ninguna llamada de red. `fixtures/cams_forecast_sample.nc` es un
NetCDF sintético pero con la misma estructura real documentada del dataset
(dimensiones `time`/`latitude`/`longitude`, variable escalar
`forecast_reference_time`, variables `no2_conc`/`o3_conc`/`pm2p5_conc`/
`pm10_conc` con atributo `units`, ver docstring del módulo bajo prueba para
de dónde sale esa estructura) — no se ha podido generar con datos
descargados de verdad porque el registro en la ADS API está bloqueado (ver
docstring). `FetchForecastTests` prueba el flujo completo (`fetch_forecast`,
incluida la construcción del `.zip` y la llamada a `cdsapi.Client.retrieve`)
sustituyendo `cdsapi.Client` por un doble que escribe ese `.zip` sintético
en el `target` pedido, en vez de solo probar la normalización de forma
aislada.
"""

import io
import json
import sys
import types
import unittest
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

from ingesta.capturas.cams_calidad_aire_madrid import (
    DEFAULT_AREA,
    DEFAULT_POLLUTANTS,
    POLLUTANT_LABELS,
    POLLUTANT_VARIABLES,
    SOURCE,
    CaptureConfig,
    _build_request,
    _nearest_index,
    fetch_forecast,
    normalize_forecast_file,
    normalize_forecast_zip,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
NC_FIXTURE_PATH = FIXTURES_DIR / "cams_forecast_sample.nc"


def _zip_bytes(nc_bytes: bytes, member_name: str = "cams_madrid.nc") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member_name, nc_bytes)
    return buffer.getvalue()


class BuildRequestTests(unittest.TestCase):
    def test_matches_the_real_ads_process_schema(self):
        config = CaptureConfig(
            api_key="token",
            api_url="https://ads.atmosphere.copernicus.eu/api",
            pollutants=list(DEFAULT_POLLUTANTS),
            area=list(DEFAULT_AREA),
            model="ensemble",
            level="0",
            leadtime_hours=["0", "1", "2", "3"],
            run_time="00:00",
        )
        request = _build_request(config, date(2026, 8, 13))
        self.assertEqual(request["variable"], DEFAULT_POLLUTANTS)
        self.assertEqual(request["model"], ["ensemble"])
        self.assertEqual(request["level"], ["0"])
        self.assertEqual(request["type"], ["forecast"])
        self.assertEqual(request["date"], ["2026-08-13/2026-08-13"])
        self.assertEqual(request["time"], ["00:00"])
        self.assertEqual(request["leadtime_hour"], ["0", "1", "2", "3"])
        self.assertEqual(request["data_format"], "netcdf_zip")
        self.assertEqual(request["area"], DEFAULT_AREA)

    def test_only_validated_pollutants_are_offered(self):
        # Restricción explícita de la tarea: solo los 7 contaminantes que CAMS
        # documenta como regularmente validados contra observaciones in situ.
        self.assertEqual(
            set(POLLUTANT_VARIABLES.keys()),
            {
                "nitrogen_dioxide",
                "nitrogen_monoxide",
                "sulphur_dioxide",
                "ozone",
                "particulate_matter_2.5um",
                "particulate_matter_10um",
                "dust",
            },
        )
        self.assertEqual(set(POLLUTANT_LABELS.keys()), set(POLLUTANT_VARIABLES.keys()))


class NearestIndexTests(unittest.TestCase):
    def test_finds_closest_value(self):
        self.assertEqual(_nearest_index([40.55, 40.425, 40.30], 40.4168), 1)

    def test_handles_exact_match(self):
        self.assertEqual(_nearest_index([1.0, 2.0, 3.0], 3.0), 2)


class NormalizeForecastFileTests(unittest.TestCase):
    def setUp(self):
        self.nc_bytes = NC_FIXTURE_PATH.read_bytes()
        self.captured_at = datetime(2026, 8, 13, 7, 0, 0, tzinfo=timezone.utc)

    def test_normalizes_one_record_per_pollutant_and_hour(self):
        records = normalize_forecast_file(self.nc_bytes, self.captured_at, is_mock=True)
        # 4 contaminantes (no2, o3, pm2.5, pm10) x 4 horas de leadtime = 16.
        self.assertEqual(len(records), 16)
        pollutants = {r["pollutant_code"] for r in records}
        self.assertEqual(pollutants, {"nitrogen_dioxide", "ozone", "particulate_matter_2.5um", "particulate_matter_10um"})

    def test_picks_the_grid_point_nearest_to_madrid_center(self):
        records = normalize_forecast_file(self.nc_bytes, self.captured_at)
        latitudes = {r["latitude"] for r in records}
        longitudes = {r["longitude"] for r in records}
        # La rejilla del fixture es [40.55, 40.425, 40.30] / [-3.85, -3.70, -3.55];
        # el punto más cercano al centro de Madrid (40.4168, -3.7038) es (40.425, -3.70).
        self.assertEqual(latitudes, {40.425})
        self.assertEqual(longitudes, {-3.7})

    def test_leadtime_hour_and_datetimes_are_correct(self):
        records = normalize_forecast_file(self.nc_bytes, self.captured_at)
        no2_records = sorted(
            (r for r in records if r["pollutant_code"] == "nitrogen_dioxide"), key=lambda r: r["leadtime_hour"]
        )
        self.assertEqual([r["leadtime_hour"] for r in no2_records], [0, 1, 2, 3])
        self.assertEqual(no2_records[0]["valid_datetime"], "2026-08-13T00:00:00+00:00")
        self.assertEqual(no2_records[3]["valid_datetime"], "2026-08-13T03:00:00+00:00")
        self.assertTrue(all(r["forecast_issued_at"] == "2026-08-13T00:00:00+00:00" for r in no2_records))

    def test_records_carry_source_schema_and_units(self):
        records = normalize_forecast_file(self.nc_bytes, self.captured_at)
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], SOURCE)
            self.assertEqual(record["unit"], "µg m-3")
            self.assertEqual(record["model"], "ensemble")
            self.assertFalse(record["is_mock"])

    def test_records_are_json_serializable(self):
        records = normalize_forecast_file(self.nc_bytes, self.captured_at)
        json.dumps(records)

    def test_ignores_pollutant_variables_not_present_in_the_file(self):
        # El fixture no trae so2_conc/no_conc/dust_conc; no debe fallar, solo
        # no generar registros para esos contaminantes (ver docstring del
        # módulo: no_conc/dust_conc son un mapeo sin contrastar).
        records = normalize_forecast_file(self.nc_bytes, self.captured_at)
        self.assertNotIn("sulphur_dioxide", {r["pollutant_code"] for r in records})
        self.assertNotIn("nitrogen_monoxide", {r["pollutant_code"] for r in records})
        self.assertNotIn("dust", {r["pollutant_code"] for r in records})


class NormalizeForecastZipTests(unittest.TestCase):
    def test_extracts_and_normalizes_every_nc_member(self):
        nc_bytes = NC_FIXTURE_PATH.read_bytes()
        zip_bytes = _zip_bytes(nc_bytes)
        captured_at = datetime(2026, 8, 13, 7, 0, 0, tzinfo=timezone.utc)
        records = normalize_forecast_zip(zip_bytes, captured_at)
        self.assertEqual(len(records), 16)

    def test_ignores_non_nc_members(self):
        nc_bytes = NC_FIXTURE_PATH.read_bytes()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("cams_madrid.nc", nc_bytes)
            archive.writestr("readme.txt", "no es un NetCDF")
        captured_at = datetime(2026, 8, 13, 7, 0, 0, tzinfo=timezone.utc)
        records = normalize_forecast_zip(buffer.getvalue(), captured_at)
        self.assertEqual(len(records), 16)


class FetchForecastTests(unittest.TestCase):
    """Prueba el flujo completo (petición -> cdsapi -> zip -> normalización).

    Sustituye `cdsapi.Client` por un doble que, en vez de llamar a la red,
    escribe el `.zip` sintético (construido a partir del fixture NetCDF) en
    el `target` que le pasa `_fetch_forecast_zip_bytes`. `cdsapi` no está
    importado a nivel de módulo (import perezoso dentro de
    `_fetch_forecast_zip_bytes`) precisamente para poder sustituirlo así sin
    depender de que esté instalado en todos los entornos que solo necesiten
    normalizar/testear.
    """

    def setUp(self):
        self.nc_bytes = NC_FIXTURE_PATH.read_bytes()
        self.zip_bytes = _zip_bytes(self.nc_bytes)

        fake_cdsapi = types.ModuleType("cdsapi")

        class FakeClient:
            def __init__(self, url, key):
                self.url = url
                self.key = key
                self.requests = []

            def retrieve(fake_self, name, request, target):
                fake_self.requests.append((name, request, target))
                Path(target).write_bytes(self.zip_bytes)

        fake_cdsapi.Client = FakeClient
        self.fake_cdsapi = fake_cdsapi
        self.addCleanup(sys.modules.pop, "cdsapi", None)
        sys.modules["cdsapi"] = fake_cdsapi

    def test_fetch_forecast_downloads_and_normalizes(self):
        config = CaptureConfig(
            api_key="fake-token",
            api_url="https://ads.atmosphere.copernicus.eu/api",
            pollutants=list(DEFAULT_POLLUTANTS),
            area=list(DEFAULT_AREA),
            model="ensemble",
            level="0",
            leadtime_hours=["0", "1", "2", "3"],
            run_time="00:00",
        )
        records = fetch_forecast(config, run_date=date(2026, 8, 13))
        self.assertEqual(len(records), 16)
        self.assertTrue(all(r["source"] == "cams" for r in records))

    def test_does_not_leave_the_temporary_zip_on_disk(self):
        config = CaptureConfig(
            api_key="fake-token",
            api_url="https://ads.atmosphere.copernicus.eu/api",
            pollutants=list(DEFAULT_POLLUTANTS),
            area=list(DEFAULT_AREA),
            model="ensemble",
            level="0",
            leadtime_hours=["0"],
            run_time="00:00",
        )
        captured_targets = []
        original_retrieve = self.fake_cdsapi.Client.retrieve

        def spying_retrieve(fake_self, name, request, target):
            captured_targets.append(Path(target))
            return original_retrieve(fake_self, name, request, target)

        self.fake_cdsapi.Client.retrieve = spying_retrieve
        fetch_forecast(config, run_date=date(2026, 8, 13))
        self.assertEqual(len(captured_targets), 1)
        self.assertFalse(captured_targets[0].exists())


class SampleFixtureTests(unittest.TestCase):
    """Verifica que la muestra commiteada en `capturas/samples/` es válida."""

    def test_sample_matches_schema(self):
        sample_path = Path(__file__).parent.parent / "capturas" / "samples" / "cams_calidad_aire_madrid_sample.json"
        records = json.loads(sample_path.read_text(encoding="utf-8"))
        self.assertGreater(len(records), 0)
        required_keys = {
            "schema_version",
            "source",
            "pollutant",
            "pollutant_code",
            "value",
            "unit",
            "valid_datetime",
            "forecast_issued_at",
            "leadtime_hour",
            "model",
            "latitude",
            "longitude",
            "captured_at",
            "is_mock",
        }
        for record in records:
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], SOURCE)
            self.assertTrue(required_keys.issubset(record.keys()))
            self.assertIn(record["pollutant_code"], POLLUTANT_VARIABLES)
            self.assertTrue(record["is_mock"])


if __name__ == "__main__":
    unittest.main()
