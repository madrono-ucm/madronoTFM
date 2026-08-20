"""Tests de `grafo.nodos` -- Python puro, sin el driver `neo4j` instalado.

Los fixtures de `:Distrito`/`:Barrio` (`barrios_distritos_madrid`, sin
Silver/Gold) y de `:ParadaTransporte`/`crtm` y `:Lugar`/`poi_madrid` (Bronze,
sin Silver/Gold) son las muestras reales ya commitadas en
`ingesta/capturas/samples/` -- se cargan directamente en vez de duplicarlas,
tal como pide la tarea 067.

Los fixtures de Gold (`trafico`, `calidad_aire`, `ruido`,
`transporte_publico_emt`, `bicimad`, `aparcamientos`,
`cartelera_cines_estrenos`) se construyen a mano en este fichero, mismo
patrón que `procesamiento/tests/test_bicimad_aggregate.py` (que hand-builds
registros Silver): no existe ningún fixture de Gold commiteado en el
repositorio (Gold solo se genera ejecutando `aggregate.py` sobre Silver, y
Silver no está commiteado), así que se replican a mano las claves exactas
que produce cada `aggregate_silver_to_gold` real (ver
`procesamiento/silver_gold/<dataset>/aggregate.py`).
"""

import json
import unittest
from pathlib import Path

from grafo.nodos import (
    barrio_from_bronze,
    barrios_from_bronze,
    dedupe_nodes,
    distrito_from_bronze,
    distritos_from_bronze,
    estacion_medida_from_calidad_aire_gold,
    estacion_medida_from_ruido_gold,
    estacion_medida_from_trafico_gold,
    estaciones_medida_from_calidad_aire_gold,
    estaciones_medida_from_ruido_gold,
    estaciones_medida_from_trafico_gold,
    lugar_from_aparcamientos_gold,
    lugar_from_cartelera_cines_gold,
    lugar_from_poi_bronze,
    lugares_from_poi_bronze,
    parada_transporte_from_bicimad_gold,
    parada_transporte_from_transporte_publico_emt_gold,
    paradas_transporte_from_crtm_bronze,
)

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "ingesta" / "capturas" / "samples"


