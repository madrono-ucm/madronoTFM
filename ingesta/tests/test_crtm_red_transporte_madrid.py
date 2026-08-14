"""Tests de la carga batch puntual de la red de transporte de Madrid (GTFS, CRTM).

No hacen ninguna llamada de red. `_build_gtfs_zip` construye un ZIP GTFS
sintético en memoria (mismas columnas que los feeds reales de CRTM
inspeccionados en vivo durante esta sesión, ver docstring del módulo bajo
prueba), incluyendo a propósito los dos casos reales encontrados en la
fuente: una línea sin ningún `trip_id` (como la línea 3 de metro) y
elementos de accesibilidad con prefijo `acc_` en `stops.txt` que no deben
tratarse como paradas de embarque.

`FetchAndNormalizeModeTests` prueba el flujo completo (`fetch_and_normalize_mode`)
sustituyendo `fetch_gtfs_zip` por un doble que devuelve el ZIP sintético en
vez de llamar a la red.
"""

import io
import json
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from ingesta.capturas.crtm_red_transporte_madrid import (
    DEFAULT_MODES,
    MODE_FEEDS,
    SOURCE,
    CaptureConfig,
    _index_boarding_stops,
    _read_csv_member,
    _read_stop_times_for_trips,
    _select_representative_trip,
    fetch_and_normalize_mode,
    normalize_route,
    select_sample_routes,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PATH = Path(__file__).parent.parent / "capturas" / "samples" / "crtm_red_transporte_madrid_sample.json"

INGESTED_AT = datetime(2026, 8, 14, 3, 46, 26, tzinfo=timezone.utc)

ROUTES_CSV = (
    "route_id,agency_id,route_short_name,route_long_name,route_desc,route_type,route_url,route_color,route_text_color\r\n"
    "4__1___,CRTM,1,Pinar de Chamartín-Valdecarros,,1,https://www.crtm.es/4__1___.aspx,2DBEF0,FFFFFF\r\n"
    "4__3___,CRTM,3,Villaverde Alto-Moncloa,,1,https://www.crtm.es/4__3___.aspx,FFD000,000000\r\n"
)

# La línea 4__3___ no tiene ningún trip, igual que en el feed real de metro
# (ver docstring del módulo bajo prueba).
TRIPS_CSV = (
    "route_id,service_id,trip_id,trip_headsign,trip_short_name,direction_id,block_id,shape_id,wheelchair_accessible\r\n"
    "4__1___,4_I12,trip_dir1,VALDECARROS,,1,,4__1____1__IT_1,1\r\n"
    "4__1___,4_I12,trip_dir0,PINAR DE CHAMARTIN,,0,,4__1____2__IT_1,1\r\n"
)

# Incluye una parada real (par_4_1) y un elemento de accesibilidad (acc_*,
# location_type=2) que no debe aparecer como parada de la línea.
STOPS_CSV = (
    "stop_id,stop_code,stop_name,stop_desc,stop_lat,stop_lon,zone_id,stop_url,location_type,parent_station\r\n"
    "par_4_263,1,PINAR DE CHAMARTIN,,40.48014,-3.6668,A,http://www.crtm.es,0,est_90_1\r\n"
    "par_4_1,2,PLAZA DE CASTILLA,,40.4669,-3.68917,A,http://www.crtm.es,0,est_90_21\r\n"
    "acc_4_1_1040,2,Ascensor,,40.46555,-3.68877,,http://www.crtm.es,2,est_90_21\r\n"
)

STOP_TIMES_CSV = (
    "trip_id,arrival_time,departure_time,stop_id,stop_sequence,stop_headsign,pickup_type,drop_off_type,shape_dist_traveled\r\n"
    "trip_dir1,07:10:00,07:10:00,par_4_1,0,,,,\r\n"
    "trip_dir1,07:12:00,07:12:00,par_4_263,1,,,,\r\n"
    "trip_dir0,07:00:00,07:00:00,par_4_263,0,,,,\r\n"
    "trip_dir0,07:03:10,07:03:10,par_4_1,1,,,,\r\n"
    "trip_dir0,07:05:00,07:05:00,acc_4_1_1040,2,,,,\r\n"
)


def _build_gtfs_zip(
    routes_csv: str = ROUTES_CSV,
    trips_csv: str = TRIPS_CSV,
    stops_csv: str = STOPS_CSV,
    stop_times_csv: str = STOP_TIMES_CSV,
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("routes.txt", routes_csv)
        archive.writestr("trips.txt", trips_csv)
        archive.writestr("stops.txt", stops_csv)
        archive.writestr("stop_times.txt", stop_times_csv)
    return buffer.getvalue()


class ReadCsvMemberTests(unittest.TestCase):
    def test_reads_all_rows_as_dicts(self):
        with zipfile.ZipFile(io.BytesIO(_build_gtfs_zip())) as zf:
            rows = _read_csv_member(zf, "routes.txt")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["route_id"], "4__1___")


class ReadStopTimesForTripsTests(unittest.TestCase):
    def test_only_keeps_wanted_trip_ids_and_sorts_by_sequence(self):
        with zipfile.ZipFile(io.BytesIO(_build_gtfs_zip())) as zf:
            result = _read_stop_times_for_trips(zf, {"trip_dir0"})
        self.assertEqual(list(result.keys()), ["trip_dir0"])
        stop_ids = [row["stop_id"] for row in result["trip_dir0"]]
        self.assertEqual(stop_ids, ["par_4_263", "par_4_1", "acc_4_1_1040"])

    def test_empty_trip_id_set_returns_empty_dict(self):
        with zipfile.ZipFile(io.BytesIO(_build_gtfs_zip())) as zf:
            self.assertEqual(_read_stop_times_for_trips(zf, set()), {})

    def test_unknown_trip_id_yields_no_rows(self):
        with zipfile.ZipFile(io.BytesIO(_build_gtfs_zip())) as zf:
            result = _read_stop_times_for_trips(zf, {"does_not_exist"})
        self.assertEqual(result, {"does_not_exist": []})


class IndexBoardingStopsTests(unittest.TestCase):
    def test_excludes_accessibility_elements(self):
        rows = _read_csv_member(zipfile.ZipFile(io.BytesIO(_build_gtfs_zip())), "stops.txt")
        indexed = _index_boarding_stops(rows)
        self.assertEqual(set(indexed.keys()), {"par_4_263", "par_4_1"})
        self.assertNotIn("acc_4_1_1040", indexed)


class SelectRepresentativeTripTests(unittest.TestCase):
    def setUp(self):
        self.trips = _read_csv_member(zipfile.ZipFile(io.BytesIO(_build_gtfs_zip())), "trips.txt")

    def test_prefers_direction_zero(self):
        self.assertEqual(_select_representative_trip(self.trips, "4__1___"), "trip_dir0")

    def test_falls_back_to_first_trip_when_no_direction_zero(self):
        trips = [{"route_id": "R1", "trip_id": "only_dir1", "direction_id": "1"}]
        self.assertEqual(_select_representative_trip(trips, "R1"), "only_dir1")

    def test_returns_none_when_route_has_no_trips(self):
        # Caso real: la línea 3 de metro (4__3___) no tiene ningún trip.
        self.assertIsNone(_select_representative_trip(self.trips, "4__3___"))


class SelectSampleRoutesTests(unittest.TestCase):
    def test_takes_first_n_routes_in_file_order_with_their_trip(self):
        with zipfile.ZipFile(io.BytesIO(_build_gtfs_zip())) as zf:
            routes = _read_csv_member(zf, "routes.txt")
            trips = _read_csv_member(zf, "trips.txt")
        selected = select_sample_routes(routes, trips, sample_size=2)
        self.assertEqual([r["route_id"] for r, _ in selected], ["4__1___", "4__3___"])
        self.assertEqual(selected[0][1], "trip_dir0")
        self.assertIsNone(selected[1][1])


class NormalizeRouteTests(unittest.TestCase):
    def setUp(self):
        with zipfile.ZipFile(io.BytesIO(_build_gtfs_zip())) as zf:
            self.routes = _read_csv_member(zf, "routes.txt")
            self.trips = _read_csv_member(zf, "trips.txt")
            self.stops_by_id = _index_boarding_stops(_read_csv_member(zf, "stops.txt"))
            self.stop_times = _read_stop_times_for_trips(zf, {"trip_dir0"})

    def test_normalizes_route_with_ordered_boarding_stops_only(self):
        route = self.routes[0]
        record = normalize_route(route, "trip_dir0", self.stop_times, self.stops_by_id, "metro", INGESTED_AT)
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], SOURCE)
        self.assertEqual(record["mode"], "metro")
        self.assertEqual(record["route_id"], "4__1___")
        self.assertEqual(record["short_name"], "1")
        self.assertEqual(record["route_type"], "metro")
        self.assertEqual(record["color"], "2DBEF0")
        self.assertEqual(record["ingested_at"], "2026-08-14T03:46:26+00:00")
        # acc_4_1_1040 (location_type=2) queda excluida: solo 2 paradas reales.
        self.assertEqual([s["stop_id"] for s in record["stops"]], ["par_4_263", "par_4_1"])
        self.assertEqual([s["sequence"] for s in record["stops"]], [0, 1])
        self.assertEqual(record["stops"][0]["name"], "PINAR DE CHAMARTIN")
        self.assertEqual(record["stops"][0]["location"], {"lat": 40.48014, "lon": -3.6668, "srid": "EPSG:4326"})

    def test_route_without_any_trip_has_empty_stops(self):
        # Caso real: línea 3 de metro sin trips (ver docstring del módulo).
        route = self.routes[1]
        record = normalize_route(route, None, {}, self.stops_by_id, "metro", INGESTED_AT)
        self.assertEqual(record["route_id"], "4__3___")
        self.assertEqual(record["stops"], [])


