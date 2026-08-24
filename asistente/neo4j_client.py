"""Cliente de lectura mínimo contra el grafo urbano real en Neo4j (tarea 081,
primera `tool` del asistente que cruza datasets vía el grafo cargado en la
tarea 080: 9327 nodos, 41031 relaciones, ver `doc/080-cargar-grafo-neo4j-real.md`).

Mismo patrón que `asistente/athena.py` frente a `grafo/extract.py`: no se
reutiliza `grafo/cypher.py` -- ese módulo solo tiene métodos de *escritura*
(`Neo4jLoader.load_*`, pensados para `cargar_grafo.py`), no una sola consulta
de lectura -- y `asistente/` se mantiene autocontenido, sin depender de
`grafo/` (mismo criterio ya documentado en `asistente/timeutils.py`).

Import perezoso del driver oficial `neo4j` (mismo motivo que
`grafo/cypher.py::Neo4jLoader`): `lugares_proximos_a_estaciones_trafico_query`
es Python puro y se puede testear por inspección de la cadena generada, sin
el paquete instalado ni conexión real (ver `asistente/tests/test_neo4j_client.py`,
mismo patrón que `grafo/tests/test_cypher.py`); solo `run_neo4j_query` (con
`driver=None`, el caso real) necesita `neo4j` instalado.

Credenciales leídas de `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`
(`NEO4J_DATABASE`, opcional, por defecto `"neo4j"`) -- este módulo no las
obtiene de SSM directamente, eso es responsabilidad de quien arranca el
proceso (mismo patrón que `grafo/cargar_grafo.py::main()`).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional


def lugares_proximos_a_estaciones_trafico_query(nombre_lugar: str, radio_m: float) -> "tuple[str, dict]":
    """Resuelve `nombre_lugar` contra `:Lugar` (coincidencia de texto, case
    insensitive vía `toLower`/`CONTAINS` -- mismo criterio pragmático que
    `calidad_aire` con `zona`, ver `asistente/mcp_agent/tools.py`) y sigue
    `PROXIMO_A` hasta las `EstacionMedida` de tráfico (`tipo = 'trafico'`)
    dentro de `radio_m`.

    Patrón **no dirigido** (`-[r:PROXIMO_A]-`, sin flecha): la relación se
    carga en un único sentido por pareja (ver
    `grafo/relaciones.py::proximo_a`, "la relación se genera en un único
    sentido por pareja... una consulta que necesite ambos sentidos usa un
    patrón no dirigido") -- como los nodos `:EstacionMedida` se cargan antes
    que los `:Lugar` en `grafo/cargar_grafo.py::cargar_grafo`, el sentido real
    siempre es `EstacionMedida -> Lugar`, pero esta consulta no depende de
    ese orden de carga (que es un detalle de implementación de
    `cargar_grafo.py`, no del esquema, ver `infra/neo4j/schema/schema.cypher`).

    `radio_m` se aplica como filtro explícito sobre `r.distancia_m`, no solo
    confiando en el umbral (300m) con el que se cargó la relación (tarea
    070) -- permite pedir un radio más estricto que ese umbral; un radio
    mayor no encontraría relaciones que nunca se cargaron.
    """
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "MATCH (l)-[r:PROXIMO_A]-(e:EstacionMedida {tipo: 'trafico'}) "
        "WHERE r.distancia_m <= $radio_m "
        "RETURN l.id AS lugar_id, l.nombre AS lugar_nombre, "
        "e.id AS estacion_id, r.distancia_m AS distancia_m "
        "ORDER BY distancia_m"
    )
    return query, {"nombre_lugar": nombre_lugar, "radio_m": radio_m}


@lru_cache
def _driver_from_env():
    from neo4j import GraphDatabase  # import perezoso, ver docstring del módulo

    uri = os.environ["NEO4J_URI"]
    username = os.environ["NEO4J_USERNAME"]
    password = os.environ["NEO4J_PASSWORD"]
    return GraphDatabase.driver(uri, auth=(username, password))


def run_neo4j_query(query: str, params: dict, *, driver=None, database: Optional[str] = None) -> "list[dict]":
    """Ejecuta `query` con `params` y devuelve las filas como `dict`.

    `driver` es inyectable (por defecto, un driver construido de
    `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`, cacheado por proceso con
    `lru_cache` -- abrir un driver por petición HTTP sería un coste
    innecesario, el driver oficial ya gestiona su propio pool de conexiones)
    para poder testear sin credenciales/conexión real -- ver
    `asistente/tests/test_mcp_tools.py`, mismo criterio que
    `asistente/athena.py::run_athena_query`.
    """
    driver = driver or _driver_from_env()
    database = database or os.environ.get("NEO4J_DATABASE", "neo4j")

    with driver.session(database=database) as session:
        result = session.run(query, params)
        return [dict(record) for record in result]
