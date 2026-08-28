# `grafo/` — ETL Gold/Bronze → nodos del grafo Neo4j (tareas 067/069/070/071)

Análogo de `ingesta/`/`procesamiento/` para la pieza de grafo urbano que
diseñó la tarea 043 (`infra/neo4j/README.md`, `infra/neo4j/schema/
schema.cypher`): mientras esos dos directorios llevan datos reales de Madrid
a Bronze y de Bronze a Silver/Gold, `grafo/` transforma esas capas ya
existentes (Gold cuando existe; Bronze directo para las tres fuentes que
nunca tuvieron Silver/Gold: `barrios_distritos_madrid`, `poi_madrid`,
`crtm_red_transporte_madrid`) en los `dict` de propiedades que definió el
esquema de Neo4j, y en las sentencias `MERGE` que los cargarían.

La tarea 067 escribió la transformación (`nodos.py`/`relaciones.py`/
`cypher.py`) recibiendo los registros ya como `list[dict]` en memoria, sin
leer nada real. La tarea 069 añadió `extract.py` (y el entry point
`cargar_grafo.py`), que sí consulta datos reales de esta cuenta AWS
(`eu-west-1`, `222234418587`): Athena para Gold (tareas 066/068) y S3 directo
para las tres fuentes Bronze-only. La tarea 070 añade las dos relaciones
espaciales genéricas del esquema, `UBICADO_EN` y `PROXIMO_A` (`geo.py`,
ampliación de `relaciones.py`/`cypher.py`/`cargar_grafo.py`). La tarea 071
añade la última relación del esquema, `CONECTADO_CON` (adyacencia real de
la red de transporte, a partir de las rutas de `crtm_red_transporte_madrid`).

