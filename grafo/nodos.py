"""Extracción/transformación de nodos del grafo urbano (tarea 043/067).

Python puro (solo `stdlib`): sin `neo4j` como dependencia de import, mismo
motivo que `procesamiento/silver_gold/*/transform.py` (ver
`procesamiento/README.md`, "Por qué Python puro para la lógica"): así se
puede probar en cualquier entorno, incluida esta EC2 (disco limitado, sin
el driver de Neo4j instalado). `grafo/cypher.py` es la única pieza que
depende del driver, y solo para ejecutar (no para construir los `dict`).

Cada tipo de nodo tiene dos niveles de función, mismo patrón que
`validate_record`/`to_silver_record`/`bronze_to_silver` en `procesamiento/`:

- `<tipo>_from_<origen>(record)`: convierte **un** registro Gold/Bronze ya
  normalizado en el `dict` de propiedades de un nodo (o `None` si el
  registro no trae la clave de negocio mínima -- no debería ocurrir con
  datos reales que ya pasaron la puerta de calidad de Silver/Gold, pero se
  comprueba para no producir un nodo sin identidad).
- `<tipo>s_from_<origen>(records)`: aplica la función anterior a una lista
  de registros y deduplica por `id` (ver `dedupe_nodes`) -- necesario
  porque Gold trae una fila por punto de medida/estación **y hora** (o,
  en `crtm_red_transporte_madrid`, una fila por parada **y ruta**), no una
  fila por entidad única.

Los `dict` resultantes tienen exactamente las claves que documenta
`infra/neo4j/schema/schema.cypher` para cada label (`codigo`/`nombre` para
Distrito/Barrio; `id`/`tipo`/`fuente`/`ubicacion` para los otros tres) --
`ubicacion` es siempre `{"lat": ..., "lon": ...}` o `None` si el origen no
trae coordenadas (ver "Limitaciones de datos reales" en `grafo/README.md`),
nunca un objeto `Point` de Neo4j: eso lo construye `grafo/cypher.py`, la
única capa que conoce el tipo `Point` real de Neo4j.
"""

from __future__ import annotations

from typing import Iterable, Optional

from grafo import geo


def _location(record: dict) -> Optional[dict]:
    """Normaliza `record["location"]` (Gold/Silver, `{"lat", "lon", ...}`) a
    `{"lat", "lon"}`, o `None` si faltan las dos coordenadas."""
    location = record.get("location") or {}
    lat, lon = location.get("lat"), location.get("lon")
    if lat is None or lon is None:
        return None
    return {"lat": lat, "lon": lon}


def dedupe_nodes(nodes: "Iterable[Optional[dict]]") -> "list[dict]":
    """Deduplica una secuencia de nodos (algunos posiblemente `None`) por
    `id`/`codigo` (la que esté presente), conservando el primero visto.

    Gold es una serie por punto/estación **y hora** (o por parada y ruta en
    `crtm_red_transporte_madrid`); un nodo del grafo es una entidad única,
    así que hace falta colapsar antes de cargar. Se conserva el primer
    registro visto, no el más reciente: `aggregate.py` (Silver -> Gold) ya
    conserva como "representativas" las columnas casi constantes de un
    punto/estación (`location`, `name`...) tomándolas del primer registro
    del bucket -- son iguales en cualquier fila del mismo id salvo alguna
    corrección puntual de la fuente, así que quedarse con el primer valor
    visto aquí es un criterio consistente con el que ya usa Gold.
    """
    seen: "dict[object, dict]" = {}
    for node in nodes:
        if node is None:
            continue
        key = node.get("id", node.get("codigo"))
        if key is None or key in seen:
            continue
        seen[key] = node
    return list(seen.values())


# ---------------------------------------------------------------------------
# :Distrito / :Barrio -- desde `barrios_distritos_madrid` (Bronze, sin Silver/
# Gold, ver doc/010).
# ---------------------------------------------------------------------------


def distrito_from_bronze(record: dict) -> Optional[dict]:
    """`{codigo, nombre}` desde un registro de distrito de
    `barrios_distritos_madrid_distritos` (Bronze)."""
    codigo = record.get("district_id")
    if not codigo:
        return None
    return {"codigo": codigo, "nombre": record.get("name")}


