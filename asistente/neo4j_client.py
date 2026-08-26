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


def lugares_proximos_a_estaciones_ruido_query(nombre_lugar: str, radio_m: float) -> "tuple[str, dict]":
    """Igual que `lugares_proximos_a_estaciones_trafico_query` pero contra
    `EstacionMedida {tipo: 'ruido'}` (tarea 089, señal secundaria de
    `afluencia_estimada`) -- ver el docstring de esa función para el
    criterio de resolución/radio, idéntico aquí."""
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "MATCH (l)-[r:PROXIMO_A]-(e:EstacionMedida {tipo: 'ruido'}) "
        "WHERE r.distancia_m <= $radio_m "
        "RETURN l.id AS lugar_id, l.nombre AS lugar_nombre, "
        "e.id AS estacion_id, r.distancia_m AS distancia_m "
        "ORDER BY distancia_m"
    )
    return query, {"nombre_lugar": nombre_lugar, "radio_m": radio_m}


def lugares_proximos_a_estaciones_calidad_aire_query(nombre_lugar: str, radio_m: float) -> "tuple[str, dict]":
    """Igual que `lugares_proximos_a_estaciones_trafico_query` pero contra
    `EstacionMedida {tipo: 'calidad_aire'}` (tarea 089, señal más débil/
    indirecta de `afluencia_estimada` -- ver el docstring de
    `asistente.mcp_agent.tools.afluencia_estimada`)."""
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "MATCH (l)-[r:PROXIMO_A]-(e:EstacionMedida {tipo: 'calidad_aire'}) "
        "WHERE r.distancia_m <= $radio_m "
        "RETURN l.id AS lugar_id, l.nombre AS lugar_nombre, "
        "e.id AS estacion_id, r.distancia_m AS distancia_m "
        "ORDER BY distancia_m"
    )
    return query, {"nombre_lugar": nombre_lugar, "radio_m": radio_m}


def lugares_proximos_a_paradas_bicimad_query(nombre_lugar: str, radio_m: float) -> "tuple[str, dict]":
    """Igual que `lugares_proximos_a_estaciones_trafico_query` pero contra
    `ParadaTransporte {tipo: 'bicimad'}` (tarea 089, señal de movilidad
    activa de `afluencia_estimada`). `ParadaTransporte` puede tener
    `PROXIMO_A` igual que `EstacionMedida` -- ambos son de los 3 labels con
    `ubicacion` (ver `grafo/relaciones.py::proximo_a`)."""
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "MATCH (l)-[r:PROXIMO_A]-(e:ParadaTransporte {tipo: 'bicimad'}) "
        "WHERE r.distancia_m <= $radio_m "
        "RETURN l.id AS lugar_id, l.nombre AS lugar_nombre, "
        "e.id AS estacion_id, r.distancia_m AS distancia_m "
        "ORDER BY distancia_m"
    )
    return query, {"nombre_lugar": nombre_lugar, "radio_m": radio_m}


def resolver_lugar_query(nombre_lugar: str) -> "tuple[str, dict]":
    """Resuelve `nombre_lugar` contra `:Lugar` (mismo criterio de
    coincidencia de texto que el resto de query builders de este módulo),
    devolviendo solo sus coordenadas -- sin seguir ninguna relación
    `PROXIMO_A`.

    A diferencia de `lugares_proximos_a_*` (tarea 081/089), `eventos_cercanos`
    (tarea 093) no cruza contra ningún nodo del grafo: no existe ningún
    `:Evento` cargado todavía (`agenda_eventos`/`agenda_recintos` no forman
    parte del grafo, ver `grafo/README.md`), y Gold de `agenda_eventos`
    agrega por categoría/distrito/fecha (sin lat/lon por evento individual,
    ver `doc/093-...md`) -- la única fuente con posición real por evento es
    **Silver** (`ingesta.capturas.agenda_eventos_madrid`, lat/lon ya
    normalizados). Esta consulta solo resuelve el punto de referencia; el
    filtro de distancia contra los eventos de Silver se hace en Python
    (`asistente/mcp_agent/tools.py::_haversine_m`), no en Cypher.

    `l.ubicacion` es un `Point` WGS84 (`infra/neo4j/schema/schema.cypher`) --
    se extraen `.latitude`/`.longitude` explícitamente porque el driver
    `neo4j` devuelve un objeto `Point`, no dos escalares, y el resto de este
    módulo (y `asistente/mcp_agent/tools.py`) trabaja con `lat`/`lon` planos.
    """
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "RETURN l.id AS lugar_id, l.nombre AS lugar_nombre, "
        "l.ubicacion.latitude AS lat, l.ubicacion.longitude AS lon"
    )
    return query, {"nombre_lugar": nombre_lugar}


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
