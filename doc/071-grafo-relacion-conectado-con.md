# 071 — Grafo: relación `CONECTADO_CON` (adyacencia real de la red de transporte)

## Objetivo

Última relación pendiente del esquema del grafo Neo4j (`infra/neo4j/schema/
schema.cypher`, tarea 043): `CONECTADO_CON`, la adyacencia real de la red de
transporte (`modo`/`linea` como propiedades de la relación), a partir de las
rutas de `crtm_red_transporte_madrid` (Bronze) — cada registro trae, por
`route_id`, una lista `stops` ya ordenada por `sequence`; dos paradas
consecutivas en esa lista quedan conectadas directamente por esa línea. Sin
conectar a ninguna instancia Neo4j real (sigue bloqueada el alta manual de
AuraDB Free, tarea 043).

## Qué se ha añadido

- **`grafo/relaciones.py`**: `conectado_con(rutas_crtm)` — para cada ruta,
  ordena `stops` por `sequence` y genera, por cada par consecutivo, una
  relación `{origen, destino, modo, linea}` en ambos sentidos. `origen`/
  `destino` llevan la forma mínima de un `:ParadaTransporte` (`id`/`tipo`/
  `ubicacion`), construida con el helper `_parada_minima`.
- **`grafo/cypher.py`**: `conectado_con_query()` (Python puro, mismo patrón
  que las funciones `*_query()` existentes) y
  `Neo4jLoader.load_conectado_con`.
- **`grafo/cargar_grafo.py`**: `cargar_grafo()` lee ahora las rutas CRTM una
  única vez y las reutiliza tanto para
  `nodos.paradas_transporte_from_crtm_bronze` (nodos) como para
  `relaciones.conectado_con` (relación), en ese orden.
- **Tests**: `grafo/tests/test_relaciones.py::ConectadoConTests` (7 tests
  nuevos, usando directamente el fixture real
  `crtm_red_transporte_madrid_sample.json`) y
  `grafo/tests/test_cypher.py::ConectadoConQueryTests` (3 tests nuevos) — 80
  tests en total en `grafo/tests/`, todos en verde, verificados **sin** el
  driver `neo4j` instalado (`python3 -c "import neo4j"` sigue fallando con
  `ModuleNotFoundError`).
- `grafo/README.md`: sección nueva `CONECTADO_CON (tarea 071)`, actualizada
  la tabla de estructura, "Cómo se cargaría", el recuento de tests y
  "Relevante para tareas futuras" (la entrada de la tarea 070 que dejaba
  esto abierto se sustituye por una marcada como resuelta).

## Decisiones de diseño relevantes

- **Solo pares consecutivos dentro de la misma `route_id`** (decisión ya
  fijada por el enunciado, no reabierta): nunca se infiere una conexión
  entre `route_id` distintos aunque compartan parada física — eso ya lo
  cubre `PROXIMO_A` (tarea 070) si están dentro del umbral de 300 m.
- **Bidireccional, con la comprobación real que pedía el enunciado antes de
  asumirlo.** Se ha revisado el fixture real (12 rutas de
  metro/EMT/metro ligero/cercanías) y el propio
  `ingesta/capturas/crtm_red_transporte_madrid.py`: ningún registro trae un
  campo de sentido único. El módulo de captura, a propósito, solo conserva
  la secuencia de un único viaje representativo por línea (el primero con
  `direction_id="0"` en el GTFS de origen) — el dataset nunca podría
  "indicar sentido único" con la información que trae. Los cuatro modos
  reales de la muestra son además, en la realidad física que modelan,
  servicios de ida y vuelta, no líneas de sentido único. Se genera por
  tanto también el sentido inverso (mismo `route_id`/`modo`, misma
  `linea`).
