# 067 — ETL de carga de nodos del grafo Neo4j (sin conexión real, sigue bloqueado)

## Objetivo

Con Silver/Gold en producción continua (tareas 041-065) y el esquema del
grafo Neo4j diseñado sin aplicar (tarea 043, `infra/neo4j/schema/
schema.cypher`), esta tarea escribe el ETL que transformaría Gold/Bronze en
los nodos de ese grafo — **código puro, testado con fixtures, sin conectar a
ninguna instancia real**, porque el alta de AuraDB Free sigue bloqueada en
un paso manual de consola (mismo bloqueo documentado desde la tarea 043,
`infra/neo4j/README.md`).

**Alcance acotado a propósito** (así lo fijaba el enunciado, no reabierto):
solo los 5 labels de nodo del esquema (`:Distrito`, `:Barrio`, `:Lugar`,
`:EstacionMedida`, `:ParadaTransporte`) y la relación `PERTENECE_A`
(Barrio→Distrito, un simple lookup por código de distrito). Las otras 3
relaciones (`UBICADO_EN`, `PROXIMO_A`, `CONECTADO_CON`) quedan
explícitamente fuera, para tareas de seguimiento separadas.

## Qué se ha hecho

Directorio nuevo `grafo/` (análogo de `ingesta/`/`procesamiento/` para esta
pieza), con la misma separación lógica-pura/adaptador que ya usa
`procesamiento/silver_gold/*/transform.py` frente a
`glue_bronze_to_silver.py`:

- **`grafo/nodos.py`** (Python puro, sin `neo4j` como dependencia de
  import): funciones `<tipo>_from_<origen>(record)` que convierten un
  registro Gold/Bronze en el `dict` de propiedades de un nodo, y funciones
  plural `<tipo>s_from_<origen>(records)` que aplican la anterior a una
  lista y deduplican por `id`/`codigo` (`dedupe_nodes`) — necesario porque
  Gold es una serie por punto/estación **y hora** (o por ruta y parada en
  `crtm_red_transporte_madrid`), no una fila por entidad única.
- **`grafo/relaciones.py`**: `PERTENECE_A` a partir de un nodo `:Barrio` ya
  construido (que ya trae `distrito_codigo`, sin cálculo geométrico).
- **`grafo/cypher.py`**: funciones `*_query()` que traducen esos `dict` a
  sentencias `MERGE` parametrizadas (Python puro, **no importa `neo4j` a
  nivel de módulo**) + `Neo4jLoader`, la clase que ejecuta esas sentencias
  contra una instancia real, con `from neo4j import GraphDatabase` **dentro
  de `__init__`** (import perezoso) — así los tests de este módulo también
  corren sin el driver instalado.
- **`grafo/requirements.txt`**: solo `neo4j` (driver oficial), y solo para
  `Neo4jLoader`. No instalado en esta EC2.
- **`grafo/tests/`**: 31 tests (`unittest`), verificados corriendo
  **sin** el driver `neo4j` instalado (confirmado con
  `python3 -c "import neo4j"` fallando con `ModuleNotFoundError` antes de
  ejecutar la suite). Fixtures de `:Distrito`/`:Barrio`/`:ParadaTransporte`
  (CRTM)/`:Lugar` (POI) cargadas directamente desde las muestras reales ya
  commiteadas en `ingesta/capturas/samples/`; fixtures de Gold construidas
  a mano en el propio fichero de test (mismo patrón que
  `procesamiento/tests/test_bicimad_aggregate.py`), porque no existe ningún
  fixture de Gold commiteado en el repositorio — se replican a mano las
  claves exactas de cada `aggregate_silver_to_gold` real.
- **`grafo/README.md`**: estructura, orígenes por tipo de nodo, por qué
  hace falta deduplicar, limitaciones de datos reales encontradas (ver
  abajo), cómo se cargaría el día que exista una instancia real (referencia
  a `infra/neo4j/README.md` para las variables de entorno, sin
  redefinirlas).

## Decisiones de diseño relevantes

- **`id` = `"<fuente>:<id_origen>"`**, donde `fuente` es siempre el nombre
  del dataset de origen tal como lo usa el resto del repositorio — no
  estrictamente "el dataset Gold" (como sugiere el comentario original de
  `schema.cypher`), porque tres orígenes de `:Lugar`/`:ParadaTransporte`
  (`poi_madrid`, `crtm_red_transporte_madrid`, y el propio
  `barrios_distritos_madrid` para Distrito/Barrio) nunca tuvieron Gold.
