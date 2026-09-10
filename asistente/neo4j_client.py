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
(`NEO4J_DATABASE`, opcional; sin definir usa la home database del DBMS --
en AuraDB la base real no se llama `"neo4j"`, FIL_67) -- este módulo no las
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


def estaciones_calidad_aire_que_miden_query(
    nombre_lugar: str, contaminante: str, radio_m: float
) -> "tuple[str, dict]":
    """Como `lugares_proximos_a_estaciones_calidad_aire_query` pero filtra a
    las estaciones que **de hecho miden** `contaminante` (FIL_66 cargó la
    lista `e.contaminantes` en cada nodo; cada estación mide un subconjunto
    distinto -- p. ej. muchas no tienen O₃). Sin este filtro, la estación
    más cercana puede no servir para el contaminante pedido.

    `contaminante` se compara en mayúsculas contra los códigos de Gold
    (`"NO2"`, `"O3"`, `"PM10"`, `"PM2.5"`, ...). Si `e.contaminantes` no
    existe en el nodo (grafo cargado antes de FIL_66), la condición
    `contaminante IN e.contaminantes` es falsa y la estación se descarta --
    recargar el grafo para que vuelva a estar disponible."""
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "MATCH (l)-[r:PROXIMO_A]-(e:EstacionMedida {tipo: 'calidad_aire'}) "
        "WHERE r.distancia_m <= $radio_m AND toUpper($contaminante) IN e.contaminantes "
        "RETURN l.id AS lugar_id, l.nombre AS lugar_nombre, "
        "e.id AS estacion_id, e.contaminantes AS contaminantes, r.distancia_m AS distancia_m "
        "ORDER BY distancia_m"
    )
    return query, {"nombre_lugar": nombre_lugar, "contaminante": contaminante, "radio_m": radio_m}


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


def lugares_proximos_a_paradas_emt_query(nombre_lugar: str, radio_m: float) -> "tuple[str, dict]":
    """Igual que `lugares_proximos_a_paradas_bicimad_query` pero contra
    `ParadaTransporte {tipo: 'emt'}` (tarea 096, señal de transporte público
    de `opciones_movilidad`). El `id` de estos nodos es
    `transporte_publico_emt:<stop_id>` (ver `grafo/nodos.py::parada_
    transporte_from_transporte_publico_emt_gold`) -- mismo criterio de
    extraer el identificador real tras los dos puntos que usa
    `_trafico_cercano_impl` con `estacion_id`."""
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "MATCH (l)-[r:PROXIMO_A]-(e:ParadaTransporte {tipo: 'emt'}) "
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
    (tarea 095) no cruza contra ningún nodo del grafo: no existe ningún
    `:Evento` cargado todavía (`agenda_eventos`/`agenda_recintos` no forman
    parte del grafo, ver `grafo/README.md`), y Gold de `agenda_eventos`
    agrega por categoría/distrito/fecha (sin lat/lon por evento individual,
    ver `doc/095-...md`) -- la única fuente con posición real por evento es
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


# ---------------------------------------------------------------------------
# Librería de consultas parametrizadas (FIL_67 Parte 2B). Mismo patrón que
# los `lugares_proximos_a_*` de arriba: Python puro, testables por
# inspección de la cadena; el `MATCH` de lugar usa `CONTAINS` case-insensitive
# y el patrón `PROXIMO_A` es no dirigido. Explotan los nodos y atributos que
# cargaron FIL_65 (meteo, recintos) y FIL_66 (contaminantes, capacidades,
# subárea) y no tenían constructor.
# ---------------------------------------------------------------------------


def vecindario_de_lugar_query(nombre_lugar: str, radio_m: float) -> "tuple[str, dict]":
    """Todo lo que hay a `radio_m` de `nombre_lugar` por `PROXIMO_A`, en una
    sola consulta: estaciones de medida (con su lista de contaminantes /
    magnitudes / subárea), paradas de transporte y otros `:Lugar` (parques,
    aparcamientos con capacidad, recintos, POIs). `categoria` = label del
    nodo vecino; `subtipo` = su propiedad `tipo`."""
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "MATCH (l)-[r:PROXIMO_A]-(v) "
        "WHERE r.distancia_m <= $radio_m "
        "RETURN labels(v)[0] AS categoria, v.tipo AS subtipo, v.id AS id, "
        "v.nombre AS nombre, r.distancia_m AS distancia_m, "
        "v.contaminantes AS contaminantes, v.magnitudes AS magnitudes, "
        "v.altitud_m AS altitud_m, v.subarea AS subarea, "
        "v.anclajes_totales AS anclajes_totales, v.plazas_totales AS plazas_totales "
        "ORDER BY distancia_m"
    )
    return query, {"nombre_lugar": nombre_lugar, "radio_m": radio_m}