class FetchAndNormalizeModeTests(unittest.TestCase):
    """Prueba el flujo completo, sustituyendo `fetch_gtfs_zip` por un doble."""

    def test_downloads_and_normalizes_a_mode_sample(self):
        config = CaptureConfig(
            modes=("metro",),
            routes_per_mode=2,
            timeout_seconds=5.0,
            max_retries=1,
            retry_backoff_seconds=0.0,
        )
        with mock.patch(
            "ingesta.capturas.crtm_red_transporte_madrid.fetch_gtfs_zip",
            return_value=_build_gtfs_zip(),
        ) as fake_fetch:
            records = fetch_and_normalize_mode(config, "metro", INGESTED_AT)

        fake_fetch.assert_called_once_with(config, "metro")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["route_id"], "4__1___")
        self.assertEqual(len(records[0]["stops"]), 2)
        self.assertEqual(records[1]["route_id"], "4__3___")
        self.assertEqual(records[1]["stops"], [])
        json.dumps(records)


class ModeFeedsTests(unittest.TestCase):
    def test_default_modes_are_registered_feeds(self):
        self.assertTrue(set(DEFAULT_MODES).issubset(set(MODE_FEEDS.keys())))

    def test_investigated_modes_are_all_present_in_the_catalogue(self):
        # Los 6 feeds GTFS encontrados en vivo en el catálogo DCAT de
        # datos.crtm.es (ver docstring del módulo): 4 en la muestra por
        # defecto y 2 soportados pero excluidos de ella (ver docstring).
        self.assertEqual(
            set(MODE_FEEDS.keys()),
            {"metro", "emt", "metro_ligero", "cercanias", "urbano_cm", "interurbano_cm"},
        )