- **`crtm_red_transporte_madrid`**: cada registro Bronze es una **ruta**
  completa (`route_id`, `mode`, lista `stops`), no una parada — la función
  correspondiente devuelve una lista de nodos por cada registro de entrada
  (a diferencia del resto del módulo, que devuelve `None` o un único
  `dict`), y el dedup por `stop_id` es imprescindible porque una misma
  parada física (p. ej. un intercambiador de metro) aparece repetida en
  varias rutas del mismo Bronze.
- **`cypher.py` con import perezoso de `neo4j`**: el enunciado autoriza a
  este módulo (a diferencia de `nodos.py`/`relaciones.py`) a depender del
  driver oficial, pero también pide que los tests de `MERGE` generado
  corran "sin conexión real" — sin especificar si eso implica también "sin
  el driver instalado". Se ha optado por la interpretación más estricta
  (compatible con la restricción explícita "no instales el driver `neo4j`
  en esta EC2... no hace falta para los tests"): las funciones `*_query()`
  que construyen las sentencias son Python puro sin ningún import de
  `neo4j`; solo `Neo4jLoader.__init__` lo importa, y lo hace de forma
  perezosa. Confirmado con un test dedicado
  (`test_cypher.py::Neo4jLoaderSinDriverTests`) que instanciar
  `Neo4jLoader` sin el paquete instalado falla con un `ImportError` claro,
  no con un error oscuro más adelante.
- **`MERGE ... SET n.ubicacion = CASE WHEN $lat IS NOT NULL AND $lon IS NOT
  NULL THEN point(...) ELSE n.ubicacion END`**: en vez de un `SET`
  incondicional, para que recargar un nodo cuyo origen no trae coordenadas
  en una ejecución concreta no borre una `ubicacion` ya cargada en una
  ejecución anterior — verificado por test (`test_estacion_medida_query_sin
  _ubicacion_manda_lat_lon_none`), no ejecutado contra una instancia real.

## Limitaciones de datos reales encontradas (documentadas, no corregidas)

Dos, ambas confirmadas inspeccionando el código real de `procesamiento/
silver_gold/`, no asumidas:

1. **`:ParadaTransporte` desde `transporte_publico_emt`: sin `nombre` ni
   `ubicacion`.** Gold de este dataset no incluye `location` (en Silver es
   la posición GPS del autobús en el instante de la estimación, no la de la
   parada fija — no se agrega en Gold, ver el docstring de
   `procesamiento/silver_gold/transporte_publico_emt/aggregate.py`), ni
   ningún campo de nombre de parada. El nodo se crea con `id`/`tipo`/
   `fuente` reales; `nombre`/`ubicacion` quedan a `None`.
2. **`:Lugar` desde `cartelera_cines_estrenos`: sin `ubicacion`.** Ni
   Bronze ni Silver ni Gold de este dataset traen coordenadas (confirmado
   en `procesamiento/silver_gold/cartelera_cines_estrenos/transform.py`:
   "no hace falta ningún `geo.py` ni columna `location`"), solo dirección
   postal. `ubicacion` queda siempre a `None` para este origen.

Además, documentado como riesgo de modelado (no un bug, una limitación de
diseño heredada de tratar cada fuente por separado): `crtm_red_transporte_
madrid` y `transporte_publico_emt` pueden representar la misma parada
física con dos nodos `:ParadaTransporte` distintos (prefijos de `id`
distintos), sin ninguna resolución de entidades entre fuentes en esta
tarea.

## Restricciones respetadas

- No se ha intentado crear ni conectar a ninguna instancia Neo4j real.
- No se han implementado `UBICADO_EN`/`PROXIMO_A`/`CONECTADO_CON`.
- No se ha instalado el driver `neo4j` en esta EC2 — confirmado con
  `python3 -c "import neo4j"` fallando antes de correr los 31 tests, todos
  en verde.
- No se ha tocado `infra/neo4j/schema/schema.cypher` (no se ha encontrado
  ningún error real en él).
- No se ha escrito nada en disco fuera del propio código commiteado ni
  queda nada programado (cron/systemd/bucle) en esta EC2.

## Relevante para tareas futuras

- El siguiente trabajo natural sobre `grafo/` son las 3 relaciones
  restantes. `UBICADO_EN` necesitará las geometrías de
  `barrios_distritos_madrid` (`geometry`), que **no** se han conservado en
  el `dict` de nodo `:Barrio`/`:Distrito` de esta tarea (solo `codigo`/
  `nombre`/`distrito_codigo`) — habrá que decidir si se extiende `nodos.py`
  o si el point-in-polygon vive en un módulo separado con acceso al Bronze
  crudo.
- La lectura real de Gold/Bronze desde S3 (boto3 + pandas/pyarrow, o
  reutilizar patrones de Glue) queda fuera de esta tarea, que recibe los
  registros ya como `list[dict]` en memoria.
- Ver `grafo/README.md` para el detalle completo de decisiones y
  limitaciones (no repetido aquí).
