"""Entry point que encadena `extract.py` (Athena/S3 real, tarea 069) ->
`nodos.py`/`relaciones.py` (transformación, tareas 067/070) -> `cypher.py`
(carga real, tareas 067/070) para los 5 labels y las relaciones
`PERTENECE_A`, `UBICADO_EN` y `PROXIMO_A` que cubre este directorio.

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
    `PROXIMO_A`) contra `loader`, leyendo los datos reales con
    `grafo.extract` en el momento de la llamada."""
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

    paradas_transporte = (
        nodos.paradas_transporte_from_transporte_publico_emt_gold(extract.fetch_paradas_emt())
        + nodos.paradas_transporte_from_bicimad_gold(extract.fetch_paradas_bicimad())
        + nodos.paradas_transporte_from_crtm_bronze(extract.fetch_paradas_crtm_bronze())
    )
    loader.load_paradas_transporte(paradas_transporte)

    lugares = (
        nodos.lugares_from_poi_bronze(extract.fetch_poi_bronze())
        + nodos.lugares_from_aparcamientos_gold(extract.fetch_lugares_aparcamientos())
        + nodos.lugares_from_cartelera_cines_gold(extract.fetch_lugares_cartelera_cines())
    )
    loader.load_lugares(lugares)

    loader.load_pertenece_a(relaciones.pertenece_a_from_barrios(barrio_nodes))

    # UBICADO_EN/PROXIMO_A: cualquier nodo con ubicación, de los 3 labels
    # que pueden tenerla (ver `schema.cypher`) -- Distrito/Barrio quedan
    # fuera (no tienen `ubicacion`, solo la geometría cruda de Bronze).
    nodos_con_ubicacion = estaciones_medida + paradas_transporte + lugares
    loader.load_ubicado_en(relaciones.ubicado_en(nodos_con_ubicacion, barrio_records))
    loader.load_proximo_a(relaciones.proximo_a(nodos_con_ubicacion))


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