def barrio_from_bronze(record: dict) -> Optional[dict]:
    """`{codigo, nombre, distrito_codigo}` desde un registro de barrio de
    `barrios_distritos_madrid_barrios` (Bronze).

    `distrito_codigo` es el mismo `district_id` que usa `PERTENECE_A`
    (`grafo/relaciones.py`) -- se conserva también como propiedad del nodo
    (ver `schema.cypher`, comentario de `:Barrio`) para poder filtrar por
    distrito sin atravesar la relación.
    """
    codigo = record.get("neighbourhood_id")
    distrito_codigo = record.get("district_id")
    if not codigo or not distrito_codigo:
        return None
    return {
        "codigo": codigo,
        "nombre": record.get("name"),
        "distrito_codigo": distrito_codigo,
    }


def distritos_from_bronze(records: "Iterable[dict]") -> "list[dict]":
    return dedupe_nodes(distrito_from_bronze(r) for r in records)


def barrios_from_bronze(records: "Iterable[dict]") -> "list[dict]":
    return dedupe_nodes(barrio_from_bronze(r) for r in records)


# ---------------------------------------------------------------------------
# :EstacionMedida -- desde Gold de `trafico`, `calidad_aire`, `ruido`.
# ---------------------------------------------------------------------------


def estacion_medida_from_trafico_gold(record: dict) -> Optional[dict]:
    point_id = record.get("point_id")
    if not point_id:
        return None
    return {
        "id": f"trafico:{point_id}",
        "tipo": "trafico",
        "fuente": "trafico",
        "nombre": None,  # Gold de trafico no trae un nombre legible del punto.
        "ubicacion": _location(record),
    }


def estacion_medida_from_calidad_aire_gold(record: dict) -> Optional[dict]:
    station_id = record.get("station_id")
    if not station_id:
        return None
    return {
        "id": f"calidad_aire:{station_id}",
        "tipo": "calidad_aire",
        "fuente": "calidad_aire",
        "nombre": record.get("station_name"),
        "ubicacion": _location(record),
    }


def estacion_medida_from_ruido_gold(record: dict) -> Optional[dict]:
    station_id = record.get("station_id")
    if not station_id:
        return None
    return {
        "id": f"ruido:{station_id}",
        "tipo": "ruido",
        "fuente": "ruido",
        "nombre": record.get("station_name"),
        "ubicacion": _location(record),
    }


def estaciones_medida_from_trafico_gold(records: "Iterable[dict]") -> "list[dict]":
    return dedupe_nodes(estacion_medida_from_trafico_gold(r) for r in records)


def estaciones_medida_from_calidad_aire_gold(records: "Iterable[dict]") -> "list[dict]":
    return dedupe_nodes(estacion_medida_from_calidad_aire_gold(r) for r in records)


def estaciones_medida_from_ruido_gold(records: "Iterable[dict]") -> "list[dict]":
    return dedupe_nodes(estacion_medida_from_ruido_gold(r) for r in records)


# ---------------------------------------------------------------------------
# :ParadaTransporte -- desde Gold de `transporte_publico_emt`, `bicimad`, y
# Bronze de `crtm_red_transporte_madrid` (sin Silver/Gold).
# ---------------------------------------------------------------------------


def parada_transporte_from_transporte_publico_emt_gold(record: dict) -> Optional[dict]:
    """Gold de `transporte_publico_emt` no trae ni nombre de parada ni
    ubicación fija (ver `procesamiento/silver_gold/transporte_publico_emt/
    aggregate.py`: `location` en Silver es la posición GPS del autobús en el
    instante de la estimación, no la de la parada, así que no se agrega ni
    se traslada a Gold -- ver `grafo/README.md`, "Limitaciones de datos
    reales"). El nodo se crea igualmente con `id`/`tipo`/`fuente` (identidad
    real y estable, `stop_id`), pero `nombre`/`ubicacion` quedan a `None`."""
    stop_id = record.get("stop_id")
    if not stop_id:
        return None
    return {
        "id": f"transporte_publico_emt:{stop_id}",
        "tipo": "emt",
        "fuente": "transporte_publico_emt",
        "nombre": None,
        "ubicacion": None,
    }


