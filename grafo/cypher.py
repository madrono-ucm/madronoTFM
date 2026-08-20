"""Traduce los `dict` de `grafo.nodos`/`grafo.relaciones` a sentencias Cypher
`MERGE` parametrizadas, y las ejecuta contra una instancia Neo4j real.

Este módulo **sí** puede depender del driver oficial `neo4j` (ver
`grafo/requirements.txt`) -- a diferencia de `nodos.py`/`relaciones.py`, es
la capa adaptadora, mismo rol que `glue_bronze_to_silver.py` frente a
`transform.py` en `procesamiento/silver_gold/` (ese sí importa `pyspark`,
`transform.py` no).

Pero **no importa `neo4j` a nivel de módulo**: las funciones `*_query()` de
más abajo, que construyen las sentencias (usadas por
`grafo/tests/test_cypher.py` para verificar el Cypher generado "por
inspección... sin conexión real", como pide la tarea 067), son Python puro y
no necesitan el driver instalado. Solo `Neo4jLoader` -- la clase que abre una
conexión real y ejecuta las sentencias -- importa `neo4j`, y lo hace de forma
perezosa dentro de `__init__`: crear un `Neo4jLoader` sin el paquete
instalado falla con un `ImportError` claro en ese punto, pero importar este
módulo o usar las funciones `*_query()` no requiere tenerlo instalado en
absoluto. Así los tests de este fichero corren en esta EC2 (disco limitado,
sin `neo4j` instalado) igual que los de `nodos.py`/`relaciones.py`.

`MERGE` (no `CREATE`) sobre la clave `UNIQUE` de cada label (ver
`infra/neo4j/schema/schema.cypher`: `codigo` para Distrito/Barrio, `id` para
Lugar/EstacionMedida/ParadaTransporte) para que cargar el mismo nodo dos
veces no lo duplique -- idempotente, igual que el propio `schema.cypher`.
"""

from __future__ import annotations

from typing import Iterable

# ---------------------------------------------------------------------------
# Construcción de sentencias (Python puro, sin `neo4j`).
# ---------------------------------------------------------------------------

_UBICACION_SET = (
    "n.ubicacion = CASE WHEN $lat IS NOT NULL AND $lon IS NOT NULL "
    "THEN point({latitude: $lat, longitude: $lon, crs: 'wgs-84'}) "
    "ELSE n.ubicacion END"
)


def distrito_query(node: dict) -> "tuple[str, dict]":
    query = "MERGE (n:Distrito {codigo: $codigo}) SET n.nombre = $nombre"
    return query, {"codigo": node["codigo"], "nombre": node.get("nombre")}


def barrio_query(node: dict) -> "tuple[str, dict]":
    query = (
        "MERGE (n:Barrio {codigo: $codigo}) "
        "SET n.nombre = $nombre, n.distrito_codigo = $distrito_codigo"
    )
    return query, {
        "codigo": node["codigo"],
        "nombre": node.get("nombre"),
        "distrito_codigo": node.get("distrito_codigo"),
    }


def _ubicacion_params(node: dict) -> dict:
    ubicacion = node.get("ubicacion") or {}
    return {"lat": ubicacion.get("lat"), "lon": ubicacion.get("lon")}


def estacion_medida_query(node: dict) -> "tuple[str, dict]":
    query = (
        "MERGE (n:EstacionMedida {id: $id}) "
        "SET n.tipo = $tipo, n.fuente = $fuente, " + _UBICACION_SET
    )
    return query, {
        "id": node["id"],
        "tipo": node.get("tipo"),
        "fuente": node.get("fuente"),
        **_ubicacion_params(node),
    }


def parada_transporte_query(node: dict) -> "tuple[str, dict]":
    query = (
        "MERGE (n:ParadaTransporte {id: $id}) "
        "SET n.tipo = $tipo, n.fuente = $fuente, " + _UBICACION_SET
    )
    return query, {
        "id": node["id"],
        "tipo": node.get("tipo"),
        "fuente": node.get("fuente"),
        **_ubicacion_params(node),
    }


def lugar_query(node: dict) -> "tuple[str, dict]":
    query = (
        "MERGE (n:Lugar {id: $id}) "
        "SET n.nombre = $nombre, n.tipo = $tipo, n.fuente = $fuente, " + _UBICACION_SET
    )
    return query, {
        "id": node["id"],
        "nombre": node.get("nombre"),
        "tipo": node.get("tipo"),
        "fuente": node.get("fuente"),
        **_ubicacion_params(node),
    }


def pertenece_a_query(relacion: dict) -> "tuple[str, dict]":
    query = (
        "MATCH (b:Barrio {codigo: $barrio_codigo}), (d:Distrito {codigo: $distrito_codigo}) "
        "MERGE (b)-[:PERTENECE_A]->(d)"
    )
    return query, {
        "barrio_codigo": relacion["barrio_codigo"],
        "distrito_codigo": relacion["distrito_codigo"],
    }


# ---------------------------------------------------------------------------
# Ejecución real (import perezoso de `neo4j`).
# ---------------------------------------------------------------------------


class Neo4jLoader:
    """Abre una sesión Bolt y ejecuta las sentencias `*_query()` anteriores.

    Uso previsto (una vez exista una instancia real, ver
    `infra/neo4j/README.md`, "Alta de AuraDB Free"):

        from grafo.cypher import Neo4jLoader
        from grafo import nodos

        with Neo4jLoader(uri, username, password, database) as loader:
            loader.load_distritos(nodos.distritos_from_bronze(distrito_records))
            loader.load_barrios(nodos.barrios_from_bronze(barrio_records))
            ...

    No se ha ejecutado nunca contra una instancia real en esta tarea (sigue
    bloqueado el alta manual de AuraDB Free, tarea 043).
    """

    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        from neo4j import GraphDatabase  # import perezoso, ver docstring del módulo

        self._driver = GraphDatabase.driver(uri, auth=(username, password))
        self._database = database

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jLoader":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _run_all(self, queries: "Iterable[tuple[str, dict]]") -> None:
        with self._driver.session(database=self._database) as session:
            for query, params in queries:
                session.run(query, params)

    def load_distritos(self, nodes: "Iterable[dict]") -> None:
        self._run_all(distrito_query(n) for n in nodes)

    def load_barrios(self, nodes: "Iterable[dict]") -> None:
        self._run_all(barrio_query(n) for n in nodes)

    def load_estaciones_medida(self, nodes: "Iterable[dict]") -> None:
        self._run_all(estacion_medida_query(n) for n in nodes)

    def load_paradas_transporte(self, nodes: "Iterable[dict]") -> None:
        self._run_all(parada_transporte_query(n) for n in nodes)

    def load_lugares(self, nodes: "Iterable[dict]") -> None:
        self._run_all(lugar_query(n) for n in nodes)

    def load_pertenece_a(self, relaciones: "Iterable[dict]") -> None:
        self._run_all(pertenece_a_query(r) for r in relaciones)