class CommittedSampleTests(unittest.TestCase):
    """Verifica que la muestra commiteada en `capturas/samples/` es válida."""

    EXPECTED_KEYS = {
        "schema_version",
        "source",
        "mode",
        "route_id",
        "short_name",
        "long_name",
        "route_type",
        "color",
        "url",
        "ingested_at",
        "stops",
    }

    def test_sample_matches_schema(self):
        records = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
        self.assertGreater(len(records), 0)
        modes_seen = set()
        for record in records:
            self.assertEqual(set(record.keys()), self.EXPECTED_KEYS)
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["source"], SOURCE)
            self.assertIn(record["mode"], DEFAULT_MODES)
            modes_seen.add(record["mode"])
            for stop in record["stops"]:
                self.assertIn("stop_id", stop)
                self.assertIn("name", stop)
                self.assertIn("sequence", stop)
                self.assertIn("location", stop)
        self.assertEqual(modes_seen, set(DEFAULT_MODES))

    def test_cercanias_routes_have_no_stops_source_data_gap(self):
        # Hallazgo de calidad de datos documentado: el feed de cercanías de
        # CRTM no tiene trips/stop_times, así que sus líneas no pueden traer
        # paradas derivadas (ver docstring del módulo).
        records = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
        cercanias_records = [r for r in records if r["mode"] == "cercanias"]
        self.assertTrue(cercanias_records)
        self.assertTrue(all(r["stops"] == [] for r in cercanias_records))

    def test_at_least_one_mode_has_routes_with_real_stop_sequences(self):
        records = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
        self.assertTrue(any(len(r["stops"]) > 0 for r in records))


if __name__ == "__main__":
    unittest.main()