def estaciones_meteo_cerca_query(nombre_lugar: str, radio_m: float) -> "tuple[str, dict]":
    """Estaciones meteo (`:EstacionMedida {tipo:'meteo'}`, FIL_65) a `radio_m`
    de `nombre_lugar`, con las magnitudes que miden y su altitud (FIL_66)."""
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "MATCH (l)-[r:PROXIMO_A]-(e:EstacionMedida {tipo: 'meteo'}) "
        "WHERE r.distancia_m <= $radio_m "
        "RETURN e.id AS estacion_id, e.nombre AS estacion_nombre, "
        "e.magnitudes AS magnitudes, e.altitud_m AS altitud_m, r.distancia_m AS distancia_m "
        "ORDER BY distancia_m"
    )
    return query, {"nombre_lugar": nombre_lugar, "radio_m": radio_m}


def recintos_cerca_query(nombre_lugar: str, radio_m: float) -> "tuple[str, dict]":
    """Recintos de eventos (`:Lugar {tipo:'recinto'}`, FIL_65) a `radio_m` de
    `nombre_lugar` por `PROXIMO_A`."""
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "MATCH (l)-[r:PROXIMO_A]-(v:Lugar {tipo: 'recinto'}) "
        "WHERE r.distancia_m <= $radio_m "
        "RETURN v.id AS recinto_id, v.nombre AS recinto_nombre, r.distancia_m AS distancia_m "
        "ORDER BY distancia_m"
    )
    return query, {"nombre_lugar": nombre_lugar, "radio_m": radio_m}


def aparcamientos_cerca_query(nombre_lugar: str, radio_m: float) -> "tuple[str, dict]":
    """Aparcamientos a `radio_m` de `nombre_lugar` con su capacidad
    (`plazas_totales`, FIL_66)."""
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "MATCH (l)-[r:PROXIMO_A]-(v:Lugar {tipo: 'aparcamiento'}) "
        "WHERE r.distancia_m <= $radio_m "
        "RETURN v.id AS aparcamiento_id, v.nombre AS nombre, "
        "v.plazas_totales AS plazas_totales, r.distancia_m AS distancia_m "
        "ORDER BY distancia_m"
    )
    return query, {"nombre_lugar": nombre_lugar, "radio_m": radio_m}


def bicimad_cerca_query(nombre_lugar: str, radio_m: float) -> "tuple[str, dict]":
    """Estaciones BiciMAD a `radio_m` de `nombre_lugar` con su capacidad
    (`anclajes_totales`, FIL_66)."""
    query = (
        "MATCH (l:Lugar) "
        "WHERE toLower(l.nombre) CONTAINS toLower($nombre_lugar) "
        "MATCH (l)-[r:PROXIMO_A]-(v:ParadaTransporte {tipo: 'bicimad'}) "
        "WHERE r.distancia_m <= $radio_m "
        "RETURN v.id AS estacion_id, v.nombre AS nombre, "
        "v.anclajes_totales AS anclajes_totales, r.distancia_m AS distancia_m "
        "ORDER BY distancia_m"
    )
    return query, {"nombre_lugar": nombre_lugar, "radio_m": radio_m}


def lineas_que_pasan_por_query(estacion_id: str) -> "tuple[str, dict]":
    """Líneas de transporte que sirven una parada, desde las aristas
    `CONECTADO_CON` (su propiedad `linea`/`modo`). `estacion_id` es el `id`
    completo del nodo (`"crtm_red_transporte_madrid:<stop_id>"`)."""
    query = (
        "MATCH (p:ParadaTransporte {id: $estacion_id})-[r:CONECTADO_CON]-() "
        "RETURN DISTINCT r.modo AS modo, r.linea AS linea "
        "ORDER BY modo, linea"
    )
    return query, {"estacion_id": estacion_id}


