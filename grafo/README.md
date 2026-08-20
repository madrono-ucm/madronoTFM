# `grafo/` — ETL Gold/Bronze → nodos del grafo Neo4j (tarea 067)

Análogo de `ingesta/`/`procesamiento/` para la pieza de grafo urbano que
diseñó la tarea 043 (`infra/neo4j/README.md`, `infra/neo4j/schema/
schema.cypher`): mientras esos dos directorios llevan datos reales de Madrid
a Bronze y de Bronze a Silver/Gold, `grafo/` transforma esas capas ya
existentes (Gold cuando existe; Bronze directo para las tres fuentes que
nunca tuvieron Silver/Gold: `barrios_distritos_madrid`, `poi_madrid`,
`crtm_red_transporte_madrid`) en los `dict` de propiedades que definió el
esquema de Neo4j, y en las sentencias `MERGE` que los cargarían.

**Alcance de esta tarea, acotado a propósito**: los nodos de los 5 labels
del esquema (`:Distrito`, `:Barrio`, `:Lugar`, `:EstacionMedida`,
`:ParadaTransporte` — el enunciado los agrupa como "4 tipos" contando
Distrito/Barrio como una única jerarquía administrativa) y la relación
`PERTENECE_A` (Barrio→Distrito, un simple lookup por código de distrito).
Las otras 3 relaciones del esquema
(`UBICADO_EN`, point-in-polygon; `PROXIMO_A`, proximidad genérica;
`CONECTADO_CON`, adyacencia real de red de transporte) son, deliberadamente,
tareas de seguimiento separadas — no están implementadas aquí.

**Sigue sin existir ninguna instancia Neo4j real** (bloqueo de alta manual en
`https://console.neo4j.io`, documentado en `infra/neo4j/README.md` desde la
tarea 043, sin resolver por esta tarea). Todo el código de este directorio es
código puro, testado con fixtures, sin conectar a nada.

## Estructura

| Fichero | Depende de `neo4j` (driver) | Qué hace |
|---|---|---|
| `nodos.py` | No | Convierte un registro Gold/Bronze en el `dict` de propiedades de un nodo (`<tipo>_from_<origen>`), y una lista de registros en una lista de nodos deduplicados por `id`/`codigo` (`<tipo>s_from_<origen>`). |
| `relaciones.py` | No | `PERTENECE_A` (Barrio→Distrito) a partir de un nodo `:Barrio` ya construido por `nodos.py`. |
| `cypher.py` | Solo `Neo4jLoader`, de forma perezosa | Traduce esos `dict` a sentencias `MERGE` parametrizadas (funciones `*_query()`, Python puro) y las ejecuta contra una instancia real (`Neo4jLoader`, que hace `from neo4j import GraphDatabase` dentro de `__init__`, no a nivel de módulo). |
| `requirements.txt` | — | Solo `neo4j` (el driver oficial), y solo para `Neo4jLoader`. No instalado en esta EC2. |
| `tests/` | No | `unittest`, sin conexión real ni el driver instalado (ver más abajo). |

## Orígenes por tipo de nodo

| Label | Función(es) en `nodos.py` | Origen |
|---|---|---|
| `:Distrito` | `distrito_from_bronze` / `distritos_from_bronze` | `barrios_distritos_madrid` (Bronze, distritos) |
| `:Barrio` | `barrio_from_bronze` / `barrios_from_bronze` | `barrios_distritos_madrid` (Bronze, barrios) |
| `:EstacionMedida` | `estacion_medida_from_trafico_gold`, `..._calidad_aire_gold`, `..._ruido_gold` (+ plural) | Gold de `trafico`, `calidad_aire`, `ruido` |
| `:ParadaTransporte` | `parada_transporte_from_transporte_publico_emt_gold`, `..._bicimad_gold`, `paradas_transporte_from_crtm_bronze` | Gold de `transporte_publico_emt`, `bicimad`; Bronze de `crtm_red_transporte_madrid` |
| `:Lugar` | `lugar_from_poi_bronze`, `..._aparcamientos_gold`, `..._cartelera_cines_gold` (+ plural) | Bronze de `poi_madrid`; Gold de `aparcamientos`, `cartelera_cines_estrenos` |

`id` sigue el formato que ya documentaba `schema.cypher`
(`"<fuente>:<id_origen>"`), donde `fuente` es siempre el nombre del dataset
de origen tal como lo usa el resto del repositorio (`trafico`,
`calidad_aire`, `ruido`, `transporte_publico_emt`, `bicimad`,
`crtm_red_transporte_madrid`, `poi_madrid`, `aparcamientos`,
`cartelera_cines_estrenos`) — no se ha reinterpretado como "el dataset Gold"
estrictamente, ya que tres orígenes de `:Lugar`/`:ParadaTransporte` no tienen
Gold.

## Por qué hace falta deduplicar (`dedupe_nodes`)

