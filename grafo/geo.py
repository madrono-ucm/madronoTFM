"""Geometría en Python puro para las relaciones espaciales del grafo (tarea
070): point-in-polygon (para `UBICADO_EN`) y distancia Haversine (para
`PROXIMO_A`).

Sin `shapely` ni ninguna otra dependencia de geometría -- decisión ya tomada
por el enunciado, mismo criterio que evitó `pyproj` en la reproyección de
tráfico de la tarea 041: menos superficie de despliegue (ver el mismo tipo de
fricción que causó `netCDF4` en su día, `procesamiento/README.md`).
"""

from __future__ import annotations

import math
from typing import Iterable, Optional

_EARTH_RADIUS_M = 6371000.0


def _point_in_ring(lat: float, lon: float, ring: "list[list[float]]") -> bool:
    """Ray casting sobre un único anillo GeoJSON (`[[lon, lat], ...]`, el
    formato real de `barrios_distritos_madrid`, ver `ingesta/capturas/
    samples/barrios_distritos_madrid_barrios_sample.json`: cada punto es
    `[longitud, latitud]`, no `[lat, lon]`)."""
    inside = False
    n = len(ring)
    for i in range(n):
        lon1, lat1 = ring[i][0], ring[i][1]
        lon2, lat2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (lat1 > lat) != (lat2 > lat):
            x_at_lat = (lon2 - lon1) * (lat - lat1) / (lat2 - lat1) + lon1
            if lon < x_at_lat:
                inside = not inside
    return inside


def _point_in_polygon_coords(lat: float, lon: float, polygon_coords: "list") -> bool:
    """`polygon_coords`: lista de anillos GeoJSON de un `Polygon` -- el
    primero es el anillo exterior, el resto (si los hay) son huecos. Un
    punto está dentro del polígono si cae dentro del anillo exterior y fuera
    de todos los huecos."""
    if not polygon_coords:
        return False
    if not _point_in_ring(lat, lon, polygon_coords[0]):
        return False
    return not any(_point_in_ring(lat, lon, hole) for hole in polygon_coords[1:])


def point_in_geometry(lat: float, lon: float, geometry: Optional[dict]) -> bool:
    """Soporta GeoJSON `Polygon` y `MultiPolygon`. El fixture real
    commiteado (`ingesta/capturas/samples/
    barrios_distritos_madrid_barrios_sample.json`, los 6 barrios de muestra)
    solo trae `"type": "Polygon"`, pero se soporta también `MultiPolygon`
    (lista de `Polygon`) por si el dataset completo de
    `barrios_distritos_madrid` -- no solo la muestra commiteada -- incluye
    algún barrio con varias partes desconectadas (Madrid tiene barrios así,
    p. ej. divididos por una vía de tren)."""
    geometry = geometry or {}
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geom_type == "Polygon":
        return _point_in_polygon_coords(lat, lon, coordinates)
    if geom_type == "MultiPolygon":
        return any(_point_in_polygon_coords(lat, lon, polygon) for polygon in coordinates)
    return False


def find_barrio(lat: float, lon: float, barrios: "Iterable[dict]") -> Optional[str]:
    """Devuelve el `neighbourhood_id` del primer barrio de `barrios`
    (registros Bronce de `barrios_distritos_madrid`, con `neighbourhood_id` +
    `geometry` -- el mismo `dict` que devuelve `extract.fetch_barrios_
    bronze()`, sin pasar por `nodos.barrio_from_bronze`, que no conserva la
    geometría) cuyo polígono contiene el punto, o `None` si no cae en
    ninguno. Los barrios de Madrid no se solapan entre sí, así que en datos
    reales no debería haber ambigüedad; si la hubiera, se conserva el
    primero encontrado en el orden de `barrios`."""
    for barrio in barrios:
        neighbourhood_id = barrio.get("neighbourhood_id")
        geometry = barrio.get("geometry")
        if not neighbourhood_id or not geometry:
            continue
        if point_in_geometry(lat, lon, geometry):
            return neighbourhood_id
    return None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia Haversine en metros entre dos puntos WGS84 (radio terrestre
    medio, 6371 km)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def nearest_within_radius(lat: float, lon: float, candidates: "Iterable", radius_m: float, get_coords) -> Optional[object]:
    """Devuelve el elemento de `candidates` más cercano (Haversine) a
    `(lat, lon)` dentro de `radius_m` metros, o `None` si ninguno cae dentro
    del radio.

    `get_coords(candidate)` debe devolver `(lat, lon)` del candidato, o
    `None` si no tiene coordenadas conocidas (se ignora sin error) -- así
    esta función es agnóstica del `dict`/objeto concreto que se le pase.
    Si varios candidatos caen dentro del radio, se queda con el más cercano
    (usado por `grafo.nodos.enrich_lugar_con_osm` para elegir un único POI de
    OpenStreetMap por `:Lugar` cuando hay varios próximos, tarea 083)."""
    best = None
    best_distance = None
    for candidate in candidates:
        coords = get_coords(candidate)
        if coords is None:
            continue
        candidate_lat, candidate_lon = coords
        distance = haversine_m(lat, lon, candidate_lat, candidate_lon)
        if distance <= radius_m and (best_distance is None or distance < best_distance):
            best = candidate
            best_distance = distance
    return best
