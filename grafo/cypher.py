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

import logging
import re
import time
from typing import Iterable

logger = logging.getLogger(__name__)

# FIL_08: tamaño de lote para el `UNWIND`. Con los índices de `schema.cypher`
# aplicados (tarea 094) cada `MERGE` por `id` dentro del lote es barato; el
# objetivo es cambiar decenas de miles de idas y vueltas de red (que AuraDB
# Free cortaba, `SessionExpired`) por unas pocas.
_BATCH_SIZE = 1000
_MAX_REINTENTOS = 5
_BACKOFF_BASE_S = 2.0

_PARAM_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def _to_unwind(query: str) -> str:
    """Convierte una sentencia parametrizada con `$x` en su forma por lotes:
    `UNWIND $rows AS row <query con $x -> row.x>`. Seguro para las sentencias
    de este módulo -- todas usan `$nombre` solo como parámetro, nunca dentro
    de un literal de cadena."""
    return "UNWIND $rows AS row\n" + _PARAM_RE.sub(r"row.\1", query)

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
    """`osm_id`/`osm_amenity`/`osm_opening_hours` (tarea 083,
    `grafo.nodos.enrich_lugar_con_osm`) son opcionales -- `node.get(...)`
    devuelve `None` para cualquier `:Lugar` sin match de OSM, mismo criterio
    que `nombre`/`tipo`/`fuente` (un `SET` plano, sin preservar un valor
    anterior como sí hace `_UBICACION_SET`)."""
    query = (
        "MERGE (n:Lugar {id: $id}) "
        "SET n.nombre = $nombre, n.tipo = $tipo, n.fuente = $fuente, "
        "n.osm_id = $osm_id, n.osm_amenity = $osm_amenity, n.osm_opening_hours = $osm_opening_hours, "
        + _UBICACION_SET
    )
    return query, {
        "id": node["id"],
        "nombre": node.get("nombre"),
        "tipo": node.get("tipo"),
        "fuente": node.get("fuente"),
        "osm_id": node.get("osm_id"),
        "osm_amenity": node.get("osm_amenity"),
        "osm_opening_hours": node.get("osm_opening_hours"),
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


def ubicado_en_query(relacion: dict) -> "tuple[str, dict]":
    """`(n)-[:UBICADO_EN]->(b:Barrio)`. `n` se busca solo por `id`, sin
    restringir el label (`:Lugar`/`:EstacionMedida`/`:ParadaTransporte`): los
    prefijos `fuente` de cada label (ver `grafo/nodos.py`) no se solapan
    entre sí, así que `id` ya es único en la práctica en todo el grafo, no
    solo dentro de su propio label/constraint."""
    query = (
        "MATCH (n {id: $nodo_id}), (b:Barrio {codigo: $barrio_codigo}) "
        "MERGE (n)-[:UBICADO_EN]->(b)"
    )
    return query, {
        "nodo_id": relacion["nodo_id"],
        "barrio_codigo": relacion["barrio_codigo"],
    }


def _ubicacion_on_create(alias: str, prefix: str) -> str:
    """`SET` de `ubicacion` para un nodo recién `MERGE`-ado por `ON CREATE`:
    a diferencia de `_UBICACION_SET` (que conserva el valor existente si no
    llegan coordenadas nuevas, pensado para un nodo que ya podía tener
    `ubicacion`), aquí el nodo es nuevo -- no hay nada que conservar --, así
    que sin coordenadas el valor queda `NULL` directamente."""
    return (
        f"{alias}.ubicacion = CASE WHEN ${prefix}_lat IS NOT NULL AND ${prefix}_lon IS NOT NULL "
        f"THEN point({{latitude: ${prefix}_lat, longitude: ${prefix}_lon, crs: 'wgs-84'}}) ELSE NULL END"
    )


def conectado_con_query(relacion: dict) -> "tuple[str, dict]":
    """`(origen:ParadaTransporte)-[:CONECTADO_CON {modo, linea}]->(destino:
    ParadaTransporte)` -- adyacencia real de la red de transporte (tarea
    071, ver `grafo.relaciones.conectado_con`).

    Los extremos se `MERGE` (no `MATCH`) con `ON CREATE SET`: en el flujo
    normal (`cargar_grafo.py`) ya existen, cargados antes vía
    `nodos.paradas_transporte_from_crtm_bronze`, pero el enunciado de la
    tarea 071 pide explícitamente no descartar la relación si algún
    `stop_id` no tuviera nodo correspondiente -- `ON CREATE SET` solo rellena
    propiedades en el nodo nuevo, sin tocar un nodo que ya existiera con
    datos más completos.

    `linea` forma parte del propio patrón `MERGE` de la relación, no solo de
    un `SET` posterior: dos paradas consecutivas pueden estar conectadas por
    más de una línea (p. ej. dos autobuses que comparten un tramo), y cada
    una debe quedar como una relación `CONECTADO_CON` distinta -- si `linea`
    no formara parte del patrón de `MERGE`, cargar una segunda línea sobre
    el mismo par de paradas sobrescribiría la primera en vez de añadir una
    relación nueva.
    """
    query = (
        "MERGE (a:ParadaTransporte {id: $origen_id}) "
        "ON CREATE SET a.tipo = $modo, a.fuente = 'crtm_red_transporte_madrid', "
        + _ubicacion_on_create("a", "origen")
        + " "
        "MERGE (b:ParadaTransporte {id: $destino_id}) "
        "ON CREATE SET b.tipo = $modo, b.fuente = 'crtm_red_transporte_madrid', "
        + _ubicacion_on_create("b", "destino")
        + " "
        "MERGE (a)-[r:CONECTADO_CON {linea: $linea}]->(b) "
        "SET r.modo = $modo"
    )
    origen_ubicacion = relacion["origen"].get("ubicacion") or {}
    destino_ubicacion = relacion["destino"].get("ubicacion") or {}
    return query, {
        "origen_id": relacion["origen"]["id"],
        "destino_id": relacion["destino"]["id"],
        "modo": relacion["modo"],
        "linea": relacion["linea"],
        "origen_lat": origen_ubicacion.get("lat"),
        "origen_lon": origen_ubicacion.get("lon"),
        "destino_lat": destino_ubicacion.get("lat"),
        "destino_lon": destino_ubicacion.get("lon"),
    }


def proximo_a_query(relacion: dict) -> "tuple[str, dict]":
    """`(a)-[:PROXIMO_A {distancia_m}]->(b)`, un único sentido por pareja
    (ver `grafo.relaciones.proximo_a`). `SET` (no solo en el `MERGE`) para
    que recargar la misma pareja actualice `distancia_m` si cambiara (p. ej.
    si se corrige la ubicación de alguno de los dos nodos en una carga
    posterior)."""
    query = (
        "MATCH (a {id: $origen_id}), (b {id: $destino_id}) "
        "MERGE (a)-[r:PROXIMO_A]->(b) "
        "SET r.distancia_m = $distancia_m"
    )
    return query, {
        "origen_id": relacion["origen_id"],
        "destino_id": relacion["destino_id"],
        "distancia_m": relacion["distancia_m"],
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
        self._uri = uri
        self._auth = (username, password)

    def close(self) -> None:
        self._driver.close()

    def _reconectar(self) -> None:
        """Recrea el driver -- lo llama `_ejecutar_lote` tras un corte de
        conexión de AuraDB Free (`SessionExpired`/`ServiceUnavailable`)."""
        from neo4j import GraphDatabase

        try:
            self._driver.close()
        except Exception:  # noqa: BLE001 -- el driver ya está roto, da igual
            pass
        self._driver = GraphDatabase.driver(self._uri, auth=self._auth)

    def __enter__(self) -> "Neo4jLoader":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _ejecutar_lote(self, unwind_query: str, filas: "list[dict]") -> None:
        """Ejecuta un `UNWIND` sobre `filas` con reintento y reconexión ante
        cortes transitorios de la conexión (FIL_08). Los errores de sintaxis
        Cypher u otros no transitorios se propagan tal cual."""
        from neo4j.exceptions import (  # import perezoso, ver docstring del módulo
            ServiceUnavailable,
            SessionExpired,
            TransientError,
        )

        transitorios = (SessionExpired, ServiceUnavailable, TransientError)
        for intento in range(1, _MAX_REINTENTOS + 1):
            try:
                with self._driver.session(database=self._database) as session:
                    session.execute_write(lambda tx: tx.run(unwind_query, rows=filas).consume())
                return
            except transitorios as exc:  # noqa: PERF203
                if intento == _MAX_REINTENTOS:
                    raise
                espera = _BACKOFF_BASE_S * intento
                logger.warning(
                    "Lote de %d filas falló (%s), intento %d/%d; reconectando en %.0fs",
                    len(filas),
                    type(exc).__name__,
                    intento,
                    _MAX_REINTENTOS,
                    espera,
                )
                time.sleep(espera)
                self._reconectar()

    def _run_all(self, queries: "Iterable[tuple[str, dict]]") -> None:
        """Agrupa las sentencias por texto (dentro de cada `load_*` son
        idénticas) y las ejecuta en lotes `UNWIND` en vez de una por una
        (FIL_08: AuraDB Free cortaba la conexión con decenas de miles de
        `session.run` seguidos)."""
        por_query: "dict[str, list[dict]]" = {}
        orden: "list[str]" = []
        for query, params in queries:
            if query not in por_query:
                por_query[query] = []
                orden.append(query)
            por_query[query].append(params)

        for query in orden:
            filas = por_query[query]
            unwind_query = _to_unwind(query)
            for inicio in range(0, len(filas), _BATCH_SIZE):
                self._ejecutar_lote(unwind_query, filas[inicio : inicio + _BATCH_SIZE])

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

    def load_ubicado_en(self, relaciones: "Iterable[dict]") -> None:
        self._run_all(ubicado_en_query(r) for r in relaciones)

    def load_proximo_a(self, relaciones: "Iterable[dict]") -> None:
        self._run_all(proximo_a_query(r) for r in relaciones)

    def load_conectado_con(self, relaciones: "Iterable[dict]") -> None:
        self._run_all(conectado_con_query(r) for r in relaciones)