**Alcance cubierto a día de la tarea 071**: los nodos de los 5 labels del
esquema (`:Distrito`, `:Barrio`, `:Lugar`, `:EstacionMedida`,
`:ParadaTransporte` — el enunciado de la tarea 067 los agrupaba como "4
tipos" contando Distrito/Barrio como una única jerarquía administrativa) y
las 4 relaciones del esquema: `PERTENECE_A` (Barrio→Distrito, tarea 067),
`UBICADO_EN` (point-in-polygon contra los barrios, tarea 070), `PROXIMO_A`
(proximidad genérica por Haversine, tarea 070) y `CONECTADO_CON` (adyacencia
real de red de transporte, tarea 071).

**Nota de estado (28/8)**: los tres párrafos anteriores describen el alcance
tal como quedó en la tarea 071. Desde entonces la instancia Neo4j real
**existe y está cargada** (AuraDB Free, alta resuelta en la tarea 080, ver
"Bloqueadores" en `PLAN.md`): `cargar_grafo.py` se ha ejecutado end-to-end
contra ella tres veces (tareas 080/087/094) y el esquema
(`infra/neo4j/schema/schema.cypher`) quedó aplicado el 26/8 (tarea 094). El
código de este directorio sigue siendo puro y testado con fixtures, pero
"sin conectar a nada" ya no describe el estado del proyecto — ver "Cómo se
carga" más abajo.

## Estructura

| Fichero | Depende de `neo4j` (driver) | Qué hace |
|---|---|---|
| `extract.py` | No | Consulta Athena (Gold, tareas 066/068) o lee JSON de S3 (Bronze-only) y devuelve `list[dict]` en el formato que esperan `nodos.py`/`relaciones.py`. También lee la muestra local de POIs de OSM (`fetch_osm_pois_sample`, tarea 083). Solo depende de `boto3` (tarea 069). |
| `nodos.py` | No | Convierte un registro Gold/Bronze en el `dict` de propiedades de un nodo (`<tipo>_from_<origen>`), y una lista de registros en una lista de nodos deduplicados por `id`/`codigo` (`<tipo>s_from_<origen>`). También enriquece `:Lugar` con POIs de OSM por proximidad (`enrich_lugar(es)_con_osm`, tarea 083). |
| `geo.py` | No | Point-in-polygon (ray casting sobre GeoJSON `Polygon`/`MultiPolygon`), distancia Haversine y "vecino más cercano dentro de un radio" (`nearest_within_radius`, tarea 083), todo Python puro sin dependencias de geometría (tarea 070). |
| `relaciones.py` | No | `PERTENECE_A` (Barrio→Distrito, tarea 067); `UBICADO_EN` y `PROXIMO_A` (tarea 070, usan `geo.py`); `CONECTADO_CON` (tarea 071, adyacencia real de red de transporte a partir de rutas CRTM). |
| `cypher.py` | Solo `Neo4jLoader`, de forma perezosa | Traduce esos `dict` a sentencias `MERGE` parametrizadas (funciones `*_query()`, Python puro) y las ejecuta contra una instancia real (`Neo4jLoader`, que hace `from neo4j import GraphDatabase` dentro de `__init__`, no a nivel de módulo). |
| `cargar_grafo.py` | Solo al importar `Neo4jLoader` (perezoso hasta instanciarlo) | Entry point que encadena `extract.py` → `nodos.py`/`relaciones.py` → `cypher.py`. Ejecutado varias veces contra la instancia real (tareas 080/087/094), ver "Cómo se carga" más abajo. |
| `requirements.txt` | — | `neo4j` (solo para `Neo4jLoader`, no instalado en esta EC2) y `boto3` (para `extract.py`, ya instalado). |
| `tests/` | No | `unittest`, sin conexión real ni el driver instalado (ver más abajo). |

## Orígenes por tipo de nodo

| Label | Función(es) en `nodos.py` | Origen |
|---|---|---|
| `:Distrito` | `distrito_from_bronze` / `distritos_from_bronze` | `barrios_distritos_madrid` (Bronze, distritos) |
| `:Barrio` | `barrio_from_bronze` / `barrios_from_bronze` | `barrios_distritos_madrid` (Bronze, barrios) |
| `:EstacionMedida` | `estacion_medida_from_trafico_gold`, `..._calidad_aire_gold`, `..._ruido_gold`, `..._aforos_peatones_bicicletas_gold` (+ plural) | Gold de `trafico`, `calidad_aire`, `ruido`, `aforos_peatones_bicicletas` (tarea 087) |
| `:ParadaTransporte` | `parada_transporte_from_transporte_publico_emt_gold`, `..._bicimad_gold`, `paradas_transporte_from_crtm_bronze` | Gold de `transporte_publico_emt`, `bicimad`; Bronze de `crtm_red_transporte_madrid` |
| `:Lugar` | `lugar_from_poi_bronze`, `..._parque_bronze` (FIL_04), `..._aparcamientos_gold`, `..._cartelera_cines_gold` (+ plural) | Bronze de `poi_madrid` y `parques_jardines`; Gold de `aparcamientos`, `cartelera_cines_estrenos` |

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

## `UBICADO_EN` y `PROXIMO_A` (tarea 070)

`grafo/geo.py` implementa, en Python puro (sin `shapely` ni ninguna otra
dependencia de geometría — mismo criterio que evitó `pyproj` en la
reproyección de tráfico de la tarea 041, `procesamiento/silver_gold/trafico/
geo.py`):

- **Point-in-polygon por ray casting** (`_point_in_ring`/
  `_point_in_polygon_coords`/`point_in_geometry`), sobre las coordenadas
  GeoJSON reales de `barrios_distritos_madrid` (`geometry.coordinates`,
  formato `[longitud, latitud]` por punto — no `[lat, lon]`). Soporta
  `Polygon` (con huecos, si los hubiera) y también `MultiPolygon`, aunque el
  fixture real commiteado (`ingesta/capturas/samples/
  barrios_distritos_madrid_barrios_sample.json`, 6 barrios de muestra) solo
  trae `"type": "Polygon"` — se soporta `MultiPolygon` de forma defensiva
  por si el dataset completo (no solo la muestra) incluye algún barrio con
  varias partes desconectadas.
- **Distancia Haversine** (`haversine_m`), radio terrestre medio 6371 km.

`grafo/relaciones.py` añade dos funciones que usan `geo.py`:

- `ubicado_en(nodos_con_ubicacion, barrios)`: un `{nodo_id, barrio_codigo}`
  por cada nodo (`:Lugar`/`:EstacionMedida`/`:ParadaTransporte`, cualquiera
  con `ubicacion`) que cae dentro de algún barrio. **`barrios` son los
  registros Bronce crudos** de `barrios_distritos_madrid`
  (`extract.fetch_barrios_bronze()`, con `neighbourhood_id` + `geometry`),
  **no** los nodos `:Barrio` ya construidos por `nodos.barrios_from_bronze`
  — esos no conservan la geometría (`schema.cypher` no define ninguna
  propiedad de geometría para `:Barrio`, solo `codigo`/`nombre`/
  `distrito_codigo`), así que no serviría pasarlos. Esta es la decisión que
  la tarea 069 dejaba abierta ("decidir si se extiende `nodos.py` o si el
  point-in-polygon vive en un módulo separado con acceso al Bronze crudo"):
  se ha optado por lo segundo, sin tocar `nodos.py` (ya testado, y su
  contrato — un nodo `:Barrio` con exactamente las propiedades del esquema —
  no debería cargar datos que no le corresponden a él).
- `proximo_a(nodos_con_ubicacion, umbral_m=300)`: un `{origen_id, destino_id,
  distancia_m}` por cada pareja de nodos con `ubicacion` y **`tipo`**
  (la propiedad de `nodos.py`, p. ej. `"trafico"`, `"bicimad"`,
  `"poi_turistico"` — no el label de Neo4j) distintos, cuya distancia
  Haversine no supera el umbral (300 m por defecto, fijado por el
  enunciado). Dos nodos del mismo `tipo` no generan relación entre sí (ya
  comparten semántica por ser del mismo tipo de sensor/lugar — dos
  `:EstacionMedida` de tráfico no aportan nada relacionándose entre ellas),
  pero dos nodos del mismo label de Neo4j con `tipo` distinto sí (una
  `:EstacionMedida` de tráfico y una de ruido, por ejemplo). No se limita el
  número de relaciones por nodo (zonas densas del centro pueden generar
  decenas), tal como pedía el enunciado — es información real, no ruido. La
  relación se genera en un único sentido por pareja (`a -> b`), igual que
  documenta `schema.cypher`.

`grafo/cypher.py` añade `ubicado_en_query()`/`proximo_a_query()` (y
`Neo4jLoader.load_ubicado_en`/`load_proximo_a`). `ubicado_en_query` hace
`MATCH (n {id: $nodo_id})` **sin restringir el label**: los prefijos
`fuente` de `id` de los tres labels con ubicación no se solapan entre sí
(ver tabla de arriba), así que `id` ya es único en la práctica en todo el
grafo, no solo dentro de su propio constraint `UNIQUE` por label — no hace
falta saber a qué label pertenece cada nodo para construir el `MATCH`.

**Nota de rendimiento, no resuelta aquí**: `proximo_a` compara todas las
parejas de nodos (`O(n²)`) — con los volúmenes reales de esta cuenta a
fecha de la tarea 069 (~4700 `trafico` + ~700 `bicimad` + ~30 `calidad_aire`/
`ruido` + ...) son unas pocas decenas de millones de comparaciones, factible
en Python pero no instantáneo. No se ha optimizado con ningún índice
espacial (p. ej. un grid de celdas de ~300 m) porque el enunciado no lo pedía
y añadiría complejidad sin datos reales que la justifiquen todavía — si el
volumen de nodos crece mucho, sería la primera optimización a considerar.

## `CONECTADO_CON` (tarea 071)

`grafo/relaciones.py::conectado_con(rutas_crtm)` genera la adyacencia real de
la red de transporte a partir de las rutas Bronce de
`crtm_red_transporte_madrid` (`extract.fetch_paradas_crtm_bronze()`): cada
registro trae, por `route_id` (línea), una lista `stops` **ya ordenada por
`sequence`** (`nodos.paradas_transporte_from_crtm_route_bronze` la consume
igual para construir los nodos `:ParadaTransporte`, tarea 067). Para cada par
de paradas consecutivas dentro de la misma `route_id` se genera una relación
`{origen, destino, modo, linea}` (`linea` = `short_name`, o `route_id` si el
registro no trae `short_name`).

**Decisión ya fijada por el enunciado (no reabierta)**: solo pares
consecutivos dentro de la misma `route_id` — nunca se infiere una conexión
entre `route_id` distintos aunque compartan parada física (dos líneas que
confluyen en un intercambiador quedan relacionadas por `PROXIMO_A`, tarea
070, si están dentro del umbral de 300 m, no por `CONECTADO_CON`).

**Bidireccional, con la comprobación real que pedía el enunciado antes de
asumirlo**: además del sentido de `sequence` creciente se genera también el
sentido inverso (mismo `route_id`/`modo`, misma `linea`). Se ha revisado el
fixture real (`crtm_red_transporte_madrid_sample.json`, 12 rutas de
metro/EMT/metro ligero/cercanías) y el propio
`ingesta/capturas/crtm_red_transporte_madrid.py`, sin encontrar ningún campo
de sentido único: el módulo de captura, a propósito, solo conserva la
secuencia de un único viaje representativo por línea (el primero con
`direction_id="0"` en el GTFS de origen, ver su docstring "Esquema mínimo
elegido") — el dataset nunca podría "indicar sentido único" con la
información que trae, así que no hay ninguna señal real que contradiga la
bidireccionalidad. Los cuatro modos reales de la muestra (metro, autobús
urbano, metro ligero, cercanías) son además, en la realidad física que
modelan, servicios de ida y vuelta, no líneas de sentido único.

**`stop_id` sin nodo correspondiente: se crea un `:ParadaTransporte` mínimo
en vez de descartar la relación** (punto 2 del enunciado). En el flujo
normal (`cargar_grafo.py`) esto no llega a ocurrir — las mismas rutas CRTM
alimentan primero `nodos.paradas_transporte_from_crtm_bronze` (todos los
`stop_id` de todas las rutas obtienen nodo) y solo después
`relaciones.conectado_con` —, pero `conectado_con()` no depende de ese
orden: cada extremo de la relación (`origen`/`destino`) lleva ya su propia
forma mínima de `:ParadaTransporte` (`id`/`tipo`/`ubicacion`, mismo `id` que
construiría `nodos.py` para el mismo `stop_id` — sin `nombre`, ver más
abajo), y `cypher.conectado_con_query` hace `MERGE ... ON CREATE SET` sobre
ambos extremos antes de `MERGE` la relación: si el nodo ya existe (caso
normal) no se toca ninguna propiedad; si no existe, se crea con lo mínimo
disponible en la propia parada CRTM.

No se incluye `nombre` en ese `:ParadaTransporte` mínimo: `schema.cypher` no
lo declara como propiedad esperada de este label (a diferencia de `:Lugar`),
mismo criterio que ya seguía `cypher.parada_transporte_query` desde la tarea
067 (tampoco persiste `nombre`, aunque el nodo `dict` de `nodos.py` lo
lleve) — no se reabre esa decisión aquí.

`linea` forma parte del propio patrón `MERGE` de la relación en
`conectado_con_query` (`MERGE (a)-[r:CONECTADO_CON {linea: $linea}]->(b)`),
no solo de un `SET` posterior: dos paradas consecutivas pueden estar
conectadas por más de una línea (p. ej. dos autobuses que comparten un
tramo), y cada una debe quedar como una relación distinta — si `linea` no
formara parte del patrón, cargar una segunda línea sobre el mismo par de
paradas sobrescribiría la primera en vez de añadir una relación nueva.

Verificado con el fixture real: la línea 1 de metro (`route_id="4__1___"`)
trae 33 paradas → 32 pares consecutivos → 64 relaciones (32 en cada
sentido); las líneas de Cercanías del fixture (`"stops": []`, ver hallazgo
de calidad de datos documentado en `crtm_red_transporte_madrid.py`) no
generan ninguna relación, sin error.

## `extract.py` (tarea 069): la capa de lectura real

Consulta **Athena** para todo lo que tiene Gold (decisión ya tomada por el
enunciado de la tarea 069, no releer Parquet directamente con
`pyarrow`/`pandas`: evita duplicar la lógica de particionado que ya resuelve
Partition Projection, tarea 068), y **S3 directo** (JSON) para los tres
orígenes Bronze-only, que no tienen tabla en el catálogo de Glue.

| Función | Origen real | Nodo que alimenta |
|---|---|---|
| `fetch_estaciones_trafico` | Athena, `gold.trafico_por_punto_hora` | `estaciones_medida_from_trafico_gold` |
| `fetch_estaciones_calidad_aire` | Athena, `gold.calidad_aire_por_estacion_contaminante_hora` | `estaciones_medida_from_calidad_aire_gold` |
| `fetch_estaciones_ruido` | Athena, `gold.ruido_por_estacion_periodo_fecha` | `estaciones_medida_from_ruido_gold` |
| `fetch_estaciones_aforos_peatones_bicicletas` | Athena, `gold.aforos_peatones_bicicletas_por_estacion_modo_hora` | `estaciones_medida_from_aforos_peatones_bicicletas_gold` |
| `fetch_paradas_emt` | Athena, `gold.transporte_publico_emt_por_parada_hora` | `paradas_transporte_from_transporte_publico_emt_gold` |
| `fetch_paradas_bicimad` | Athena, `gold.bicimad_por_estacion_hora` | `paradas_transporte_from_bicimad_gold` |
| `fetch_lugares_aparcamientos` | Athena, `gold.aparcamientos_por_parking_hora` | `lugares_from_aparcamientos_gold` |
| `fetch_lugares_cartelera_cines` | Athena, `gold.cartelera_cines_estrenos_por_pelicula_cine_fecha` | `lugares_from_cartelera_cines_gold` |
| `fetch_distritos_bronze` | S3, `barrios_distritos_madrid_distritos/` | `distritos_from_bronze` |
| `fetch_barrios_bronze` | S3, `barrios_distritos_madrid_barrios/` | `barrios_from_bronze` |
| `fetch_poi_bronze` | S3, `poi_madrid/` | `lugares_from_poi_bronze` |
| `fetch_paradas_crtm_bronze` | S3, `crtm_red_transporte_madrid/` | `paradas_transporte_from_crtm_bronze` |

Cada consulta Athena agrega en el propio Athena (`GROUP BY <id>`,
`max_by(<columna>, date)`) en vez de traer el histórico completo — un nodo
del grafo es una entidad única y su identidad/ubicación es, en la práctica,
constante en el tiempo (mismo criterio que `dedupe_nodes`), así que traer
todo el histórico (cientos de millones de filas en `trafico`, ver tarea 068)
solo para quedarse con `id`/`nombre`/`lat`/`lon` desperdiciaría bytes
escaneados. Se acota además a los últimos 14 días (`_RECENT_WINDOW_DAYS`)
con un filtro de partición, aprovechando la Partition Projection de la
tarea 068. `max_by(col, date)` se queda con el valor de la fila con la
`date` más reciente dentro de esa ventana — no un valor arbitrario.

**Gold aplana la ubicación a columnas `lat`/`lon`** (a diferencia de Silver,
que la anida en una columna `location` struct, ver `infra/terraform/
glue.tf`); `grafo.nodos._location()` espera, en cambio, `record["location"] =
{"lat": ..., "lon": ...}`. `extract._nest_location()` hace esa traducción
para no tener que tocar `nodos.py` (ya testado, y no le corresponde saber de
dónde vienen sus columnas).

`aforos_peatones_bicicletas` (tarea 087) sigue la misma regla: aunque
`aggregate.py` (tarea 054) construye el registro Python con `location` como
`dict` anidado (`{"lat": ..., "lon": ..., "srid": ...}`), el job real de
Glue que escribe Gold lo aplana igual que los demás datasets -- verificado
contra el catálogo real (`DESCRIBE aforos_peatones_bicicletas_por_estacion_
modo_hora`, tarea 087) tras un primer intento fallido que asumió lo
contrario leyendo solo `aggregate.py` en Python puro. **No infieras el
esquema de Gold leyendo solo la función de agregación Python de un
dataset** -- compáralo siempre contra el catálogo real antes de escribir el
SQL de un origen nuevo.

**`get_query_results` de Athena devuelve todo como texto** (`VarCharValue`),
sea cual sea el tipo real de columna — comportamiento documentado de la
API, no un bug. `extract._cast_athena_value()` los convierte de vuelta a
`int`/`float` según `ResultSetMetadata.ColumnInfo[].Type`, imprescindible
para que `lat`/`lon` lleguen a `Neo4jLoader` como números (el `point({...})`
de Cypher que construye `cypher.py` los necesita numéricos, no como cadena).

### Verificado contra datos reales de esta cuenta (`eu-west-1`, `222234418587`) al escribir este módulo

Las 11 funciones originales se han ejecutado una vez contra Athena/S3 reales
para validar el SQL antes de darlo por bueno — no simulado.
`fetch_estaciones_aforos_peatones_bicicletas` (tarea 087) también se ha
verificado contra Athena real: **0 filas, no por un bug de la consulta**.
La fuente externa (`datos.madrid.es`, dataset
`300321-0-aforos-peatones-bicicletas`) no publica datos nuevos desde el
30/6/2024 — el único objeto real en Gold tiene esa fecha, fuera del rango
de Partition Projection configurado (`2026-08-01,NOW+1DAY`), y por tanto
invisible a cualquier consulta. Detalle completo en
`doc/087-grafo-aforos-peatones-bicicletas-neo4j-real.md` y la corrección en
`doc/086-afluencia-estimada-grafo.md` — `aforos_peatones_bicicletas` ya no
es señal primaria de `afluencia_estimada` (tarea 089).

| Función | Filas reales |
|---|---|
| `fetch_estaciones_trafico` | 4678 |
| `fetch_estaciones_calidad_aire` | 23 |
| `fetch_estaciones_ruido` | 31 |
| `fetch_estaciones_aforos_peatones_bicicletas` | 0 (fuente externa descontinuada desde 2024-06-30, ver arriba) |
| `fetch_paradas_emt` | **1** (ver hallazgo abajo) |
| `fetch_paradas_bicimad` | 679 |
| `fetch_lugares_aparcamientos` | 0 (Gold vacío, ver hallazgo abajo) |
| `fetch_lugares_cartelera_cines` | 0 (Gold vacío, ya conocido desde la tarea 063) |
| `fetch_distritos_bronze` / `fetch_barrios_bronze` / `fetch_poi_bronze` / `fetch_paradas_crtm_bronze` | 0 (ver hallazgo abajo) |

**Hallazgo real 1 — `transporte_publico_emt` Gold solo tiene 1 `stop_id`
distinto**, en las 8 particiones `date=` reales que existen (`2026-08-14` a
`2026-08-21`, ~1144 filas/día): confirmado con
`SELECT date, COUNT(DISTINCT stop_id) FROM transporte_publico_emt_por_parada_hora
GROUP BY date` → `n_stops = 1` en las 8 fechas. No es un bug de esta
consulta (agrupa correctamente) — la ingesta real de este dataset, a fecha
de esta sesión, solo captura una parada. `fetch_paradas_emt()` devuelve, por
tanto, `[{"stop_id": "71"}]` real, no una lista vacía ni un error.

**Hallazgo real 2 — Gold de `aparcamientos` está completamente vacío** (0
objetos reales bajo `aparcamientos_por_parking_hora/` en el bucket Gold,
solo un marcador `_$folder$` sin datos) — un caso más de Gold vacío, además
de los dos ya documentados desde la tarea 063
(`cartelera_cines_estrenos`/`afluencia_lugares`). `fetch_lugares_aparcamientos()`
devuelve `[]` sin ningún error, tal como exige el enunciado de esta tarea
para este tipo de caso.

**Hallazgo real 3 — los tres orígenes Bronze-only nunca se subieron al
bucket Bronze real.** Confirmado con
`aws s3 ls s3://madrono-tfm-dev-bronze-222234418587/`: solo aparecen
prefijos de los 14 datasets con productor en bucle (tarea 032 en adelante);
ninguno de `barrios_distritos_madrid`, `poi_madrid`,
`crtm_red_transporte_madrid` — coherente con sus propios scripts de
`ingesta/capturas/` (`barrios_distritos_madrid.py`, `poi_madrid.py`,
`crtm_red_transporte_madrid.py`), que solo escriben a disco local
(`_write_json`) y **nunca llaman a `BronzeWriter`** (a diferencia de los 14
productores continuos) — son cargas puntuales de referencia, documentadas
como tales desde su propia tarea de captura (p. ej. `barrios_distritos_
madrid.py`: "esto es una carga batch puntual... no una captura periódica").
Los nombres de prefijo que usa `extract.py`
(`barrios_distritos_madrid_distritos`, `barrios_distritos_madrid_barrios`,
`poi_madrid`, `crtm_red_transporte_madrid`) son, por tanto, una **convención
asumida** siguiendo el patrón `<dataset>/fecha=/hora=/*.json` de
`ingesta/capturas/bronze.py` y el nombre que ya usan los ficheros de muestra
commiteados (`ingesta/capturas/samples/*_sample.json`) — no verificada contra
ninguna key real, porque no existe ninguna. Las cuatro funciones devuelven
`[]` sin error contra el S3 real de hoy, exactamente como exige el enunciado
para el caso de un dataset sin datos.

## Enriquecimiento de `:Lugar` con OpenStreetMap (tarea 083)

Los `:Lugar` del grafo vienen de tres fuentes municipales (`poi_madrid`,
`aparcamientos`, `cartelera_cines_estrenos`), ninguna con categoría
estructurada tipo `amenity`, horario de apertura ni accesibilidad.
`ingesta/capturas/enriquecimiento_osm_lugares.py` (ver `ingesta/README.md`)
añade OpenStreetMap (Overpass API, pública, sin API key) como fuente de
**enriquecimiento** de esos `:Lugar` ya existentes — decisión ya fijada por
el enunciado: unir por proximidad geográfica, no crear `:Lugar` nuevos a
partir de OSM (evita duplicar cobertura con `poi_madrid` y mantiene el
número de nodos estable).

- `geo.nearest_within_radius(lat, lon, candidates, radius_m, get_coords)`:
  helper genérico (no específico de OSM) que devuelve el candidato más
  cercano dentro de un radio, o `None` si ninguno cae dentro — construido
  sobre `haversine_m`, ya existente desde la tarea 070.
- `nodos.enrich_lugar_con_osm(lugar, osm_pois, radio_m=30.0)`: si hay un POI
  de OSM a ≤30 m del `:Lugar` (umbral fijado por el enunciado, distinto del
  umbral de 300 m de `proximo_a` — aquí se busca "es el mismo sitio", no
  "está cerca"), añade `osm_id` (`"<osm_type>:<osm_id>"`, mismo formato
  `"<fuente>:<id_origen>"` que ya usa `id` en el resto de labels),
  `osm_amenity` y `osm_opening_hours`. Si varios POIs de OSM caen dentro del
  radio, se queda con el más cercano. Sin match — o sin `ubicacion` en el
  `:Lugar` (p. ej. origen `cartelera_cines_estrenos`) —, el `:Lugar` se
  devuelve sin ninguna propiedad nueva: no se añaden propiedades `null` de
  más a un `:Lugar` sin match real.
- `nodos.enrich_lugares_con_osm(lugares, osm_pois, radio_m=30.0)`: aplica lo
  anterior a la lista completa de `:Lugar` ya construidos por
  `lugares_from_*`.
- `extract.fetch_osm_pois_sample()`: lee la muestra ya normalizada de POIs
  de OSM commiteada en `ingesta/capturas/samples/
  enriquecimiento_osm_lugares_sample.json` (captura real contra Overpass, no
  datos inventados). **No repite la consulta Overpass real en cada carga
  del grafo**: el bounding box completo de Madrid devuelve más de 75.000
  nodos (ver `ingesta/README.md`), y repetir esa consulta cada vez que se
  ejecuta `cargar_grafo.py` no sería un uso responsable de una instancia
  pública gratuita de terceros. Una captura real y completa de POIs de OSM
  subida a Bronze S3 (para que `extract.py` la lea igual que
  `poi_madrid`/`crtm_red_transporte_madrid`) queda como trabajo futuro
  deliberado.
- `cypher.lugar_query` persiste las 3 propiedades opcionales con `node.get(...)`
  (mismo criterio "sin preservar valor anterior" que `nombre`/`tipo`/
  `fuente`, a diferencia de `_UBICACION_SET`). `schema.cypher` las documenta
  como opcionales en el bloque de `:Lugar`.
- `cargar_grafo.py::cargar_grafo()` llama a `enrich_lugares_con_osm` sobre la
  lista de `lugares` justo antes de `loader.load_lugares(lugares)`.

## Cómo se carga (instancia real: AuraDB Free, tareas 080/094)

Ver `grafo/cargar_grafo.py::cargar_grafo()` para el bloque completo (nodos +
`PERTENECE_A`/`UBICADO_EN`/`PROXIMO_A`/`CONECTADO_CON`), no repetido aquí.
Resumen: junta las listas de nodos con ubicación (`estaciones_medida +
paradas_transporte + lugares`) y las pasa a
`relaciones.ubicado_en`/`relaciones.proximo_a` junto con los registros
Bronce crudos de barrios (`extract.fetch_barrios_bronze()`, no los nodos
`:Barrio` ya transformados, ver arriba); las rutas Bronce de
`extract.fetch_paradas_crtm_bronze()` se leen una única vez y se reutilizan
tanto para `nodos.paradas_transporte_from_crtm_bronze` como para
`relaciones.conectado_con`, en ese orden (nodos antes que la relación).

Este mismo bloque, encapsulado, es `grafo/cargar_grafo.py::cargar_grafo()`
(`python3 -m grafo.cargar_grafo` como script). **Ejecutado varias veces
contra la instancia real** (tarea 080, primera carga; tarea 087, Fase A de
`aforos_peatones_bicicletas`; tarea 094, recarga completa) -- ver
`infra/neo4j/README.md`, "Esquema inicial del grafo", para un hallazgo real
de la tarea 094: `infra/neo4j/schema/schema.cypher` (los constraints
`UNIQUE` de los que dependen los `MERGE`) no se había aplicado nunca contra
la instancia real pese a que este documento ya advertía que hacía falta --
una recarga contra el grafo ya poblado, sin esos índices, colgó 3 horas
reales antes de detectarse y corregirse. **Aplicar `schema.cypher` es un
prerrequisito real, no solo documental, antes de cualquier recarga
completa.**

## Tests

`grafo/tests/` (`python3 -m unittest discover -s grafo/tests -t .`, 89
tests a fecha de la tarea 083):

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
- `test_geo.py` (tarea 070): point-in-polygon y Haversine verificados con
  datos reales — el barrio "011" Palacio del fixture commiteado y un punto
  real conocido dentro de él (Palacio Real de Madrid, 40.4180/-3.7143), un
  punto claramente fuera de Madrid (Barcelona) para el caso negativo, y dos
  distancias Haversine con un orden de magnitud conocido (Puerta del Sol -
  Plaza Mayor, ~365 m; Madrid - Barcelona, ~505 km).
- `test_relaciones.py::UbicadoEnTests`/`ProximoATests` (tarea 070): casos de
  `ubicado_en`/`proximo_a` sobre fixtures pequeñas construidas a mano
  (algunas reutilizando los mismos puntos reales de `test_geo.py`), incluido
  el caso "no limita el número de relaciones por nodo" (20 vecinos dentro
  del umbral generan 20 relaciones, no un subconjunto).
- `test_cypher.py`: verifica las sentencias/parámetros generados por las
  funciones `*_query()` (incluidas `ubicado_en_query`/`proximo_a_query`,
  tarea 070, y `conectado_con_query`, tarea 071) por inspección de la
  cadena, y confirma que `Neo4jLoader(...)` falla con `ImportError` (no con
  un error oscuro) si se instancia sin el driver instalado.
- `test_relaciones.py::ConectadoConTests` (tarea 071): usa directamente el
  fixture real `crtm_red_transporte_madrid_sample.json` — número exacto de
  relaciones para la línea 1 de metro (33 paradas → 64), primer par real en
  ambos sentidos, forma mínima del `:ParadaTransporte` de cada extremo, que
  no conecta entre `route_id` distintos, que una ruta con `"stops": []`
  (Cercanías del fixture) no genera nada, y que ordena por `sequence`
  aunque la entrada no venga ordenada.
- `test_extract.py` (tarea 069, 15 tests): mockea `boto3` por completo
  (`FakeAthenaClient`/`FakeS3Client`, inyectados vía el parámetro
  `athena_client`/`s3_client` de cada función de `extract.py`) — sin
  credenciales ni conexión real, verifica el parseo de `get_query_results`
  (incluido el cast de `VarCharValue` a `int`/`float`), los tres estados
  terminales de una consulta (`SUCCEEDED`/`FAILED`/timeout), la forma exacta
  de cada `fetch_*` (columnas `lat`/`lon` planas anidadas en `location`) y
  el caso de lista vacía (Gold sin datos, o ningún objeto bajo un prefijo de
  S3) sin ningún error.
- `test_geo.py::NearestWithinRadiusTests` / `test_nodos.py::EnrichLugaresConOsmTests`
  (tarea 083): usan la muestra real commiteada de POIs de OSM
  (`enriquecimiento_osm_lugares_sample.json`, captura real contra Overpass,
  no coordenadas inventadas) — un `:Lugar` construido con las coordenadas
  exactas de un POI real de la muestra (match, distancia 0), y otro en
  Puerta del Sol (a más de 1 km de cualquier punto de la muestra,
  verificado con `haversine_m`, sin match).

## Relevante para tareas futuras

- **Resuelto por la tarea 070**: `UBICADO_EN` y `PROXIMO_A` ya están
  implementadas (`grafo/geo.py`, ampliación de `relaciones.py`/`cypher.py`/
  `cargar_grafo.py`, ver la sección dedicada arriba).
- **Resuelto por la tarea 071**: `CONECTADO_CON` ya está implementada
  (`relaciones.conectado_con`, `cypher.conectado_con_query`, ampliación de
  `cargar_grafo.py`, ver la sección dedicada arriba). A diferencia de lo que
  suponía la nota anterior de la tarea 070, no hizo falta ampliar
  `extract.py`: `fetch_paradas_crtm_bronze()` ya devuelve los registros
  Bronce **de ruta** sin aplanar (con `stops` en orden de `sequence`,
  confirmado con `test_extract.py::test_crtm_bronze_devuelve_registros_de_
  ruta_sin_transformar`) — es `nodos.paradas_transporte_from_crtm_route_
  bronze` quien aplana a paradas sueltas, no `extract.py`; `relaciones.
  conectado_con` consume directamente esos mismos registros de ruta. Las 4
  relaciones del esquema del grafo (`schema.cypher`) están ahora completas.
  Con `CONECTADO_CON` implementada, `cargar_grafo.py::cargar_grafo()` ya
  cubre las 4 relaciones sin ningún hueco, y desde la tarea 080 se ejecuta
  end-to-end contra la instancia real (ver "Cómo se carga").
  El límite ya conocido desde la tarea 067 (resolución de entidades entre
  fuentes fuera de alcance: `crtm_red_transporte_madrid` y
  `transporte_publico_emt` pueden representar la misma parada física con dos
  nodos `:ParadaTransporte` distintos) sigue aplicando aquí sin cambios:
  `CONECTADO_CON` solo se genera dentro de `crtm_red_transporte_madrid`, así
  que nunca conecta un nodo `crtm_red_transporte_madrid:...` con uno
  `transporte_publico_emt:...` aunque sean la misma parada real — una
  consulta de "ruta más corta" que cruce ambas fuentes tendría que atravesar
  primero un `PROXIMO_A` entre ambos nodos, si la distancia real entre ellos
  cae dentro del umbral de 300 m.
- **Resuelto por la tarea 069**: `extract.py` ya lee Gold real vía Athena y
  Bronze-only real vía S3 — la nota anterior de la tarea 067 ("decidir cómo
  se resuelve el import de `procesamiento/silver_gold/*` para leer Gold/
  Bronze reales desde S3") queda superada por esa vía distinta (Athena, no
  releer Parquet), que era justamente la decisión ya tomada por el
  enunciado de esta tarea.
- ~~El bloqueo real (alta manual de AuraDB Free)~~ **Resuelto** (tarea 080):
  la instancia real existe y `grafo/cargar_grafo.py` ya se ejecuta
  end-to-end contra ella sin cambios en este directorio (tareas
  080/087/094). Lo que quedó escrito en las tareas 067/070/071 —
  `extract.py` y las 4 relaciones del esquema listas — se confirmó correcto
  al ejecutarlo de verdad.
- `relaciones.proximo_a` es `O(n²)` en el número de nodos con ubicación —
  ver la nota de rendimiento en la sección dedicada arriba. No es un
  problema con los volúmenes reales de hoy, pero si una tarea futura amplía
  mucho la captura de algún dataset (p. ej. más paradas EMT, ver más abajo)
  convendría revisar si sigue siendo aceptable antes de ejecutar
  `cargar_grafo.py` contra una instancia real.
- **`transporte_publico_emt_por_parada_hora` Gold solo tiene 1 parada
  distinta** (`stop_id = "71"`). **Investigado (28/8, Prioridad 7 de
  `NEXT_STEPS.md`): no es un límite de la fuente ni un bug de captura, es el
  alcance con el que se construyó el productor.**
  `ingesta/capturas/transporte_publico_madrid.py` consulta el endpoint EMT
  `/v2/transport/busemtmad/stops/{stop_id}/arrives/`, que es **una parada
  por llamada**, y tanto `capture_all()` como `lambda_handler()` usan un
  único `config.stop_id` (por defecto `"71"`, o `$EMT_STOP_ID`) — heredado
  de la muestra puntual de las tareas 003/024. La EMT publica miles de
  paradas; ampliarlo es una **feature nueva** (enumerar `stop_id` — p. ej.
  desde `crtm_red_transporte_madrid` o un endpoint de paradas EMT — y
  recorrerlos respetando el rate-limit de MobilityLabs), no un arreglo.
  `fetch_paradas_emt()` no necesita cambios: empezaría a devolver más filas
  en cuanto la ingesta capture más paradas.
- **`aparcamientos_por_parking_hora` Gold está completamente vacío** (0
  objetos reales, solo un marcador `_$folder$`) — un tercer caso de Gold
  vacío, además de los dos ya conocidos desde la tarea 063
  (`cartelera_cines_estrenos`/`afluencia_lugares`, ambos con el mismo tipo de
  causa: el job Silver→Gold sin `--extra-py-files`). Merece la misma
  investigación que aquellos dos antes de considerar el pipeline de
  `aparcamientos` completo end-to-end — fuera del alcance de esta tarea, que
  solo necesitaba manejar el caso de lista vacía sin error (ya lo hace).
- **Los nombres de prefijo de S3 usados para los tres orígenes Bronze-only
  (`barrios_distritos_madrid_distritos`, `barrios_distritos_madrid_barrios`,
  `poi_madrid`, `crtm_red_transporte_madrid`) son una convención asumida, no
  verificada contra ningún dato real** — ninguno de los tres se ha subido
  nunca al bucket Bronze real (`ingesta/capturas/barrios_distritos_madrid.py`
  /`poi_madrid.py`/`crtm_red_transporte_madrid.py` solo escriben JSON local,
  nunca llaman a `BronzeWriter`, a diferencia de los 14 productores
  continuos). Si una tarea futura decide subir estas cargas de referencia al
  bucket Bronze real (p. ej. añadiendo una llamada a `BronzeWriter` a esos
  tres scripts), debe usar exactamente estos cuatro nombres de dataset para
  que `extract.py` los encuentre sin cambios — o, si elige otros nombres,
  actualizar las cuatro constantes correspondientes en
  `grafo/extract.py::fetch_distritos_bronze`/`fetch_barrios_bronze`/
  `fetch_poi_bronze`/`fetch_paradas_crtm_bronze`.
- **Enriquecimiento de OSM limitado a una muestra de 6 POIs** (tarea 083,
  `extract.fetch_osm_pois_sample`) — solo enriquecerá los `:Lugar` reales
  que caigan a ≤30 m de alguno de esos 6 puntos concretos, prácticamente
  ninguno con los ~381 `:Lugar` reales de la tarea 080. Una captura real y
  completa de POIs de OSM (todo el bounding box de Madrid, no solo una
  muestra de 250 elementos truncados) subida a Bronze S3 —igual que se hizo
  con `poi_madrid` en la tarea 080— es el siguiente paso natural para que
  este enriquecimiento tenga cobertura real; `cargar_grafo.py` no necesitaría
  ningún cambio salvo apuntar `fetch_osm_pois_sample` (o una función
  equivalente que lea de S3) a esos datos completos.
