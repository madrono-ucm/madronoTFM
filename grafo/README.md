# `grafo/` — ETL Gold/Bronze → nodos del grafo Neo4j (tareas 067/069)

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
para las tres fuentes Bronze-only.

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
| `extract.py` | No | Consulta Athena (Gold, tareas 066/068) o lee JSON de S3 (Bronze-only) y devuelve `list[dict]` en el formato que esperan `nodos.py`/`relaciones.py`. Solo depende de `boto3` (tarea 069). |
| `nodos.py` | No | Convierte un registro Gold/Bronze en el `dict` de propiedades de un nodo (`<tipo>_from_<origen>`), y una lista de registros en una lista de nodos deduplicados por `id`/`codigo` (`<tipo>s_from_<origen>`). |
| `relaciones.py` | No | `PERTENECE_A` (Barrio→Distrito) a partir de un nodo `:Barrio` ya construido por `nodos.py`. |
| `cypher.py` | Solo `Neo4jLoader`, de forma perezosa | Traduce esos `dict` a sentencias `MERGE` parametrizadas (funciones `*_query()`, Python puro) y las ejecuta contra una instancia real (`Neo4jLoader`, que hace `from neo4j import GraphDatabase` dentro de `__init__`, no a nivel de módulo). |
| `cargar_grafo.py` | Solo al importar `Neo4jLoader` (perezoso hasta instanciarlo) | Entry point que encadena `extract.py` → `nodos.py`/`relaciones.py` → `cypher.py`. No ejecutado contra ninguna instancia real (tarea 069). |
| `requirements.txt` | — | `neo4j` (solo para `Neo4jLoader`, no instalado en esta EC2) y `boto3` (para `extract.py`, ya instalado). |
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

**`get_query_results` de Athena devuelve todo como texto** (`VarCharValue`),
sea cual sea el tipo real de columna — comportamiento documentado de la
API, no un bug. `extract._cast_athena_value()` los convierte de vuelta a
`int`/`float` según `ResultSetMetadata.ColumnInfo[].Type`, imprescindible
para que `lat`/`lon` lleguen a `Neo4jLoader` como números (el `point({...})`
de Cypher que construye `cypher.py` los necesita numéricos, no como cadena).

### Verificado contra datos reales de esta cuenta (`eu-west-1`, `222234418587`) al escribir este módulo

Las 11 funciones se han ejecutado una vez contra Athena/S3 reales (con las
credenciales de esta EC2, sin asumir ningún rol) para validar el SQL antes de
darlo por bueno — no simulado:

| Función | Filas reales |
|---|---|
| `fetch_estaciones_trafico` | 4678 |
| `fetch_estaciones_calidad_aire` | 23 |
| `fetch_estaciones_ruido` | 31 |
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

## Cómo se cargaría (cuando exista una instancia real)

```python
from grafo import extract, nodos, relaciones
from grafo.cypher import Neo4jLoader

# NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD / NEO4J_DATABASE:
# ver infra/neo4j/README.md, "Cómo se conectaría el proyecto" -- no
# redefinidas aquí.
with Neo4jLoader(uri, username, password, database) as loader:
    barrio_nodes = nodos.barrios_from_bronze(extract.fetch_barrios_bronze())

    loader.load_distritos(nodos.distritos_from_bronze(extract.fetch_distritos_bronze()))
    loader.load_barrios(barrio_nodes)
    loader.load_estaciones_medida(nodos.estaciones_medida_from_trafico_gold(extract.fetch_estaciones_trafico()))
    loader.load_estaciones_medida(nodos.estaciones_medida_from_calidad_aire_gold(extract.fetch_estaciones_calidad_aire()))
    loader.load_estaciones_medida(nodos.estaciones_medida_from_ruido_gold(extract.fetch_estaciones_ruido()))
    loader.load_paradas_transporte(nodos.paradas_transporte_from_transporte_publico_emt_gold(extract.fetch_paradas_emt()))
    loader.load_paradas_transporte(nodos.paradas_transporte_from_bicimad_gold(extract.fetch_paradas_bicimad()))
    loader.load_paradas_transporte(nodos.paradas_transporte_from_crtm_bronze(extract.fetch_paradas_crtm_bronze()))
    loader.load_lugares(nodos.lugares_from_poi_bronze(extract.fetch_poi_bronze()))
    loader.load_lugares(nodos.lugares_from_aparcamientos_gold(extract.fetch_lugares_aparcamientos()))
    loader.load_lugares(nodos.lugares_from_cartelera_cines_gold(extract.fetch_lugares_cartelera_cines()))

    loader.load_pertenece_a(relaciones.pertenece_a_from_barrios(barrio_nodes))
```