Gold es una serie temporal: una fila por punto de medida/estación **y
hora** (`trafico`, `calidad_aire`, `ruido`, `bicimad`), o por estación/línea
**y hora** (`transporte_publico_emt`), o por película/cine **y día**
(`cartelera_cines_estrenos`). Un nodo del grafo es una entidad única, así
que las funciones plural (`estaciones_medida_from_trafico_gold`, etc.)
convierten cada fila y luego deduplican por `id`, conservando el primer
registro visto — coherente con el propio `aggregate.py` de cada dataset, que
ya trata como "representativas" (constantes en la práctica) las columnas
como `location`/`name` tomándolas del primer registro de cada bucket.

`crtm_red_transporte_madrid` es el caso más particular: cada registro Bronze
es una **ruta** completa (`route_id`, `mode`, lista `stops`), así que
`paradas_transporte_from_crtm_route_bronze` (nombre en singular pero
devuelve una **lista**) expande un solo registro en varios nodos antes de
deduplicar por `stop_id` — necesario porque una misma parada (estación de
metro con trasbordo, p. ej.) aparece en varias rutas.

## Limitaciones de datos reales (no corregidas en esta tarea, documentadas a propósito)

- **`:ParadaTransporte` desde `transporte_publico_emt`: sin `nombre` ni
  `ubicacion`.** Gold de este dataset (`aggregate.py`) agrega por
  `(stop_id, line, fecha, hora)` el tiempo de espera estimado, y
  deliberadamente **no** incluye `location` — en Silver, `location` es la
  posición GPS del autobús en el instante de la estimación, no la de la
  parada (cambia en cada muestra, no tiene un valor representativo fijo, ver
  el docstring de `procesamiento/silver_gold/transporte_publico_emt/
  aggregate.py`). Tampoco hay ningún campo de nombre de parada en Silver/Gold
  (solo `destination`, el destino del autobús). El nodo se crea igual (con
  `id`/`tipo`/`fuente` reales y estables) pero `nombre`/`ubicacion` quedan a
  `None`. Si una tarea futura necesita la ubicación real de las paradas EMT,
  la fuente correcta sería el catálogo oficial de paradas de la EMT (no
  capturado por ningún productor de `ingesta/` a día de esta tarea), no
  intentar promediar posiciones de autobús.