def _load_sample(name: str):
    with open(SAMPLES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


class DistritoBarrioTests(unittest.TestCase):
    def setUp(self):
        self.distrito_records = _load_sample("barrios_distritos_madrid_distritos_sample.json")
        self.barrio_records = _load_sample("barrios_distritos_madrid_barrios_sample.json")

    def test_distrito_from_bronze(self):
        node = distrito_from_bronze(self.distrito_records[0])
        self.assertEqual(node, {"codigo": "01", "nombre": "Centro"})

    def test_distrito_from_bronze_sin_district_id_es_none(self):
        self.assertIsNone(distrito_from_bronze({"name": "Sin código"}))

    def test_barrio_from_bronze(self):
        node = barrio_from_bronze(self.barrio_records[0])
        self.assertEqual(
            node, {"codigo": "011", "nombre": "Palacio", "distrito_codigo": "01"}
        )

    def test_distritos_from_bronze_dedup(self):
        nodes = distritos_from_bronze(self.distrito_records + self.distrito_records)
        self.assertEqual(len(nodes), len(self.distrito_records))
        codigos = {n["codigo"] for n in nodes}
        self.assertEqual(len(codigos), len(nodes))

    def test_barrios_from_bronze(self):
        nodes = barrios_from_bronze(self.barrio_records)
        self.assertEqual(len(nodes), len(self.barrio_records))
        for node in nodes:
            self.assertIsNotNone(node["distrito_codigo"])


def _trafico_gold_record(point_id, lat=40.4, lon=-3.7):
    return {
        "schema_version": 1,
        "point_id": point_id,
        "subarea": "M30",
        "date": "2026-08-15",
        "hour": 12,
        "avg_intensity_vph": 300.0,
        "location": {"lat": lat, "lon": lon, "srid": "EPSG:4326"},
        "processed_at": "2026-08-15T13:00:00+00:00",
    }


def _calidad_aire_gold_record(station_id, pollutant="NO2"):
    return {
        "schema_version": 1,
        "station_id": station_id,
        "station_name": "Escuelas Aguirre",
        "pollutant": pollutant,
        "date": "2026-08-15",
        "hour": 12,
        "avg_value": 20.3,
        "location": {"lat": 40.42, "lon": -3.68, "srid": "EPSG:4326"},
        "processed_at": "2026-08-15T13:00:00+00:00",
    }


def _ruido_gold_record(station_id):
    return {
        "schema_version": 1,
        "station_id": station_id,
        "station_name": "Plaza del Carmen",
        "period": "D",
        "date": "2026-08-15",
        "avg_laeq_db": 63.0,
        "location": {"lat": 40.41, "lon": -3.70, "srid": "EPSG:4326"},
        "processed_at": "2026-08-15T13:00:00+00:00",
    }


class EstacionMedidaTests(unittest.TestCase):
    def test_from_trafico_gold(self):
        node = estacion_medida_from_trafico_gold(_trafico_gold_record("1009"))
        self.assertEqual(
            node,
            {
                "id": "trafico:1009",
                "tipo": "trafico",
                "fuente": "trafico",
                "nombre": None,
                "ubicacion": {"lat": 40.4, "lon": -3.7},
            },
        )

    def test_from_calidad_aire_gold(self):
        node = estacion_medida_from_calidad_aire_gold(_calidad_aire_gold_record("28079004"))
        self.assertEqual(node["id"], "calidad_aire:28079004")
        self.assertEqual(node["tipo"], "calidad_aire")
        self.assertEqual(node["nombre"], "Escuelas Aguirre")

    def test_from_ruido_gold(self):
        node = estacion_medida_from_ruido_gold(_ruido_gold_record("RF-01"))
        self.assertEqual(node["id"], "ruido:RF-01")
        self.assertEqual(node["tipo"], "ruido")

    def test_sin_point_id_es_none(self):
        self.assertIsNone(estacion_medida_from_trafico_gold({"location": {}}))

    def test_dedup_por_hora_trafico(self):
        # Gold trae una fila por (point_id, fecha, hora): dos horas del mismo
        # punto deben colapsar a un único nodo :EstacionMedida.
        records = [_trafico_gold_record("1009"), {**_trafico_gold_record("1009"), "hour": 13}]
        nodes = estaciones_medida_from_trafico_gold(records)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["id"], "trafico:1009")

    def test_dedup_por_contaminante_calidad_aire(self):
        # calidad_aire agrega por (station_id, pollutant, fecha, hora): la
        # misma estación con dos contaminantes distintos es un único nodo.
        records = [
            _calidad_aire_gold_record("28079004", pollutant="NO2"),
            _calidad_aire_gold_record("28079004", pollutant="O3"),
        ]
        nodes = estaciones_medida_from_calidad_aire_gold(records)
        self.assertEqual(len(nodes), 1)

    def test_dedup_por_periodo_ruido(self):
        records = [_ruido_gold_record("RF-01"), {**_ruido_gold_record("RF-01"), "period": "N"}]
        nodes = estaciones_medida_from_ruido_gold(records)
        self.assertEqual(len(nodes), 1)


def _emt_gold_record(stop_id, line="203"):
    return {
        "schema_version": 1,
        "stop_id": stop_id,
        "line": line,
        "date": "2026-08-15",
        "hour": 10,
        "avg_estimate_arrive_sec": 300.0,
        "processed_at": "2026-08-15T13:00:00+00:00",
    }


def _bicimad_gold_record(station_id):
    return {
        "schema_version": 1,
        "station_id": station_id,
        "name": "2 - Metro Callao",
        "date": "2026-08-15",
        "hour": 10,
        "avg_bikes_available": 3.0,
        "location": {"lat": 40.4204, "lon": -3.70569, "srid": "EPSG:4326"},
        "processed_at": "2026-08-15T13:00:00+00:00",
    }


class ParadaTransporteTests(unittest.TestCase):
    def test_from_transporte_publico_emt_gold_sin_ubicacion(self):
        # Gold de transporte_publico_emt no trae ubicación de la parada
        # (location en Silver es la posición del autobús, no de la parada,
        # y no se agrega en Gold -- ver aggregate.py) ni nombre.
        node = parada_transporte_from_transporte_publico_emt_gold(_emt_gold_record("71"))
        self.assertEqual(
            node,
            {
                "id": "transporte_publico_emt:71",
                "tipo": "emt",
                "fuente": "transporte_publico_emt",
                "nombre": None,
                "ubicacion": None,
            },
        )

    def test_from_bicimad_gold(self):
        node = parada_transporte_from_bicimad_gold(_bicimad_gold_record("1406"))
        self.assertEqual(node["id"], "bicimad:1406")
        self.assertEqual(node["tipo"], "bicimad")
        self.assertEqual(node["nombre"], "2 - Metro Callao")
        self.assertEqual(node["ubicacion"], {"lat": 40.4204, "lon": -3.70569})

    def test_from_crtm_bronze_multiples_paradas_por_ruta(self):
        records = _load_sample("crtm_red_transporte_madrid_sample.json")
        nodes = paradas_transporte_from_crtm_bronze(records)
        # Al menos tantos nodos como paradas distintas en la primera ruta.
        first_route_stop_ids = {s["stop_id"] for s in records[0]["stops"]}
        self.assertGreaterEqual(len(nodes), len(first_route_stop_ids))
        by_id = {n["id"]: n for n in nodes}
        self.assertIn("crtm_red_transporte_madrid:par_4_263", by_id)
        node = by_id["crtm_red_transporte_madrid:par_4_263"]
        self.assertEqual(node["tipo"], "metro")
        self.assertEqual(node["nombre"], "PINAR DE CHAMARTIN")
        self.assertEqual(node["fuente"], "crtm_red_transporte_madrid")
        self.assertIsNotNone(node["ubicacion"])

    def test_from_crtm_bronze_dedup_parada_compartida_entre_rutas(self):
        # Una misma parada (mismo stop_id) que aparece en varias rutas del
        # mismo Bronze no debe producir nodos duplicados.
        route_a = {
            "mode": "metro",
            "stops": [{"stop_id": "s1", "name": "A", "location": {"lat": 1.0, "lon": 2.0}}],
        }
        route_b = {
            "mode": "metro",
            "stops": [{"stop_id": "s1", "name": "A", "location": {"lat": 1.0, "lon": 2.0}}],
        }
        nodes = paradas_transporte_from_crtm_bronze([route_a, route_b])
        self.assertEqual(len(nodes), 1)


