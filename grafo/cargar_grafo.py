"""Entry point que encadena `extract.py` (Athena/S3 real, tarea 069) ->
`nodos.py`/`relaciones.py` (transformación, tareas 067/070/071) ->
`cypher.py` (carga real, tareas 067/070/071) para los 5 labels y las
relaciones `PERTENECE_A`, `UBICADO_EN`, `PROXIMO_A` y `CONECTADO_CON` que
cubre este directorio. Los `:Lugar` se enriquecen además con etiquetas de
OpenStreetMap antes de cargarse (`nodos.enrich_lugares_con_osm`, tarea 083).

**No se ejecuta contra ninguna instancia real en esta tarea.** Sigue
bloqueada el alta manual de AuraDB Free (tarea 043,
`infra/neo4j/README.md`) -- este módulo queda listo para invocarse
(`python3 -m grafo.cargar_grafo`) el día que exista una instancia, con las
variables de entorno `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`
(`NEO4J_DATABASE`, opcional, por defecto `"neo4j"`) ya configuradas -- ver
`infra/neo4j/README.md`, "Cómo se conectaría el proyecto".

Las funciones de `extract.py` ya usan solo lo desplegado en AWS a fecha de
esta tarea (workgroup Athena `madrono-tfm-dev-silver-gold`, tarea 066; bucket
Bronze `madrono-tfm-dev-bronze-222234418587`) -- no hace falta pasarles
ningún parámetro para que apunten a datos reales.
"""

from __future__ import annotations

import os

from grafo import extract, nodos, relaciones
from grafo.cypher import Neo4jLoader


def cargar_grafo(loader: Neo4jLoader) -> None:
    """Ejecuta la carga completa (nodos + `PERTENECE_A`/`UBICADO_EN`/
    `PROXIMO_A`/`CONECTADO_CON`) contra `loader`, leyendo los datos reales
    con `grafo.extract` en el momento de la llamada."""
    barrio_records = list(extract.fetch_barrios_bronze())
    barrio_nodes = nodos.barrios_from_bronze(barrio_records)

    loader.load_distritos(nodos.distritos_from_bronze(extract.fetch_distritos_bronze()))
    loader.load_barrios(barrio_nodes)

    estaciones_medida = (
        nodos.estaciones_medida_from_trafico_gold(extract.fetch_estaciones_trafico())
        + nodos.estaciones_medida_from_calidad_aire_gold(extract.fetch_estaciones_calidad_aire())
        + nodos.estaciones_medida_from_ruido_gold(extract.fetch_estaciones_ruido())
    )
    loader.load_estaciones_medida(estaciones_medida)

    rutas_crtm = list(extract.fetch_paradas_crtm_bronze())
    paradas_transporte = (
        nodos.paradas_transporte_from_transporte_publico_emt_gold(extract.fetch_paradas_emt())
        + nodos.paradas_transporte_from_bicimad_gold(extract.fetch_paradas_bicimad())
        + nodos.paradas_transporte_from_crtm_bronze(rutas_crtm)
    )
    loader.load_paradas_transporte(paradas_transporte)

    lugares = (
        nodos.lugares_from_poi_bronze(extract.fetch_poi_bronze())
        + nodos.lugares_from_aparcamientos_gold(extract.fetch_lugares_aparcamientos())
        + nodos.lugares_from_cartelera_cines_gold(extract.fetch_lugares_cartelera_cines())
    )
    # Enriquecimiento con POIs de OpenStreetMap (tarea 083): añade
    # osm_id/osm_amenity/osm_opening_hours a los :Lugar que tengan un POI de
    # OSM a <=30m, a partir de la muestra commiteada (ver
    # `extract.fetch_osm_pois_sample`, no repite la consulta Overpass real
    # en cada carga).
    lugares = nodos.enrich_lugares_con_osm(lugares, extract.fetch_osm_pois_sample())
    loader.load_lugares(lugares)

    loader.load_pertenece_a(relaciones.pertenece_a_from_barrios(barrio_nodes))

    # UBICADO_EN/PROXIMO_A: cualquier nodo con ubicación, de los 3 labels
    # que pueden tenerla (ver `schema.cypher`) -- Distrito/Barrio quedan
    # fuera (no tienen `ubicacion`, solo la geometría cruda de Bronze).
    nodos_con_ubicacion = estaciones_medida + paradas_transporte + lugares
    loader.load_ubicado_en(relaciones.ubicado_en(nodos_con_ubicacion, barrio_records))
    loader.load_proximo_a(relaciones.proximo_a(nodos_con_ubicacion))

    # CONECTADO_CON: adyacencia real de la red de transporte, solo a partir
    # de las rutas CRTM (tarea 071) -- `transporte_publico_emt`/`bicimad` no
    # traen secuencia de paradas por línea, ver `grafo/relaciones.py`.
    loader.load_conectado_con(relaciones.conectado_con(rutas_crtm))


def main() -> int:
    uri = os.environ["NEO4J_URI"]
    username = os.environ["NEO4J_USERNAME"]
    password = os.environ["NEO4J_PASSWORD"]
    database = os.environ.get("NEO4J_DATABASE", "neo4j")

    with Neo4jLoader(uri, username, password, database) as loader:
        cargar_grafo(loader)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