- **`:Lugar` desde `cartelera_cines_estrenos`: sin `ubicacion`.** Ni Bronze
  ni Silver ni Gold de este dataset traen coordenadas (confirmado en
  `procesamiento/silver_gold/cartelera_cines_estrenos/transform.py`: "no
  hace falta ningún `geo.py` ni columna `location`") — solo dirección postal
  (`address`, `postal_code`, `locality`). `ubicacion` queda siempre a `None`
  para este origen. Geocodificar la dirección (p. ej. contra el callejero de
  `callejero_madrid`, también Bronze-only) es trabajo de una tarea futura, no
  de esta.
- **`crtm_red_transporte_madrid` y `transporte_publico_emt` pueden modelar la
  misma parada física dos veces, sin deduplicar entre sí.** Ambas fuentes
  tienen prefijos de `id`/`fuente` distintos
  (`crtm_red_transporte_madrid:<stop_id>` vs.
  `transporte_publico_emt:<stop_id>`), así que nunca colisionan en Neo4j,
  pero tampoco hay ninguna resolución de entidades entre ellas en esta tarea
  — dos nodos `:ParadaTransporte` distintos pueden representar la misma
  marquesina real. Además, el `mode` que publica CRTM incluye un valor
  `"emt"` propio (líneas interurbanas gestionadas por CRTM bajo ese modo),
  que no debe confundirse con el `tipo="emt"` que usan los nodos derivados
  de la API de tiempo real de la EMT — son dos fuentes distintas con el
  mismo nombre de modo por coincidencia de nomenclatura de origen.
- **`callejero_madrid` no se usa en esta tarea.** El enunciado lo menciona
  como fuente Bronze-only "que nunca pasó por Silver/Gold" en el mismo grupo
  que `barrios_distritos_madrid`/`poi_madrid`/`crtm_red_transporte_madrid`,
  pero el alcance concreto (4 tipos de nodo) no incluye ningún label que
  derive de callejero (vías/cruces) — queda disponible para cuando una tarea
  futura lo necesite (p. ej., como referencia geométrica para `UBICADO_EN`).

## Cómo se cargaría (cuando exista una instancia real)

```python
from grafo import nodos, relaciones
from grafo.cypher import Neo4jLoader

# NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD / NEO4J_DATABASE:
# ver infra/neo4j/README.md, "Cómo se conectaría el proyecto" -- no
# redefinidas aquí.
with Neo4jLoader(uri, username, password, database) as loader:
    barrio_nodes = nodos.barrios_from_bronze(barrio_bronze_records)

    loader.load_distritos(nodos.distritos_from_bronze(distrito_bronze_records))
    loader.load_barrios(barrio_nodes)
    loader.load_estaciones_medida(nodos.estaciones_medida_from_trafico_gold(trafico_gold_records))
    loader.load_estaciones_medida(nodos.estaciones_medida_from_calidad_aire_gold(calidad_aire_gold_records))
    loader.load_estaciones_medida(nodos.estaciones_medida_from_ruido_gold(ruido_gold_records))
    loader.load_paradas_transporte(nodos.paradas_transporte_from_transporte_publico_emt_gold(emt_gold_records))
    loader.load_paradas_transporte(nodos.paradas_transporte_from_bicimad_gold(bicimad_gold_records))
    loader.load_paradas_transporte(nodos.paradas_transporte_from_crtm_bronze(crtm_bronze_records))
    loader.load_lugares(nodos.lugares_from_poi_bronze(poi_bronze_records))
    loader.load_lugares(nodos.lugares_from_aparcamientos_gold(aparcamientos_gold_records))
    loader.load_lugares(nodos.lugares_from_cartelera_cines_gold(cartelera_gold_records))

    loader.load_pertenece_a(relaciones.pertenece_a_from_barrios(barrio_nodes))
```

No se ha ejecutado nunca contra una instancia real (bloqueado, ver arriba) —
este bloque es documentación de uso previsto, no un script probado
end-to-end. Requiere ejecutar antes `infra/neo4j/schema/schema.cypher` (los
constraints `UNIQUE` de los que dependen los `MERGE`).

Falta, además de la instancia real: leer Gold/Bronze desde S3 (esta tarea
solo cubre la transformación en memoria, dado un `list[dict]` ya cargado —
la lectura real de parquet/JSON desde S3 es trabajo de un futuro job de
Glue o script, mismo patrón que `procesamiento/silver_gold/*/
glue_bronze_to_silver.py` frente a `transform.py`).

## Tests

`grafo/tests/` (`python3 -m unittest discover -s grafo/tests -t .`, 31
tests, ejecutados en esta EC2 sin el driver `neo4j` instalado —
confirmado con `python3 -c "import neo4j"` fallando con
`ModuleNotFoundError` antes de correr los tests):

- `test_nodos.py` / `test_relaciones.py`: fixtures de `:Distrito`/`:Barrio`/
  `:ParadaTransporte`(CRTM)/`:Lugar`(POI) tomadas directamente de
  `ingesta/capturas/samples/` (sin duplicarlas); fixtures de Gold
  (`trafico`, `calidad_aire`, `ruido`, `transporte_publico_emt`, `bicimad`,
  `aparcamientos`, `cartelera_cines_estrenos`) construidas a mano en el
  propio fichero de test, mismo patrón que
  `procesamiento/tests/test_bicimad_aggregate.py` — no existe ningún
  fixture de Gold commiteado en el repositorio (Gold solo se genera
  ejecutando `aggregate.py` sobre Silver, y ni Silver ni Gold están
  commiteados como fixtures), así que se replican a mano las claves exactas
  que produce cada `aggregate_silver_to_gold` real.
- `test_cypher.py`: verifica las sentencias/parámetros generados por las
  funciones `*_query()` por inspección de la cadena, y confirma que
  `Neo4jLoader(...)` falla con `ImportError` (no con un error oscuro) si se
  instancia sin el driver instalado.

## Relevante para tareas futuras

- Las 3 relaciones restantes (`UBICADO_EN`, `PROXIMO_A`, `CONECTADO_CON`)
  son el siguiente trabajo natural sobre este mismo directorio — probablemente
  un `grafo/relaciones.py` ampliado (o módulos nuevos, `grafo/ubicado_en.py`
  etc., si la lógica geométrica lo justifica) más funciones `*_query()`
  adicionales en `cypher.py`. `UBICADO_EN` necesita las geometrías de
  `barrios_distritos_madrid` (ya cargadas por `nodos.py` para
  `:Distrito`/`:Barrio`, pero el polígono en sí — `geometry` — no se ha
  conservado en el `dict` de nodo, solo `codigo`/`nombre`/`distrito_codigo`;
  habrá que decidir si extenderlo o mantener el point-in-polygon en un
  módulo separado con acceso al Bronze crudo).
- Antes de cargar datos reales, conviene decidir cómo se resuelve el import
  de `procesamiento/silver_gold/*` para leer Gold/Bronze reales desde S3
  (boto3 + pandas/pyarrow, o reutilizar patrones de Glue) — fuera del
  alcance de esta tarea, que recibe los registros ya como `list[dict]`.
- El bloqueo real (alta manual de AuraDB Free) sigue siendo el mismo que
  documentó la tarea 043 — ninguna tarea de ETL puede resolverlo, solo un
  humano completando el flujo de `https://console.neo4j.io`.