def _aparcamientos_gold_record(parking_id):
    return {
        "schema_version": 1,
        "parking_id": parking_id,
        "name": "Aparcamiento Plaza Mayor",
        "date": "2026-08-15",
        "hour": 10,
        "avg_free_spaces": 50.0,
        "location": {"lat": 40.415, "lon": -3.707, "srid": "EPSG:4326"},
        "processed_at": "2026-08-15T13:00:00+00:00",
    }


def _cartelera_gold_record(cinema_id):
    return {
        "schema_version": 1,
        "movie_title": "Minions & Monsters",
        "movie_url": "https://www.sensacine.com/peliculas/pelicula-315380/",
        "cinema_id": cinema_id,
        "chain": "cinesa",
        "cinema_name": "Cinesa Proyecciones",
        "address": "Calle de Fuencarral 136",
        "postal_code": "28001",
        "locality": "Madrid",
        "date": "2026-08-15",
        "sessions_count": 3,
        "processed_at": "2026-08-15T13:00:00+00:00",
    }


class LugarTests(unittest.TestCase):
    def test_from_poi_bronze(self):
        records = _load_sample("poi_madrid_sample.json")
        node = lugar_from_poi_bronze(records[0])
        self.assertEqual(node["id"], f"poi_madrid:{records[0]['poi_id']}")
        self.assertEqual(node["tipo"], "poi_turistico")
        self.assertEqual(node["fuente"], "poi_madrid")
        self.assertEqual(node["nombre"], records[0]["name"])
        self.assertIsNotNone(node["ubicacion"])

    def test_lugares_from_poi_bronze_dedup(self):
        records = _load_sample("poi_madrid_sample.json")
        nodes = lugares_from_poi_bronze(records + records)
        self.assertEqual(len(nodes), len(records))

    def test_from_aparcamientos_gold(self):
        node = lugar_from_aparcamientos_gold(_aparcamientos_gold_record("APK001"))
        self.assertEqual(
            node,
            {
                "id": "aparcamientos:APK001",
                "nombre": "Aparcamiento Plaza Mayor",
                "tipo": "aparcamiento",
                "fuente": "aparcamientos",
                "ubicacion": {"lat": 40.415, "lon": -3.707},
            },
        )

    def test_from_cartelera_cines_gold_sin_ubicacion(self):
        # cartelera_cines_estrenos no trae coordenadas en ninguna etapa
        # (Bronze/Silver/Gold) -- ubicacion siempre None para este origen.
        node = lugar_from_cartelera_cines_gold(_cartelera_gold_record("cinesa_proyecciones"))
        self.assertEqual(
            node,
            {
                "id": "cartelera_cines_estrenos:cinesa_proyecciones",
                "nombre": "Cinesa Proyecciones",
                "tipo": "cine",
                "fuente": "cartelera_cines_estrenos",
                "ubicacion": None,
            },
        )


class DedupeNodesTests(unittest.TestCase):
    def test_ignora_none_y_conserva_el_primero(self):
        nodes = dedupe_nodes(
            [
                {"id": "a", "v": 1},
                None,
                {"id": "a", "v": 2},
                {"id": "b", "v": 3},
            ]
        )
        self.assertEqual(nodes, [{"id": "a", "v": 1}, {"id": "b", "v": 3}])


if __name__ == "__main__":
    unittest.main()
