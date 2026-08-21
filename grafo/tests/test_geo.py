"""Tests de `grafo.geo` -- Python puro, sin ninguna dependencia de
geometría. Casos conocidos verificados contra el fixture real de
`barrios_distritos_madrid` (`ingesta/capturas/samples/
barrios_distritos_madrid_barrios_sample.json`), no geometrías inventadas."""

import json
import unittest
from pathlib import Path

from grafo.geo import find_barrio, haversine_m, point_in_geometry

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "ingesta" / "capturas" / "samples"


def _load_sample(name: str) -> list:
    with open(SAMPLES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


class PointInGeometryTests(unittest.TestCase):
    def setUp(self):
        barrios = _load_sample("barrios_distritos_madrid_barrios_sample.json")
        self.palacio = next(b for b in barrios if b["neighbourhood_id"] == "011")
        self.barrios = barrios

    def test_punto_real_dentro_del_barrio_real(self):
        # Palacio Real de Madrid, dentro del barrio "011" Palacio (distrito
        # "01" Centro) del fixture real.
        self.assertTrue(point_in_geometry(40.4180, -3.7143, self.palacio["geometry"]))

    def test_punto_claramente_fuera_de_madrid(self):
        # Plaza Catalunya, Barcelona -- muy lejos de cualquier barrio del
        # fixture.
        self.assertFalse(point_in_geometry(41.3874, 2.1686, self.palacio["geometry"]))

    def test_geometria_none_no_contiene_nada(self):
        self.assertFalse(point_in_geometry(40.4180, -3.7143, None))

    def test_tipo_de_geometria_desconocido_no_contiene_nada(self):
        self.assertFalse(point_in_geometry(40.4180, -3.7143, {"type": "Point", "coordinates": [-3.7143, 40.4180]}))

    def test_multipolygon_contiene_si_alguna_parte_contiene(self):
        multipolygon = {"type": "MultiPolygon", "coordinates": [self.palacio["geometry"]["coordinates"]]}
        self.assertTrue(point_in_geometry(40.4180, -3.7143, multipolygon))
        self.assertFalse(point_in_geometry(41.3874, 2.1686, multipolygon))


class FindBarrioTests(unittest.TestCase):
    def setUp(self):
        self.barrios = _load_sample("barrios_distritos_madrid_barrios_sample.json")

    def test_encuentra_el_barrio_real_que_contiene_el_punto(self):
        # Palacio Real de Madrid -> barrio "011" Palacio.
        self.assertEqual(find_barrio(40.4180, -3.7143, self.barrios), "011")

    def test_punto_fuera_de_todos_los_barrios_devuelve_none(self):
        self.assertIsNone(find_barrio(41.3874, 2.1686, self.barrios))

    def test_barrios_vacio_devuelve_none(self):
        self.assertIsNone(find_barrio(40.4180, -3.7143, []))

    def test_ignora_barrios_sin_geometria_o_sin_id(self):
        barrios = [{"neighbourhood_id": "999"}, {"geometry": self.barrios[0]["geometry"]}]
        self.assertIsNone(find_barrio(40.4180, -3.7143, barrios))


class HaversineTests(unittest.TestCase):
    def test_mismo_punto_distancia_cero(self):
        self.assertEqual(haversine_m(40.4180, -3.7143, 40.4180, -3.7143), 0.0)

    def test_distancia_conocida_puerta_del_sol_a_plaza_mayor(self):
        # Puerta del Sol (40.4169, -3.7035) a Plaza Mayor (40.4155, -3.7074)
        # -- unos 380 m en línea recta, distancia real conocida.
        distancia = haversine_m(40.4169, -3.7035, 40.4155, -3.7074)
        self.assertTrue(300 < distancia < 450, f"distancia inesperada: {distancia}")

    def test_madrid_a_barcelona_orden_de_magnitud_correcto(self):
        # Puerta del Sol a Plaza Catalunya: ~505 km en línea recta.
        distancia_km = haversine_m(40.4169, -3.7035, 41.3874, 2.1686) / 1000
        self.assertTrue(480 < distancia_km < 520, f"distancia inesperada: {distancia_km} km")


if __name__ == "__main__":
    unittest.main()