- **`stop_id` sin nodo correspondiente: se crea un `:ParadaTransporte`
  mínimo en vez de descartar la relación** (punto 2 del enunciado). En el
  flujo normal (`cargar_grafo.py`) esto no llega a ocurrir (las mismas
  rutas CRTM ya alimentan `nodos.py` antes que `relaciones.conectado_con`),
  pero `conectado_con()` no depende de ese orden: cada extremo de la
  relación lleva ya su propia forma mínima de nodo, y
  `cypher.conectado_con_query` hace `MERGE ... ON CREATE SET` sobre ambos
  extremos antes de `MERGE` la relación — si el nodo ya existe no se toca
  ninguna propiedad; si no existe, se crea con lo mínimo disponible en la
  propia parada CRTM. No se incluye `nombre`: `schema.cypher` no lo declara
  como propiedad esperada de `:ParadaTransporte` (a diferencia de
  `:Lugar`), mismo criterio que ya seguía `cypher.parada_transporte_query`
  desde la tarea 067.
- **`linea` forma parte del propio patrón `MERGE` de la relación**
  (`MERGE (a)-[r:CONECTADO_CON {linea: $linea}]->(b)`), no solo de un `SET`
  posterior: dos paradas consecutivas pueden estar conectadas por más de
  una línea (p. ej. dos autobuses que comparten un tramo), y cada una debe
  quedar como una relación distinta — si `linea` no formara parte del
  patrón, cargar una segunda línea sobre el mismo par de paradas
  sobrescribiría la primera en vez de añadir una relación nueva.
- **No hizo falta ampliar `extract.py`** (a diferencia de lo que suponía la
  nota de la tarea 070): `fetch_paradas_crtm_bronze()` ya devuelve los
  registros Bronce **de ruta** sin aplanar, con `stops` en orden de
  `sequence` — es `nodos.paradas_transporte_from_crtm_route_bronze` quien
  aplana a paradas sueltas, no `extract.py`. `relaciones.conectado_con`
  consume directamente esos mismos registros de ruta.

## Verificado con el fixture real

Línea 1 de metro (`route_id="4__1___"`): 33 paradas → 32 pares consecutivos
→ 64 relaciones (32 en cada sentido), primer par real `PINAR DE CHAMARTIN`
(`par_4_263`) → `BAMBU` (`par_4_262`) en ambos sentidos. Las líneas de
Cercanías del fixture (`"stops": []`, hallazgo de calidad de datos ya
documentado en `crtm_red_transporte_madrid.py`: `trips.txt`/
`stop_times.txt` vacíos en la fuente GTFS) no generan ninguna relación, sin
error.

## Restricciones respetadas

- No se han generado relaciones entre `route_id` distintos ni por
  proximidad física — solo adyacencia real dentro de la misma `route_id`.
- No se ha conectado a ninguna instancia Neo4j real.
- No se ha instalado el driver `neo4j` en esta EC2 — confirmado con
  `python3 -c "import neo4j"` fallando antes de correr los 80 tests, todos
  en verde.

## Relevante para tareas futuras

- Con `CONECTADO_CON` implementada, las 4 relaciones del esquema del grafo
  (`schema.cypher`) están completas y `cargar_grafo.py::cargar_grafo()` ya
  las cubre todas sin ningún hueco. La única pieza pendiente para
  ejecutarlo end-to-end sigue siendo la instancia Neo4j real (bloqueo
  documentado desde la tarea 043).
- El límite ya conocido desde la tarea 067 (resolución de entidades entre
  fuentes fuera de alcance) sigue aplicando: `crtm_red_transporte_madrid` y
  `transporte_publico_emt` pueden representar la misma parada física con
  dos nodos `:ParadaTransporte` distintos, y `CONECTADO_CON` solo se genera
  dentro de `crtm_red_transporte_madrid` — nunca conecta directamente un
  nodo de una fuente con el de la otra aunque sean la misma parada real
  (una ruta que cruce ambas fuentes tendría que atravesar primero un
  `PROXIMO_A` entre ambos nodos, si la distancia real cae dentro del
  umbral de 300 m).
