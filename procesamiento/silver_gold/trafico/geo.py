"""Reproyección de coordenadas ETRS89/UTM huso 30N (EPSG:25830) a WGS84.

`trafico_madrid.py` (Bronze) deja `location.x`/`location.y` sin reproyectar
a propósito (ver doc/002, sección "Campos", y `ingesta/README.md`): "no se
reproyecta a lat/lon en esta tarea para no añadir una dependencia de
geoprocesado (p.ej. `pyproj`) sin necesidad". Esta tarea (041, Silver) es
justo esa mejora futura ya anunciada.

**Decisión: fórmulas cerradas en Python puro, sin `pyproj`.** `pyproj`
resolvería esto con una precisión mayor de la que este caso de uso necesita,
pero es un binding sobre la librería nativa PROJ (extensión compilada +
datos de rejilla), el mismo tipo de dependencia que ya causó fricción de
despliegue en este proyecto con `netCDF4` (ver doc/019, doc/032: hizo falta
una Lambda Layer construida con Docker/manylinux porque esta EC2 de
desarrollo no puede compilarla). Para una única conversión de un huso UTM
fijo (30N) a WGS84, las fórmulas cerradas de Snyder ("Map Projections – A
Working Manual", USGS, 1987, series de la latitud de pie de perpendicular)
dan precisión sub-milimétrica sin ninguna dependencia nativa — verificado en
esta tarea con una prueba de round-trip (`tests/test_geo.py`): proyectar un
punto conocido de Madrid a UTM con las fórmulas directas de Snyder y volver
a WGS84 con estas fórmulas inversas recupera el punto original con un error
menor a 1e-9 grados (~0.1 mm). Sobra precisión para sensores de tráfico
(coordenadas de un punto fijo en la calzada), y el job de Glue no necesita
instalar ningún módulo Python adicional para esto.

Se usa el elipsoide GRS80 (semieje mayor `a` e inverso de aplanamiento `f`
oficiales de ETRS89), prácticamente idéntico a WGS84 (difieren en el
aplanamiento a partir de la 10ª cifra decimal) — la diferencia entre
ETRS89 y WGS84 en Europa es de un par de centímetros, muy por debajo de la
resolución de cualquier dataset de este proyecto.
"""

from __future__ import annotations

import math
from typing import Optional

# Elipsoide GRS80 (ETRS89).
_SEMI_MAJOR_AXIS_M = 6378137.0
_INVERSE_FLATTENING = 298.257222101
_FLATTENING = 1 / _INVERSE_FLATTENING

# UTM: factor de escala en el meridiano central y falso este estándar.
_UTM_SCALE_FACTOR = 0.9996
_UTM_FALSE_EASTING_M = 500000.0

# Todos los puntos de medida de tráfico de Madrid caen en el huso 30N
# (España peninsular, salvo el extremo este que cae en el 31N — Madrid no).
DEFAULT_UTM_ZONE = 30

# Bounding box laxo de la Comunidad de Madrid (WGS84), usado como puerta de
# calidad de plausibilidad tras reproyectar (ver `trafico/transform.py`).
MADRID_BBOX_LAT = (39.8, 41.2)
MADRID_BBOX_LON = (-4.6, -3.0)


def utm_etrs89_to_wgs84(
    x: float, y: float, zone: int = DEFAULT_UTM_ZONE
) -> "tuple[float, float]":
    """Convierte un punto UTM (huso `zone`, hemisferio norte) a (lat, lon) WGS84.

    Implementa la fórmula inversa cerrada de Snyder (1987) para la
    proyección Transversa de Mercator, vía la latitud de pie de
    perpendicular (`phi1`). `x`/`y` son metros (este/norte) en el sistema
    de referencia de origen (EPSG:25830 para huso 30N); el resultado son
    grados decimales WGS84.
    """
    a = _SEMI_MAJOR_AXIS_M
    f = _FLATTENING
    e2 = f * (2 - f)
    e_prime2 = e2 / (1 - e2)
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    k0 = _UTM_SCALE_FACTOR
    lon0 = math.radians(zone * 6 - 183)

    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))

    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )

    sin_phi1 = math.sin(phi1)
    cos_phi1 = math.cos(phi1)
    tan_phi1 = math.tan(phi1)

    n1 = a / math.sqrt(1 - e2 * sin_phi1**2)
    t1 = tan_phi1**2
    c1 = e_prime2 * cos_phi1**2
    r1 = a * (1 - e2) / (1 - e2 * sin_phi1**2) ** 1.5
    d = (x - _UTM_FALSE_EASTING_M) / (n1 * k0)

    lat = phi1 - (n1 * tan_phi1 / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * e_prime2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * e_prime2 - 3 * c1**2)
        * d**6
        / 720
    )

    lon = lon0 + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * e_prime2 + 24 * t1**2)
        * d**5
        / 120
    ) / cos_phi1

    return math.degrees(lat), math.degrees(lon)


def reproject_optional(
    x: Optional[float], y: Optional[float], zone: int = DEFAULT_UTM_ZONE
) -> "tuple[Optional[float], Optional[float]]":
    """Igual que `utm_etrs89_to_wgs84`, pero propaga `None` si falta alguna coordenada."""
    if x is None or y is None:
        return None, None
    try:
        lat, lon = utm_etrs89_to_wgs84(x, y, zone=zone)
    except (ValueError, ZeroDivisionError):
        return None, None
    return lat, lon


def is_within_madrid_bbox(lat: Optional[float], lon: Optional[float]) -> bool:
    """Comprueba que `(lat, lon)` cae dentro del bounding box laxo de Madrid.

    Puerta de plausibilidad, no de precisión: detecta errores burdos
    (coordenadas sin reproyectar, invertidas, o de otro huso/hemisferio),
    no valida la posición exacta del sensor.
    """
    if lat is None or lon is None:
        return False
    lat_min, lat_max = MADRID_BBOX_LAT
    lon_min, lon_max = MADRID_BBOX_LON
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