def parada_transporte_from_bicimad_gold(record: dict) -> Optional[dict]:
    station_id = record.get("station_id")
    if not station_id:
        return None
    return {
        "id": f"bicimad:{station_id}",
        "tipo": "bicimad",
        "fuente": "bicimad",
        "nombre": record.get("name"),
        "ubicacion": _location(record),
    }


def paradas_transporte_from_crtm_route_bronze(record: dict) -> "list[dict]":
    """Un registro Bronze de `crtm_red_transporte_madrid` es una **ruta**
    (`route_id`, `mode`) con una lista `stops` -- cada parada de la lista es
    un nodo `:ParadaTransporte` en potencia, así que esta función (a
    diferencia del resto del módulo) devuelve una **lista**, no un único
    `dict` u `None`, incluso para un solo registro de entrada.

    `tipo` toma el `mode` de la ruta tal cual lo publica CRTM (`"metro"`,
    `"metro_ligero"`, `"cercanias"`, o, confusamente, `"emt"` para las
    líneas interurbanas que gestiona CRTM bajo ese modo) -- **no** debe
    confundirse con el `tipo="emt"` que produce
    `parada_transporte_from_transporte_publico_emt_gold` arriba: son dos
    fuentes distintas (CRTM vs. la API de tiempo real de la EMT) con
    prefijo de `id`/`fuente` distinto (`crtm_red_transporte_madrid:` vs.
    `transporte_publico_emt:`), así que nunca colisionan en Neo4j, pero
    tampoco se deduplican entre sí aunque representen la misma parada física
    -- resolución de entidades entre fuentes queda fuera del alcance de esta
    tarea (ver `grafo/README.md`).
    """
    mode = record.get("mode")
    nodes = []
    for stop in record.get("stops") or []:
        stop_id = stop.get("stop_id")
        if not stop_id:
            continue
        location = stop.get("location") or {}
        lat, lon = location.get("lat"), location.get("lon")
        nodes.append(
            {
                "id": f"crtm_red_transporte_madrid:{stop_id}",
                "tipo": mode,
                "fuente": "crtm_red_transporte_madrid",
                "nombre": stop.get("name"),
                "ubicacion": {"lat": lat, "lon": lon} if lat is not None and lon is not None else None,
            }
        )
    return nodes


def paradas_transporte_from_transporte_publico_emt_gold(records: "Iterable[dict]") -> "list[dict]":
    return dedupe_nodes(parada_transporte_from_transporte_publico_emt_gold(r) for r in records)


def paradas_transporte_from_bicimad_gold(records: "Iterable[dict]") -> "list[dict]":
    return dedupe_nodes(parada_transporte_from_bicimad_gold(r) for r in records)


def paradas_transporte_from_crtm_bronze(records: "Iterable[dict]") -> "list[dict]":
    """`records` es la lista de registros Bronze de `crtm_red_transporte_madrid`
    (una fila por ruta); cada uno aporta varias paradas (`stops`)."""
    all_stops = (stop for record in records for stop in paradas_transporte_from_crtm_route_bronze(record))
    return dedupe_nodes(all_stops)


# ---------------------------------------------------------------------------
# :Lugar -- desde Gold de `aparcamientos`, `cartelera_cines_estrenos`, y
# Bronze de `poi_madrid` (sin Silver/Gold).
# ---------------------------------------------------------------------------


def lugar_from_poi_bronze(record: dict) -> Optional[dict]:
    poi_id = record.get("poi_id")
    if not poi_id:
        return None
    return {
        "id": f"poi_madrid:{poi_id}",
        "nombre": record.get("name"),
        "tipo": "poi_turistico",
        "fuente": "poi_madrid",
        "ubicacion": _location(record),
    }


def lugar_from_aparcamientos_gold(record: dict) -> Optional[dict]:
    parking_id = record.get("parking_id")
    if not parking_id:
        return None
    return {
        "id": f"aparcamientos:{parking_id}",
        "nombre": record.get("name"),
        "tipo": "aparcamiento",
        "fuente": "aparcamientos",
        "ubicacion": _location(record),
    }