def paradas_de_linea_query(linea: str, modo: str) -> "tuple[str, dict]":
    """Todas las paradas de una línea (`modo` + `linea` de `CONECTADO_CON`),
    ordenadas por nombre. `modo` distingue líneas homónimas de redes
    distintas (p. ej. metro "1" vs. bus "1")."""
    query = (
        "MATCH (a:ParadaTransporte)-[r:CONECTADO_CON {linea: $linea}]-(b:ParadaTransporte) "
        "WHERE r.modo = $modo "
        "WITH collect(DISTINCT a) + collect(DISTINCT b) AS ps "
        "UNWIND ps AS p "
        "RETURN DISTINCT p.id AS parada_id, p.nombre AS nombre, "
        "p.ubicacion.latitude AS lat, p.ubicacion.longitude AS lon "
        "ORDER BY nombre"
    )
    return query, {"linea": linea, "modo": modo}


# ---------------------------------------------------------------------------
# Explorador del grafo en vivo (FIL_67 Parte 3): tres consultas de solo
# lectura que alimentan `viz/grafo_explorador.html` desde Neo4j en directo
# en vez de un snapshot estático.
# ---------------------------------------------------------------------------


def grafo_explorador_nodos_query() -> "tuple[str, dict]":
    """Todos los nodos geolocalizados (`:EstacionMedida` / `:ParadaTransporte`
    / `:Lugar`) con sus atributos estáticos (FIL_66) y su barrio/distrito
    reales (`UBICADO_EN`→`PERTENECE_A`)."""
    query = (
        "MATCH (n) "
        "WHERE (n:EstacionMedida OR n:ParadaTransporte OR n:Lugar) AND n.ubicacion IS NOT NULL "
        "OPTIONAL MATCH (n)-[:UBICADO_EN]->(b:Barrio)-[:PERTENECE_A]->(d:Distrito) "
        "RETURN labels(n)[0] AS label, n.id AS id, n.tipo AS tipo, n.nombre AS nombre, "
        "n.ubicacion.latitude AS lat, n.ubicacion.longitude AS lon, "
        "b.nombre AS barrio, d.nombre AS distrito, "
        "n.contaminantes AS contaminantes, n.magnitudes AS magnitudes, "
        "n.altitud_m AS altitud_m, n.subarea AS subarea, "
        "n.anclajes_totales AS anclajes_totales, n.plazas_totales AS plazas_totales"
    )
    return query, {}


def grafo_explorador_conectado_con_query() -> "tuple[str, dict]":
    """Aristas `CONECTADO_CON` (esqueleto de transporte) como pares de `id` +
    `modo`/`linea`. Dirigidas; el consumidor las pliega a no dirigidas."""
    query = (
        "MATCH (a:ParadaTransporte)-[r:CONECTADO_CON]->(b:ParadaTransporte) "
        "RETURN a.id AS a, b.id AS b, r.modo AS modo, r.linea AS linea"
    )
    return query, {}


def vecindario_grafo_query(nodo_id: str, radio_m: float) -> "tuple[str, dict]":
    """Vecinos `PROXIMO_A` de un nodo (por `id`) dentro de `radio_m`, con sus
    atributos — lo que el explorador pide al hacer clic en un nodo."""
    query = (
        "MATCH (n {id: $nodo_id})-[r:PROXIMO_A]-(v) "
        "WHERE r.distancia_m <= $radio_m "
        "RETURN labels(v)[0] AS label, v.id AS id, v.tipo AS tipo, v.nombre AS nombre, "
        "v.ubicacion.latitude AS lat, v.ubicacion.longitude AS lon, "
        "v.contaminantes AS contaminantes, v.magnitudes AS magnitudes, "
        "v.altitud_m AS altitud_m, v.subarea AS subarea, "
        "v.anclajes_totales AS anclajes_totales, v.plazas_totales AS plazas_totales, "
        "r.distancia_m AS distancia_m "
        "ORDER BY distancia_m"
    )
    return query, {"nodo_id": nodo_id, "radio_m": radio_m}