Este mismo bloque, encapsulado, es `grafo/cargar_grafo.py::cargar_grafo()`
(`python3 -m grafo.cargar_grafo` como script). **No se ha ejecutado nunca
contra una instancia real** (bloqueado, ver arriba) — sí se ha ejecutado
`extract.py` contra Athena/S3 reales (ver tabla de arriba), pero no la carga
Cypher completa. Requiere ejecutar antes `infra/neo4j/schema/schema.cypher`
(los constraints `UNIQUE` de los que dependen los `MERGE`).

## Tests

`grafo/tests/` (`python3 -m unittest discover -s grafo/tests -t .`, 46
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
- `test_extract.py` (tarea 069, 15 tests): mockea `boto3` por completo
  (`FakeAthenaClient`/`FakeS3Client`, inyectados vía el parámetro
  `athena_client`/`s3_client` de cada función de `extract.py`) — sin
  credenciales ni conexión real, verifica el parseo de `get_query_results`
  (incluido el cast de `VarCharValue` a `int`/`float`), los tres estados
  terminales de una consulta (`SUCCEEDED`/`FAILED`/timeout), la forma exacta
  de cada `fetch_*` (columnas `lat`/`lon` planas anidadas en `location`) y
  el caso de lista vacía (Gold sin datos, o ningún objeto bajo un prefijo de
  S3) sin ningún error.

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
- **Resuelto por la tarea 069**: `extract.py` ya lee Gold real vía Athena y
  Bronze-only real vía S3 — la nota anterior de la tarea 067 ("decidir cómo
  se resuelve el import de `procesamiento/silver_gold/*` para leer Gold/
  Bronze reales desde S3") queda superada por esa vía distinta (Athena, no
  releer Parquet), que era justamente la decisión ya tomada por el
  enunciado de esta tarea.
- El bloqueo real (alta manual de AuraDB Free) sigue siendo el mismo que
  documentó la tarea 043 — ninguna tarea de ETL puede resolverlo, solo un
  humano completando el flujo de `https://console.neo4j.io`. Con `extract.py`
  ya escrito, la siguiente tarea de grafo con una instancia real disponible
  podría ejecutar `grafo/cargar_grafo.py` end-to-end sin más cambios.
- Las 3 relaciones restantes (`UBICADO_EN`, `PROXIMO_A`, `CONECTADO_CON`)
  son el siguiente trabajo natural sobre este mismo directorio — probablemente
  un `grafo/relaciones.py` ampliado (o módulos nuevos, `grafo/ubicado_en.py`
  etc., si la lógica geométrica lo justifica) más funciones `*_query()`
  adicionales en `cypher.py`. `UBICADO_EN` necesita las geometrías de
  `barrios_distritos_madrid` (ya cargadas por `nodos.py` para
  `:Distrito`/`:Barrio`, pero el polígono en sí — `geometry` — no se ha
  conservado en el `dict` de nodo, solo `codigo`/`nombre`/`distrito_codigo`;
  habrá que decidir si extenderlo o mantener el point-in-polygon en un
  módulo separado con acceso al Bronze crudo). Esas relaciones también
  necesitarán su propia extracción real (p. ej. `PROXIMO_A` sobre las
  ubicaciones que ya devuelve `extract.py`), reutilizable desde este mismo
  módulo.
- **`transporte_publico_emt_por_parada_hora` Gold solo tiene 1 parada
  distinta** (`stop_id = "71"`) en las 8 particiones reales de esta sesión —
  no es un límite de la consulta de esta tarea, es el estado real de la
  ingesta de ese dataset a fecha 2026-08-21. Si una tarea futura amplía la
  captura de EMT a más paradas, `fetch_paradas_emt()` no necesita ningún
  cambio — empezaría a devolver más filas automáticamente.
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