def lugar_from_cartelera_cines_gold(record: dict) -> Optional[dict]:
    """Gold de `cartelera_cines_estrenos` no trae coordenadas (ver
    `procesamiento/silver_gold/cartelera_cines_estrenos/transform.py`: "no
    hace falta ningún geo.py ni columna location") -- `ubicacion` queda
    siempre a `None` para este origen, ver `grafo/README.md`."""
    cinema_id = record.get("cinema_id")
    if not cinema_id:
        return None
    return {
        "id": f"cartelera_cines_estrenos:{cinema_id}",
        "nombre": record.get("cinema_name"),
        "tipo": "cine",
        "fuente": "cartelera_cines_estrenos",
        "ubicacion": None,
    }


def lugares_from_poi_bronze(records: "Iterable[dict]") -> "list[dict]":
    return dedupe_nodes(lugar_from_poi_bronze(r) for r in records)


def lugares_from_aparcamientos_gold(records: "Iterable[dict]") -> "list[dict]":
    return dedupe_nodes(lugar_from_aparcamientos_gold(r) for r in records)


def lugares_from_cartelera_cines_gold(records: "Iterable[dict]") -> "list[dict]":
    return dedupe_nodes(lugar_from_cartelera_cines_gold(r) for r in records)


# ---------------------------------------------------------------------------
# Enriquecimiento de :Lugar con POIs de OpenStreetMap (tarea 083).
# ---------------------------------------------------------------------------

# Umbral de proximidad para considerar que un POI de OSM describe el mismo
# `:Lugar` -- fijado por el enunciado de la tarea 083, no derivado de ningún
# cálculo (a diferencia del umbral de 300m de `relaciones.proximo_a`, pensado
# para "cerca de", aquí se busca "es el mismo sitio").
OSM_MATCH_RADIUS_M = 30.0


def _osm_poi_coords(poi: dict) -> "Optional[tuple[float, float]]":
    location = poi.get("location") or {}
    lat, lon = location.get("lat"), location.get("lon")
    if lat is None or lon is None:
        return None
    return lat, lon


def enrich_lugar_con_osm(lugar: dict, osm_pois: "Iterable[dict]", radio_m: float = OSM_MATCH_RADIUS_M) -> dict:
    """Añade `osm_id`/`osm_amenity`/`osm_opening_hours` a `lugar` si hay un
    POI de OSM (`osm_pois`, registros normalizados por
    `ingesta.capturas.enriquecimiento_osm_lugares.normalize_record`) a
    `radio_m` metros o menos (Haversine, `grafo.geo.nearest_within_radius`).
    Si varios POIs de OSM caen dentro del radio, se queda con el más
    cercano.

    Sin match -- o sin `ubicacion` en `lugar` (p. ej. `:Lugar` de
    `cartelera_cines_estrenos`, ver "Limitaciones de datos reales" en
    `grafo/README.md`) --, devuelve `lugar` sin ninguna propiedad nueva: no
    se añaden propiedades `null` de más a un `:Lugar` sin match real, tal
    como pide el enunciado de la tarea 083."""
    ubicacion = lugar.get("ubicacion")
    if not ubicacion:
        return lugar
    match = geo.nearest_within_radius(ubicacion["lat"], ubicacion["lon"], osm_pois, radio_m, _osm_poi_coords)
    if match is None:
        return lugar
    enriched = dict(lugar)
    enriched["osm_id"] = f"{match.get('osm_type')}:{match.get('osm_id')}"
    enriched["osm_amenity"] = match.get("amenity")
    enriched["osm_opening_hours"] = match.get("opening_hours")
    return enriched


def enrich_lugares_con_osm(
    lugares: "Iterable[dict]", osm_pois: "Iterable[dict]", radio_m: float = OSM_MATCH_RADIUS_M
) -> "list[dict]":
    """Aplica `enrich_lugar_con_osm` a una lista de `:Lugar` ya construidos
    (p. ej. `lugares_from_poi_bronze(...) + lugares_from_aparcamientos_gold(...)
    + ...`). `osm_pois` se materializa una sola vez en una lista (no un
    generador) porque se recorre entero por cada `lugar`."""
    osm_pois = list(osm_pois)
    return [enrich_lugar_con_osm(lugar, osm_pois, radio_m) for lugar in lugares]