_RUTA_NODOS = (
    "[n IN nodes(p) | {id:n.id, tipo:n.tipo, nombre:n.nombre, "
    "lat:n.ubicacion.latitude, lon:n.ubicacion.longitude}]"
)


def ruta_proximo_query(a_id: str, b_id: str) -> "tuple[str, dict]":
    """Camino mínimo ponderado entre dos nodos por `PROXIMO_A` (peso
    `distancia_m`) con `apoc.algo.dijkstra` — la "capacidad de enrutado del
    grafo DB" servida directa desde Neo4j (verificado en vivo, FIL_67)."""
    query = (
        "MATCH (a {id:$a_id}), (b {id:$b_id}) "
        "CALL apoc.algo.dijkstra(a, b, 'PROXIMO_A', 'distancia_m') YIELD path AS p, weight "
        f"RETURN weight AS metros, length(p) AS saltos, {_RUTA_NODOS} AS nodos"
    )
    return query, {"a_id": a_id, "b_id": b_id}


def ruta_transporte_query(a_id: str, b_id: str) -> "tuple[str, dict]":
    """Camino con menos saltos entre dos paradas por `CONECTADO_CON`
    (`shortestPath`), con el modo/línea de cada tramo."""
    query = (
        "MATCH (a:ParadaTransporte {id:$a_id}), (b:ParadaTransporte {id:$b_id}) "
        "MATCH p = shortestPath((a)-[:CONECTADO_CON*..40]-(b)) "
        f"RETURN length(p) AS saltos, {_RUTA_NODOS} AS nodos, "
        "[r IN relationships(p) | {modo:r.modo, linea:r.linea}] AS tramos"
    )
    return query, {"a_id": a_id, "b_id": b_id}


def cobertura_aire_query() -> "tuple[str, dict]":
    """Por cada `:EstacionMedida {tipo:'trafico'}`, si tiene o no una estación
    de calidad del aire a <=300 m por `PROXIMO_A` — hallazgo del TFM: solo 23
    estaciones de aire para toda la ciudad (`FIL_66` / §7)."""
    query = (
        "MATCH (t:EstacionMedida {tipo:'trafico'}) "
        "RETURN t.id AS id, "
        "EXISTS { (t)-[:PROXIMO_A]-(:EstacionMedida {tipo:'calidad_aire'}) } AS con_aire"
    )
    return query, {}


def sensores_por_distrito_query() -> "tuple[str, dict]":
    """Nº de `:EstacionMedida` por distrito (vía `UBICADO_EN`→`PERTENECE_A`) —
    el sesgo de cobertura por distrito que la memoria declara en §7."""
    query = (
        "MATCH (d:Distrito)<-[:PERTENECE_A]-(:Barrio)<-[:UBICADO_EN]-(e:EstacionMedida) "
        "RETURN d.nombre AS distrito, count(e) AS n, "
        "count(CASE e.tipo WHEN 'trafico' THEN 1 END) AS trafico, "
        "count(CASE e.tipo WHEN 'calidad_aire' THEN 1 END) AS aire "
        "ORDER BY n DESC"
    )
    return query, {}


@lru_cache
def _driver_from_env():
    from neo4j import GraphDatabase  # import perezoso, ver docstring del módulo

    uri = os.environ["NEO4J_URI"]
    username = os.environ["NEO4J_USERNAME"]
    password = os.environ["NEO4J_PASSWORD"]
    return GraphDatabase.driver(uri, auth=(username, password))


from asistente.cache import cacheado  # noqa: E402 - se importa aquí para evitar ciclo


@cacheado(ttl_s=900)
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
    # `NEO4J_DATABASE` sin definir -> `None`, no el literal "neo4j": en AuraDB
    # la base real NO se llama "neo4j" (es el subdominio de la instancia, p. ej.
    # "5c111cec"), y `session(database="neo4j")` falla con `DatabaseNotFound`.
    # Con `database=None` el driver usa la *home database* del DBMS, que en
    # Aura es siempre la correcta (FIL_67).
    database = database or os.environ.get("NEO4J_DATABASE") or None

    with driver.session(database=database) as session:
        result = session.run(query, params)
        return [dict(record) for record in result]
