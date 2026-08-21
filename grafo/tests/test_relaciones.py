import json
import unittest
from pathlib import Path

from grafo.nodos import barrios_from_bronze
from grafo.relaciones import (
    pertenece_a_from_barrio_node,
    pertenece_a_from_barrios,
    proximo_a,
    ubicado_en,
)

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "ingesta" / "capturas" / "samples"


def _load_sample(name: str) -> list:
    with open(SAMPLES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


class PerteneceATests(unittest.TestCase):
    def test_from_barrio_node(self):
        barrio_node = {"codigo": "011", "nombre": "Palacio", "distrito_codigo": "01"}
        self.assertEqual(
            pertenece_a_from_barrio_node(barrio_node),
            {"barrio_codigo": "011", "distrito_codigo": "01"},
        )

    def test_from_barrios_un_par_por_barrio(self):
        barrio_records = [
            {"neighbourhood_id": "011", "name": "Palacio", "district_id": "01"},
            {"neighbourhood_id": "021", "name": "Gaztambide", "district_id": "02"},
        ]
        barrio_nodes = barrios_from_bronze(barrio_records)
        relaciones = pertenece_a_from_barrios(barrio_nodes)
        self.assertEqual(
            relaciones,
            [
                {"barrio_codigo": "011", "distrito_codigo": "01"},
                {"barrio_codigo": "021", "distrito_codigo": "02"},
            ],
        )


class UbicadoEnTests(unittest.TestCase):
    def setUp(self):
        self.barrios = _load_sample("barrios_distritos_madrid_barrios_sample.json")

    def test_nodo_dentro_de_un_barrio_real(self):
        # Palacio Real de Madrid -> barrio "011" Palacio, mismo punto que
        # test_geo.py::FindBarrioTests.
        nodos_con_ubicacion = [
            {"id": "poi_madrid:1", "tipo": "poi_turistico", "ubicacion": {"lat": 40.4180, "lon": -3.7143}},
        ]
        self.assertEqual(
            ubicado_en(nodos_con_ubicacion, self.barrios),
            [{"nodo_id": "poi_madrid:1", "barrio_codigo": "011"}],
        )

    def test_nodo_sin_ubicacion_no_genera_relacion(self):
        nodos_con_ubicacion = [{"id": "cartelera_cines_estrenos:1", "tipo": "cine", "ubicacion": None}]
        self.assertEqual(ubicado_en(nodos_con_ubicacion, self.barrios), [])

    def test_nodo_fuera_de_todos_los_barrios_no_genera_relacion(self):
        nodos_con_ubicacion = [
            {"id": "poi_madrid:2", "tipo": "poi_turistico", "ubicacion": {"lat": 41.3874, "lon": 2.1686}},
        ]
        self.assertEqual(ubicado_en(nodos_con_ubicacion, self.barrios), [])

    def test_varios_nodos_mezclados(self):
        nodos_con_ubicacion = [
            {"id": "poi_madrid:1", "tipo": "poi_turistico", "ubicacion": {"lat": 40.4180, "lon": -3.7143}},
            {"id": "poi_madrid:2", "tipo": "poi_turistico", "ubicacion": {"lat": 41.3874, "lon": 2.1686}},
            {"id": "cartelera_cines_estrenos:1", "tipo": "cine", "ubicacion": None},
        ]
        self.assertEqual(
            ubicado_en(nodos_con_ubicacion, self.barrios),
            [{"nodo_id": "poi_madrid:1", "barrio_codigo": "011"}],
        )


class ProximoATests(unittest.TestCase):
    def test_pareja_de_tipos_distintos_dentro_del_umbral(self):
        # Puerta del Sol - Plaza Mayor, ~365 m (ver test_geo.py), por debajo
        # del umbral por defecto de 300... se sube el umbral aquí a 400 para
        # forzar el caso positivo con puntos reales conocidos.
        nodos_con_ubicacion = [
            {"id": "trafico:1", "tipo": "trafico", "ubicacion": {"lat": 40.4169, "lon": -3.7035}},
            {"id": "ruido:1", "tipo": "ruido", "ubicacion": {"lat": 40.4155, "lon": -3.7074}},
        ]
        relaciones = proximo_a(nodos_con_ubicacion, umbral_m=400)
        self.assertEqual(len(relaciones), 1)
        relacion = relaciones[0]
        self.assertEqual(relacion["origen_id"], "trafico:1")
        self.assertEqual(relacion["destino_id"], "ruido:1")
        self.assertTrue(300 < relacion["distancia_m"] < 400)

    def test_pareja_del_mismo_tipo_no_genera_relacion(self):
        nodos_con_ubicacion = [
            {"id": "trafico:1", "tipo": "trafico", "ubicacion": {"lat": 40.4169, "lon": -3.7035}},
            {"id": "trafico:2", "tipo": "trafico", "ubicacion": {"lat": 40.4170, "lon": -3.7036}},
        ]
        self.assertEqual(proximo_a(nodos_con_ubicacion), [])

    def test_pareja_fuera_del_umbral_no_genera_relacion(self):
        nodos_con_ubicacion = [
            {"id": "trafico:1", "tipo": "trafico", "ubicacion": {"lat": 40.4169, "lon": -3.7035}},
            {"id": "poi_madrid:1", "tipo": "poi_turistico", "ubicacion": {"lat": 41.3874, "lon": 2.1686}},
        ]
        self.assertEqual(proximo_a(nodos_con_ubicacion), [])

    def test_nodo_sin_ubicacion_se_ignora(self):
        nodos_con_ubicacion = [
            {"id": "trafico:1", "tipo": "trafico", "ubicacion": {"lat": 40.4169, "lon": -3.7035}},
            {"id": "ruido:1", "tipo": "ruido", "ubicacion": None},
        ]
        self.assertEqual(proximo_a(nodos_con_ubicacion), [])

    def test_umbral_por_defecto_300m(self):
        # Misma pareja que arriba (~365 m), con el umbral por defecto (300)
        # no debe generar relación.
        nodos_con_ubicacion = [
            {"id": "trafico:1", "tipo": "trafico", "ubicacion": {"lat": 40.4169, "lon": -3.7035}},
            {"id": "ruido:1", "tipo": "ruido", "ubicacion": {"lat": 40.4155, "lon": -3.7074}},
        ]
        self.assertEqual(proximo_a(nodos_con_ubicacion), [])

    def test_no_limita_el_numero_de_relaciones_por_nodo(self):
        origen = {"id": "trafico:1", "tipo": "trafico", "ubicacion": {"lat": 40.4169, "lon": -3.7035}}
        vecinos = [
            {"id": f"ruido:{i}", "tipo": "ruido", "ubicacion": {"lat": 40.4169 + i * 0.0001, "lon": -3.7035}}
            for i in range(20)
        ]
        relaciones = proximo_a([origen] + vecinos, umbral_m=300)
        self.assertEqual(len(relaciones), 20)


if __name__ == "__main__":
    unittest.main()
