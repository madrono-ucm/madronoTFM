import math
import unittest

from procesamiento.silver_gold.trafico.geo import (
    is_within_madrid_bbox,
    reproject_optional,
    utm_etrs89_to_wgs84,
)


def _latlon_to_utm_zone30_snyder_forward(lat_deg: float, lon_deg: float) -> "tuple[float, float]":
    """Fórmula directa de Snyder (independiente de `geo.py`), solo para el test de round-trip.

    Proyecta un punto WGS84 conocido a UTM huso 30N con el mismo elipsoide
    (GRS80) que usa `geo.utm_etrs89_to_wgs84`, para poder comprobar que la
    función inversa bajo test recupera el punto original sin depender de
    ninguna fuente externa (`pyproj`, servicios online, etc.) en este
    entorno de desarrollo sin acceso a esas dependencias.
    """
    a = 6378137.0
    f = 1 / 298.257222101
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    k0 = 0.9996
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    lon0 = math.radians(30 * 6 - 183)
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    t = math.tan(lat) ** 2
    c = ep2 * math.cos(lat) ** 2
    aa = (lon - lon0) * math.cos(lat)
    m = a * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * lat
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * lat)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * lat)
        - (35 * e2**3 / 3072) * math.sin(6 * lat)
    )
    x = k0 * n * (aa + (1 - t + c) * aa**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * ep2) * aa**5 / 120) + 500000.0
    y = k0 * (
        m
        + n
        * math.tan(lat)
        * (
            aa**2 / 2
            + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * ep2) * aa**6 / 720
        )
    )
    return x, y


class UtmToWgs84Tests(unittest.TestCase):
    def test_round_trip_recovers_original_point_within_a_millimetre(self):
        lat0, lon0 = 40.4168, -3.7038  # Puerta del Sol, Madrid (referencia conocida).
        x, y = _latlon_to_utm_zone30_snyder_forward(lat0, lon0)

        lat1, lon1 = utm_etrs89_to_wgs84(x, y)

        # ~1e-8 grados equivale a menos de un milímetro en latitud.
        self.assertAlmostEqual(lat1, lat0, places=8)
        self.assertAlmostEqual(lon1, lon0, places=8)

    def test_real_bronze_sample_point_reprojects_inside_madrid(self):
        # Punto real de doc/002-captura-datos-trafico-madrid.md (Bronze, tarea 002).
        lat, lon = utm_etrs89_to_wgs84(438339.375874991, 4480454.96970565)

        self.assertTrue(is_within_madrid_bbox(lat, lon))
        self.assertAlmostEqual(lat, 40.4725, places=3)
        self.assertAlmostEqual(lon, -3.7274, places=3)


class ReprojectOptionalTests(unittest.TestCase):
    def test_none_coordinates_propagate_as_none(self):
        self.assertEqual(reproject_optional(None, None), (None, None))
        self.assertEqual(reproject_optional(438339.0, None), (None, None))


class MadridBboxTests(unittest.TestCase):
    def test_null_island_is_outside_madrid(self):
        self.assertFalse(is_within_madrid_bbox(0.0, 0.0))

    def test_missing_coordinates_are_outside_madrid(self):
        self.assertFalse(is_within_madrid_bbox(None, None))

    def test_madrid_centre_is_inside(self):
        self.assertTrue(is_within_madrid_bbox(40.4168, -3.7038))


if __name__ == "__main__":
    unittest.main()
