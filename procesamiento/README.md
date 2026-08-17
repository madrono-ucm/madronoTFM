# `procesamiento/` — Bronze → Silver → Gold (tareas 041, 046, 047, 048, 049, 050, 053, 054, 055, 056, 057, 058 y 059)

Este directorio es el análogo de `ingesta/` para la fase 2 del proyecto
(limpieza/normalización y agregación, ver memoria del TFM, apartados 5.5 y
6.2-6.4): mientras `ingesta/` lleva datos reales de las fuentes de Madrid a
la capa Bronze del lakehouse, `procesamiento/` transforma Bronze en Silver
(datos limpios, normalizados, validados) y Silver en Gold (datos agregados,
listos para consumo analítico/BI o para el grafo de la tarea 043).

La tarea 041 fue un **piloto de un único dataset** (tráfico — el más maduro y
mejor documentado de los 21 productores de `ingesta/`, ver doc/002, doc/035,
doc/037, doc/039): estableció el patrón (estructura de código, motor de
procesamiento, dónde vive la puerta de calidad, cómo se despliega). Las
tareas 046, 047, 048, 049, 050, 053, 054, 055, 056, 057, 058 y 059 replican
ese mismo patrón para un segundo, tercer, cuarto, quinto, sexto, séptimo,
octavo, noveno, décimo, undécimo, duodécimo y decimotercer dataset (`transporte_publico_emt`,
llegadas de autobús de la EMT Madrid, ver doc/003, doc/024; `bicimad`,
estado de estaciones de BiciMAD vía GBFS, ver doc/004; `aparcamientos`,
ocupación de aparcamientos rotacionales, ver doc/005; `calidad_aire`,
lecturas horarias de la red de estaciones de calidad del aire, ver doc/006;
`meteorologia`, lecturas horarias de la red de estaciones meteorológicas,
ver doc/008; `ruido`, contaminación acústica diaria de la Red Fija del
SIVCA, ver doc/007; `aforos_peatones_bicicletas`, conteos horarios de
peatones y bicicletas de la red de estaciones permanentes de aforo, ver
`ingesta/capturas/aforos_peatones_bicicletas_madrid.py`;
`cartelera_cines_estrenos`, cartelera y horarios de cines de Madrid vía
SensaCine, ver doc/023; `agenda_eventos`, agenda de eventos culturales y de
ocio de Madrid -- agenda municipal de datos.madrid.es + agenda turística de
esmadrid.com --, ver `ingesta/capturas/agenda_eventos_madrid.py`;
`bluesky_menciones`, menciones públicas de lugares/distritos de Madrid en
Bluesky -- búsqueda puntual por lugar + barrido programado por distrito,
ambos bajo un mismo campo `mode` --, ver
`ingesta/capturas/bluesky_menciones_madrid.py`; `aemet_prevision_avisos`,
previsión diaria por municipio y avisos meteorológicos vigentes de AEMET
OpenData -- dos formas de dato de un mismo productor, tratadas por separado
de principio a fin --, ver doc/018 y
`ingesta/capturas/aemet_prevision_avisos.py`; `cams_calidad_aire`, previsión
horaria de calidad del aire a 4 días vista de Copernicus CAMS para Madrid --
una rejilla espacial con horizonte de antelación (`leadtime_hour`), no una
medida puntual del instante actual --, ver doc/019, doc/045 y
`ingesta/capturas/cams_calidad_aire_madrid.py`)
— ver "Segundo dataset: `transporte_publico_emt`", "Tercer dataset:
`bicimad`", "Cuarto dataset: `aparcamientos`", "Quinto dataset:
`calidad_aire`", "Sexto dataset: `meteorologia`", "Séptimo dataset: `ruido`",
"Octavo dataset: `aforos_peatones_bicicletas`", "Noveno dataset:
`cartelera_cines_estrenos`", "Décimo dataset: `agenda_eventos`", "Undécimo
dataset: `bluesky_menciones`", "Duodécimo dataset: `aemet_prevision_avisos`"
y "Decimotercer dataset: `cams_calidad_aire`" más abajo para las diferencias
reales frente al piloto. **Los trece siguen siendo solo código e
infraestructura, sin aplicar nada en AWS** — mismo alcance que la tarea 001
con el lakehouse; aplicar (con revisión de plan de por medio) es una tarea
posterior, igual que las tareas 014/015 lo fueron para esa infraestructura
base.

## Motor de procesamiento: AWS Glue (Spark serverless)

Se descarta un clúster Spark persistente (EMR, un Spark standalone en EC2)
por el mismo principio de coste mínimo que ya rige el resto del proyecto
(Lambda + EventBridge Scheduler en vez de servidores de ingesta siempre
encendidos, un bucket S3 por capa sin cómputo asociado). AWS Glue es Spark
*serverless*: se factura por DPU-hora solo mientras un job corre, sin ningún
clúster que mantener encendido entre ejecuciones — encaja con la cadencia
baja de este piloto (horaria/diaria, no continua) sin pagar por un clúster
inactivo la mayor parte del tiempo.

## Estructura de código

```
procesamiento/
  silver_gold/
    trafico/
      geo.py                    # Reproyección EPSG:25830 -> WGS84 (Python puro)
      transform.py               # Bronze -> Silver: normalización + puerta de calidad
      aggregate.py                # Silver -> Gold: agregación por punto/hora
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold)
    transporte_publico_emt/
      transform.py               # Bronze -> Silver: normalización + puerta de calidad (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: agregación por parada/línea/hora
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold)
    bicimad/
      transform.py               # Bronze -> Silver: normalización + puerta de calidad (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: agregación por estación/hora
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold)
    aparcamientos/
      transform.py               # Bronze -> Silver: normalización + puerta de calidad (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: agregación por aparcamiento/hora
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold)
    calidad_aire/
      transform.py               # Bronze -> Silver: normalización + puerta de calidad por contaminante (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: agregación por estación/contaminante/hora
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold)
    meteorologia/
      transform.py               # Bronze -> Silver: pivote ancho->largo + puerta de calidad por magnitud (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: agregación por estación/magnitud/hora
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold)
    ruido/
      transform.py               # Bronze -> Silver: normalización + puerta de calidad (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: resumen diario por estación/periodo + media móvil 7d
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver, particiona solo por fecha)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold, con Window function)
    aforos_peatones_bicicletas/
      transform.py               # Bronze -> Silver: normalización + puerta de calidad por conteo (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: agregación por estación/modo/hora
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold)
    cartelera_cines_estrenos/
      transform.py               # Bronze -> Silver: normalización + puerta de calidad por sesión (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: número de sesiones por película/cine/día
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver, particiona por showtime_datetime)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold)
    agenda_eventos/
      transform.py               # Bronze -> Silver: normalización + puerta de calidad por evento (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: número de eventos por categoría/distrito/día
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver, particiona solo por fecha)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold)
    bluesky_menciones/
      transform.py               # Bronze -> Silver: puerta de calidad + deduplicación de duplicados exactos por lote (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: número de menciones por término/modo/hora
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver, particiona por created_at)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold)
    aemet_prevision_avisos/
      transform.py               # Bronze -> Silver: DOS puertas de calidad independientes, previsión y avisos (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: DOS agregaciones independientes, por municipio/leadtime y por zona/fecha/nivel
      ge_suite.py                  # DOS suites de Great Expectations, una por forma de dato (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver, procesa ambas formas de dato en un único job)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold, idem)
    cams_calidad_aire/
      transform.py               # Bronze -> Silver: puerta de calidad de una previsión con horizonte, por contaminante (sin geo.py, ver más abajo)
      aggregate.py                # Silver -> Gold: valor medio/máximo previsto por contaminante/día que predicen
      ge_suite.py                  # Suite de Great Expectations (requiere pyspark + GX)
      glue_bronze_to_silver.py      # Entry point real del job de Glue (Bronze->Silver, particiona por valid_datetime)
      glue_silver_to_gold.py         # Entry point real del job de Glue (Silver->Gold)
  tests/
    fixtures/trafico_bronze_sample.json
    fixtures/transporte_publico_emt_bronze_sample.json
    fixtures/bicimad_bronze_sample.json
    fixtures/aparcamientos_bronze_sample.json
    fixtures/calidad_aire_bronze_sample.json
    fixtures/meteorologia_bronze_sample.json
    fixtures/ruido_bronze_sample.json
    fixtures/aforos_peatones_bicicletas_bronze_sample.json
    fixtures/cartelera_cines_estrenos_bronze_sample.json
    fixtures/agenda_eventos_bronze_sample.json
    fixtures/bluesky_menciones_bronze_sample.json
    fixtures/aemet_prevision_bronze_sample.json
    fixtures/aemet_avisos_bronze_sample.json
    fixtures/cams_calidad_aire_bronze_sample.json
    test_geo.py
    test_transform.py
    test_aggregate.py
    test_transporte_publico_emt_transform.py
    test_transporte_publico_emt_aggregate.py
    test_bicimad_transform.py
    test_bicimad_aggregate.py
    test_aparcamientos_transform.py
    test_aparcamientos_aggregate.py
    test_calidad_aire_transform.py
    test_calidad_aire_aggregate.py
    test_meteorologia_transform.py
    test_meteorologia_aggregate.py
    test_ruido_transform.py
    test_ruido_aggregate.py
    test_aforos_peatones_bicicletas_transform.py
    test_aforos_peatones_bicicletas_aggregate.py
    test_cartelera_cines_estrenos_transform.py
    test_cartelera_cines_estrenos_aggregate.py
    test_agenda_eventos_transform.py
    test_agenda_eventos_aggregate.py
    test_bluesky_menciones_transform.py
    test_bluesky_menciones_aggregate.py
    test_aemet_prevision_avisos_transform.py
    test_aemet_prevision_avisos_aggregate.py
    test_cams_calidad_aire_transform.py
    test_cams_calidad_aire_aggregate.py
```

Precedente directo: `ingesta/capturas/` + `ingesta/tests/` (un paquete por
tipo de trabajo, tests como paquete hermano, fixtures pequeñas versionadas
en el repo). Aquí se añade un nivel más (`silver_gold/<dataset>/`) porque,
a diferencia de un productor de ingesta (una fuente → un módulo), cada
dataset de esta fase tiene dos transformaciones (Bronze→Silver,
Silver→Gold) y varios ficheros de apoyo (geo, calidad) que conviene agrupar
por dataset en vez de aplanar todo en un único módulo `trafico.py`.

## Por qué Python puro para la lógica, y PySpark solo en el job de Glue

**Decisión clave de esta tarea**, la que hace posible probar la lógica sin
un clúster Spark real: `geo.py`, `transform.py` y `aggregate.py` son Python
puro (solo `stdlib`, sin `pyspark`/`pandas`/`great_expectations` como
dependencia de import) y expresan la lógica de negocio operando sobre
`dict`/`list` en memoria, no sobre un DataFrame de Spark. Los jobs de Glue
reales (`glue_bronze_to_silver.py`, `glue_silver_to_gold.py`) son la capa
fina que adapta esa lógica a Spark: leen de S3, aplican las funciones puras
(vía `rdd.mapPartitions` en Bronze→Silver, o expresiones nativas de
`DataFrame.groupBy`/`agg` en Silver→Gold — ver más abajo por qué no es lo
mismo en los dos casos) y escriben el resultado.

Esto no es solo preferencia de estilo: es lo que permite que la lógica de
negocio (fórmulas de reproyección, rangos de la puerta de calidad, campos
de la agregación) tenga **tests unitarios reales, ejecutados en esta EC2 de
desarrollo**, en un proyecto donde instalar Spark/Great Expectations
localmente no es viable (ver "Qué no se ha podido ejecutar en este
entorno" más abajo). El enunciado de la tarea autorizaba explícitamente
esta vía ("verifica con pandas/estructuras en memoria si evitas levantar
una sesión Spark real en los tests"); aquí se ha ido un paso más allá de
`pandas` y se ha optado directamente por estructuras nativas de Python
(`dict`/`list`), sin ninguna dependencia nueva en absoluto.

### Reproyección sin `pyproj`

`geo.py` reproyecta `location.x`/`location.y` (ETRS89/UTM huso 30N,
EPSG:25830 — ver doc/002) a lat/lon (WGS84) con las **fórmulas cerradas de
Snyder** (USGS, "Map Projections – A Working Manual", 1987) implementadas
directamente en Python, en vez de `pyproj` (binding sobre la librería
nativa PROJ). Para un huso UTM fijo, estas fórmulas dan precisión
sub-milimétrica (verificado en `tests/test_geo.py` con una prueba de
round-trip: proyectar un punto conocido de Madrid a UTM con la fórmula
directa y volver con la inversa recupera el original con error < 1e-8°) sin
añadir una dependencia binaria compilada — el mismo tipo de dependencia que
ya causó fricción de despliegue real en este proyecto con `netCDF4`
(doc/019, doc/032: hizo falta una Lambda Layer construida con CodeBuild/
manylinux porque esta EC2 no puede compilarla). Evitarla aquí significa que
el job Bronze→Silver no necesita ningún módulo Python adicional para
reproyectar (a diferencia de la puerta de calidad, que sí instala Great
Expectations en tiempo de job — ver más abajo).

## Transformación Bronze → Silver (`transform.py`)

Por cada registro de `trafico` (esquema de `ingesta/capturas/trafico_madrid.py`,
ver `ingesta/README.md`):

1. **Puerta de calidad** (`validate_record`): una lista de motivos de
   rechazo (vacía = válido). Un registro con algún motivo **no llega a
   Silver**. Reglas aplicadas (rangos de plausibilidad, no cotas oficiales
   publicadas por el Ayuntamiento — el catálogo de datos.madrid.es no
   documenta, p.ej., el rango exacto de `nivelServicio`):
   - `point_id` no nulo.
   - `measured_at`/`ingested_at` parseables y *timezone-aware* (ya en hora
     de Madrid desde las tareas 034-039).
   - `location.x`/`location.y` presentes y, tras reproyectar, dentro de un
     bounding box laxo de la Comunidad de Madrid (39.8°-41.2°N,
     4.6°-3.0°O) — atrapa coordenadas ausentes, corruptas o de otro
     huso/hemisferio sin exigir precisión de posición.
   - `intensity_vph` ∈ [0, 20000], `occupancy_pct`/`load_pct` ∈ [0, 100],
     `service_level` ∈ [0, 10], `saturation_intensity_vph` ≥ 0 (cuando
     están presentes; ausentes se aceptan como `null`, igual que Bronze).
   - `has_error` debe ser `false` (`error_code == "N"`): un sensor que
     reporta error propio no tiene lecturas fiables — se descarta en vez de
     dejar pasar valores basura a Silver.
2. **Normalización** (`to_silver_record`, solo sobre registros ya
   validados):
   - Reproyección: añade `location.lat`/`location.lon` (WGS84), conserva
     `location.x`/`location.y` originales para trazabilidad.
   - Magnitudes en bruto conservadas tal cual (`intensity_vph`,
     `occupancy_pct`, `load_pct`, `service_level`,
     `saturation_intensity_vph`).
   - Magnitudes normalizadas a una escala 0-1 **comparable entre puntos de
     medida distintos**: `occupancy_ratio`/`load_ratio` (porcentaje / 100)
     y, sobre todo, `intensity_ratio` = `intensity_vph` /
     `saturation_intensity_vph` — un mismo `intensity_vph` no es comparable
     entre una avenida de 6 carriles y una calle de 1 solo carril sin
     relativizarlo a la intensidad de saturación propia de cada punto;
     dividir por 100 sería un error para esta magnitud (no es un
     porcentaje).
   - `processed_at`: instante en que el job procesó el registro (distinto
     de `measured_at`/`ingested_at`, que vienen de Bronze).

Los registros rechazados no se escriben en ningún sitio en este piloto (ver
"Registros rechazados" más abajo) — solo se cuentan/loguean.

## Transformación Silver → Gold (`aggregate.py`)

Agregación por **`(point_id, fecha, hora)`**, no por distrito. Se ha
considerado cruzar con `barrios_distritos_madrid` (tarea 010) para agregar
por distrito, pero exigiría resolver qué distrito contiene cada punto de
tráfico (`point-in-polygon` contra las geometrías de barrios) — exactamente
el tipo de relación espacial que la tarea 043 (grafo Neo4j) va a modelar de
forma explícita y reutilizable; anticiparlo aquí con una heurística ad-hoc
(bounding box, vecino más cercano) duplicaría ese trabajo con peor
información. Para un piloto de una sola fuente, agregar por punto de medida
ya reduce el volumen de Silver (una fila cada ~5 min por sensor) a una fila
por hora sin perder resolución espacial — y es la agregación mínima que
cualquier consumidor de Gold necesitaría de todos modos antes de, más
adelante, volver a agregar por distrito.

Cada fila de Gold agrega todas las lecturas de un punto dentro de una hora
natural (derivada de `measured_at`, ya en hora de Madrid): `samples_count`,
`avg`/`max`/`min_intensity_vph`, `avg_occupancy_ratio`, `avg_load_ratio`,
`avg_intensity_ratio`, `avg_service_level`, `first`/`last_measured_at`, y
`lat`/`lon` (constante por punto).

`aggregate.py` (Python puro, probado en `tests/test_aggregate.py`) es la
**fuente de verdad documental y de test** del esquema/semántica de Gold —
qué campos existen y cómo se calculan. El job real
(`glue_silver_to_gold.py`) **no llama a `aggregate.py` en tiempo de
ejecución**: una agregación correcta a través de múltiples particiones/
ficheros de Silver necesita las primitivas nativas de reduce distribuido de
Spark (`DataFrame.groupBy(...).agg(F.avg(...), ...)`), no un
`mapPartitions` fila a fila (que sí basta en Bronze→Silver, donde cada fila
se transforma de forma independiente sin combinarse con otras). Las
expresiones de Spark de `glue_silver_to_gold.py` están escritas para
producir exactamente el mismo esquema que `aggregate.aggregate_silver_to_gold`;
un cambio en una debe reflejarse en la otra (documentado también en el
docstring de ambos módulos).

## Segundo dataset: `transporte_publico_emt` (tarea 046)

Replica el patrón de `trafico` (mismos ficheros, mismo motor Glue, mismo
criterio de GX-como-observabilidad-no-filtro) sobre las llegadas de autobús
de la EMT Madrid (`ingesta/capturas/transporte_publico_madrid.py`, ver
doc/003 y doc/024). Tres diferencias reales frente al piloto, cada una
documentada también en el docstring del módulo correspondiente:

- **Sin `geo.py`**: `normalize_record` ya entrega `location.lat`/`location.lon`
  en WGS84 (coordenadas GeoJSON de la propia API MobilityLabs) — no hace
  falta ninguna reproyección, así que este subpaquete no tiene ningún
  fichero `geo.py`.
- **No existe `measured_at`**: la API MobilityLabs es un servicio de tiempo
  real que en cada llamada devuelve la estimación de espera *vigente en ese
  instante* (`estimate_arrive_sec`, segundos) — no hay una "hora de medida"
  distinta de la hora de captura. `ingested_at` hace de equivalente exacto
  de `measured_at` en la puerta de calidad y en la clave de agregación de
  Gold (ver `transform.py`/`aggregate.py`).
- **`location` es la posición del autobús, no de la parada**: cambia en
  cada muestra (el autobús se mueve), a diferencia de tráfico donde el
  sensor tiene una posición fija. Por eso Gold de este dataset **no
  incluye `lat`/`lon`** — agregar la posición del autobús no tendría el
  mismo significado que agregar la posición fija de un punto de medida (ver
  `aggregate.py`).

La puerta de calidad (`transform.validate_record`) exige `stop_id`/`line`/
`ingested_at` no nulos, `estimate_arrive_sec` en un rango de plausibilidad
laxo (0-120 minutos, igual de no-oficial que los rangos de tráfico — la API
no publica ningún máximo documentado) y `distance_bus_m` no negativo, y
descarta cualquier registro que arrastre claves propias de la respuesta de
login/error de la API (`accessToken`/`code`/`description`) — una señal de
que un payload de autenticación se coló en Bronze en vez de una llegada
normalizada, en vez de una llegada real.

Gold agrega por **`(stop_id, line, fecha, hora)`**, no solo por `stop_id`:
una parada suele dar servicio a varias líneas con frecuencias muy distintas,
mezclarlas en una sola media no tendría sentido.

## Tercer dataset: `bicimad` (tarea 047)

Replica el patrón sobre el estado de las estaciones de BiciMAD
(`ingesta/capturas/bicimad.py`, feed GBFS público, ver doc/004). Igual que
`transporte_publico_emt`, **sin `geo.py`**: el feed GBFS ya entrega
`location.lat`/`location.lon` en WGS84, no hace falta reproyección.

A diferencia de ambos datasets anteriores, aquí la puerta de calidad
(`transform.validate_record`) incluye una comprobación de **consistencia
entre contadores**: `bikes_available + bikes_disabled <= docks_total` y
`docks_available + docks_disabled <= docks_total`. El enunciado de la tarea
planteaba una igualdad exacta como posibilidad, pero se optó por `<=` (no
`==`) tras contrastar con los datos reales de
`ingesta/capturas/samples/bicimad_sample.json`: la suma de contadores de una
estación no agota su capacidad porque las bicis alquiladas en ese instante
(fuera de cualquier estación) no aparecen en ningún contador — la
discrepancia observada es sistemática y normal, no un error de datos. Se
descarta también cualquier registro con `is_installed = false` (estación
retirada de la red/en mantenimiento, sin contadores fiables).

Como en tráfico, `to_silver_record` calcula una magnitud normalizada
comparable entre estaciones de capacidades distintas: `occupancy_ratio` =
`bikes_available / docks_total`. Gold agrega por **`(station_id, fecha,
hora)`** — a diferencia de `transporte_publico_emt`, una estación de BiciMAD
sí tiene una ubicación fija (no es la posición de un vehículo en
movimiento), así que Gold sí incluye `lat`/`lon` (mismo criterio que
tráfico) además de `avg_bikes_available`/`avg_bikes_disabled`/
`avg_docks_available`/`avg_docks_disabled`/`avg_occupancy_ratio`.

## Cuarto dataset: `aparcamientos` (tarea 048)

Replica el patrón sobre la ocupación de aparcamientos públicos rotacionales
de Madrid (`ingesta/capturas/aparcamientos_madrid.py`, servicio SOAP de
datos.madrid.es, ver doc/005). Igual que `transporte_publico_emt`/`bicimad`,
**sin `geo.py`**: `normalize_record` ya entrega `location.lat`/`location.lon`
en WGS84 (coordenadas del propio servicio SOAP), no hace falta reproyección.

**Diferencia real frente a los tres datasets anteriores**: compartir la
ocupación en tiempo real es voluntaria para cada aparcamiento (ver doc/005),
así que `measured_at`/`free_spaces`/`total_spaces` pueden venir a `null` de
forma independiente en un mismo registro Bronze. Se decidió explícitamente
**no descartar** esos registros en `transform.validate_record` — pasan a
Silver con los campos numéricos a `null` — en vez de tratarlos como datos
corruptos: son aparcamientos reales que simplemente no comparten su
ocupación en ese instante, y descartarlos ocultaría que la cobertura de este
dataset es parcial por diseño de la fuente, no por un fallo de captura.
`transform.validate_record` solo rechaza combinaciones imposibles/corruptas:
`free_spaces`/`total_spaces` negativos, o `free_spaces > total_spaces`
cuando ambos están presentes.

Esa misma decisión se propaga a `aggregate.py`: los registros sin
`measured_at` (sin instante de medida, no hay hora a la que asignarlos) se
excluyen de la agregación horaria, pero sin usar `ingested_at` como
sustituto (a diferencia de `transporte_publico_emt`, aquí sí existe un
instante de medida real cuando la fuente lo comparte, y aproximarlo por la
hora de captura introduciría un desfase innecesario). Gold agrega por
**`(parking_id, fecha, hora)`** (un aparcamiento, como una estación de
BiciMAD, tiene ubicación fija, así que Gold sí incluye `lat`/`lon`):
`samples_count`, `avg_free_spaces` y `avg_occupancy_ratio` (media de
`free_spaces / total_spaces` solo sobre las muestras donde ambos estaban
disponibles) y `total_spaces` (primer valor no nulo observado, capacidad
constante en la práctica).

`glue_bronze_to_silver.py` de este dataset difiere del resto en un detalle:
como `measured_at` puede ser `null`, esas filas se particionan bajo
`fecha=__sin_medida__/hora=__sin_medida__` en vez de perderse (siguen siendo
consultables para auditoría de cobertura); `glue_silver_to_gold.py` filtra
esa partición antes de agregar, igual que `aggregate.py` las excluye.

## Quinto dataset: `calidad_aire` (tarea 049)

Replica el patrón sobre las lecturas horarias de la red de estaciones de
calidad del aire de Madrid (`ingesta/capturas/calidad_aire_madrid.py`, ver
doc/006). Igual que `transporte_publico_emt`/`bicimad`/`aparcamientos`,
**sin `geo.py`**: `normalize_record` ya entrega `location.lat`/`location.lon`
en WGS84 (coordenadas del CSV de metadatos de estaciones
`212629-0-estaciones-control-aire`), no hace falta reproyección.

**Diferencia real frente a los cuatro datasets anteriores**: cada registro
va etiquetado con un contaminante (`pollutant`, la abreviatura del Anexo II
del PDF "Intérprete de ficheros de calidad del aire" -- `"NO2"`, `"PM10"`,
`"O3"`...) con su propia unidad y escala típica, así que un único rango de
plausibilidad para todos no distinguiría un NO2 corrupto de un CO válido.
`transform.PLAUSIBLE_MAX_BY_POLLUTANT` da una cota superior laxa (no un
límite legal de calidad del aire, que son medias en ventanas de tiempo
largas -- 1h/8h/24h/anual, no un tope instantáneo) por cada contaminante que
puede devolver el feed en tiempo real; un contaminante fuera de esa tabla
(no debería ocurrir) solo se rechaza si es negativo, no por rango. El
enunciado de la tarea pedía además confirmar si la fuente ya excluye las
lecturas horarias marcadas como no válidas (`"N"` en las columnas
`V01`..`V24` del JSON crudo) antes de llegar a Bronze: se confirmó que sí --
`calidad_aire_madrid.normalize_record` usa `_latest_valid_hour`, que solo
considera horas con código `"V"` y descarta el registro entero (ni siquiera
llega a Bronze) si no tiene ninguna lectura válida ese día. Por eso el
esquema Bronze de este dataset no contiene ningún campo `V01`..`V24` y
`transform.validate_record` no necesita, ni podría, repetir ese filtro --
documentado en el docstring del módulo para que no parezca una omisión.

Gold agrega por **`(station_id, pollutant, fecha, hora)`**, no solo por
estación y hora: una misma estación reporta varios contaminantes a la vez, y
mezclarlos en un único agregado por estación+hora produciría una media sin
significado (un NO2 y un CO promediados juntos). Cada fila agrega
`samples_count`, `avg`/`max`/`min_value`, `first`/`last_measured_at` y
conserva `unit`/`pollutant_name`/`magnitude_code` para legibilidad, además
de `lat`/`lon` (una estación, como un aparcamiento o una estación de
BiciMAD, tiene ubicación fija).

## Sexto dataset: `meteorologia` (tarea 050)

Replica el patrón sobre las lecturas horarias de la red de estaciones
meteorológicas de Madrid (`ingesta/capturas/meteorologia_madrid.py`, ver
doc/008). Igual que `transporte_publico_emt`/`bicimad`/`aparcamientos`/
`calidad_aire`, **sin `geo.py`**: `normalize_station_record` ya entrega
`location.lat`/`location.lon` en WGS84 (coordenadas del CSV de metadatos
"Estaciones de control" de datos.madrid.es), no hace falta reproyección.

**Diferencia real frente a `calidad_aire`** (que usa el mismo backend
"bdca"): aunque el enunciado apuntaba a un esquema parecido, Bronze de este
dataset es **ancho**, no largo -- `meteorologia_madrid.normalize_station_record`
agrega deliberadamente todas las magnitudes de una estación (hasta 8:
`temperature_c`, `humidity_pct`, `wind_speed_ms`, `wind_direction_deg`,
`pressure_mb`, `solar_radiation_wm2`, `uv_radiation_mwm2`,
`precipitation_lm2`) en un único registro Bronze, en vez de un registro por
estación+magnitud como `calidad_aire` (el objetivo original de la tarea 008
pedía explícitamente temperatura/humedad/viento/precipitación como campos de
un mismo registro). `transform.py` pivota de ancho a largo en el propio paso
Bronze->Silver (`bronze_to_silver` puede producir hasta 8 registros Silver
por cada registro Bronze, uno por magnitud presente), para que Silver/Gold
queden en el mismo formato "largo por magnitud" que el resto del patrón. No
todas las estaciones miden todas las magnitudes -- un campo de magnitud
ausente en Bronze es `null`, no un error, y se omite en silencio (no genera
ningún registro Silver ni ninguna entrada de rechazo).

La puerta de calidad tiene dos niveles: `validate_record` (a nivel de
estación+instante: `station_id`/`measured_at`/`ingested_at` no nulos,
timestamps timezone-aware) rechaza el registro Bronze entero -- ninguna
magnitud llega a Silver si fallan estas comprobaciones, porque no hay
estación/instante al que atribuirlas; `validate_magnitude_value` (a nivel de
magnitud individual, rango de plausibilidad por magnitud vía
`transform.PLAUSIBLE_RANGE_BY_MAGNITUDE`, con mínimo Y máximo -- a
diferencia de `calidad_aire`, donde el mínimo siempre es 0) rechaza **solo
esa magnitud**: un sensor de temperatura estropeado no debe tirar también la
humedad o el viento válidos de la misma estación. Este es el primer dataset
del patrón donde una parte de un registro Bronze puede rechazarse sin
rechazar el registro completo.

Gold agrega por **`(station_id, magnitude, fecha, hora)`** (mismo criterio
de clave de tres componentes que `calidad_aire`, por la misma razón: una
estación reporta varias magnitudes a la vez, mezclarlas en un único agregado
por estación+hora no tendría sentido). Cada fila agrega `samples_count`,
`avg`/`max`/`min_value`, `first`/`last_measured_at` y `lat`/`lon`/
`altitude_m` (una estación tiene ubicación fija; `altitude_m` es un campo
propio de este dataset, ausente en el resto -- la red de estaciones
meteorológicas publica la altitud de cada emplazamiento en su catálogo).

## Séptimo dataset: `ruido` (tarea 053)

Replica el patrón sobre la contaminación acústica de la Red Fija del SIVCA
de Madrid (`ingesta/capturas/ruido_madrid.py`, ver doc/007). Igual que
`transporte_publico_emt`/`bicimad`/`aparcamientos`/`calidad_aire`/
`meteorologia`, **sin `geo.py`**: `normalize_record` ya entrega
`location.lat`/`location.lon` en WGS84 (catálogo de estaciones acústicas de
datos.madrid.es), no hace falta reproyección. `location.altitude_m` también
viene resuelto, mismo campo que `meteorologia`.

**Diferencia real frente a los seis datasets anteriores: granularidad
diaria, no horaria**. La Red Fija del SIVCA no publica un feed en tiempo
real -- solo un agregado diario por estación y periodo horario (`D`iurno,
`E`vespertino, `N`octurno, `T`otal), con LAeq y los percentiles
L1/L10/L50/L90/L99 (ver el docstring de `ingesta/capturas/ruido_madrid.py`).
No hay ningún campo de hora que agregar, así que este dataset **no** sigue
el patrón `(id, fecha, hora)` del resto: Silver se particiona solo por
`fecha` (sin `hora`) y Gold agrupa por **`(station_id, period,
measured_date)`**, la clave natural de la fuente. La puerta de calidad usa
un único rango de plausibilidad en dB (`transform.PLAUSIBLE_DB_RANGE =
(20.0, 120.0)`) para los seis campos numéricos, no una tabla por etiqueta
como `calidad_aire`/`meteorologia` -- todos representan niveles sonoros en
la misma unidad, a diferencia de un contaminante o una magnitud
meteorológica. Un registro sin `laeq_db` (columna `LAeq` vacía en el CSV de
origen) se rechaza entero ("descarta periodos sin dato", pedido por el
enunciado); los percentiles pueden ser `null` de forma independiente sin
rechazar el registro.

**Decisión de agregación Silver → Gold**: el enunciado pedía decidir con
criterio propio qué aporta Gold a esta granularidad diaria, sin forzar una
agregación horaria que la fuente no soporta. Un simple paso a través no
añadiría ningún cálculo nuevo, así que se optó por una **media móvil de 7
días naturales de LAeq** (`laeq_rolling_7d_avg_db`/`laeq_rolling_7d_days`,
por cada `(station_id, period)`), calculada con una ventana de calendario
(día actual − 6 días hasta día actual, no "últimas 7 lecturas") para que un
hueco de fin de semana/festivo (la fuente no publica esos días) reduzca
`laeq_rolling_7d_days` en vez de desplazar la ventana. En el job de Glue se
implementa con `Window.partitionBy("station_id", "period").orderBy(...).rangeBetween(-6, 0)`
sobre una columna auxiliar de días desde época (`date_epoch_days`), no con
`rowsBetween`, por la misma razón de ventana de calendario. Se documenta
también, a propósito, una imprecisión física conocida y aceptada: tanto el
`avg_laeq_db` diario como la media móvil de 7 días usan una media aritmética
simple de valores en dB, no el promedio energéticamente correcto (que
requeriría revertir a presión sonora lineal antes de promediar) -- mismo
criterio de simplicidad que el resto del patrón, documentado en el docstring
de `aggregate.py` como pendiente si una tarea futura necesita precisión
acústica exacta.

## Octavo dataset: `aforos_peatones_bicicletas` (tarea 054)

Replica el patrón sobre los conteos horarios de la red de estaciones
permanentes de aforo de peatones y bicicletas de Madrid (tecnología de
visión artificial Data From Sky, `ingesta/capturas/
aforos_peatones_bicicletas_madrid.py`). Igual que
`transporte_publico_emt`/`bicimad`/`aparcamientos`/`calidad_aire`/
`meteorologia`/`ruido`, **sin `geo.py`**: `normalize_record` ya entrega
`location.lat`/`location.lon` en WGS84 (convertidas a partir del formato
"agrupado por puntos" del CSV de origen, mismo criterio que `ruido`), no
hace falta ninguna reproyección.

**Diferencia real frente al resto del patrón: dos redes de estaciones
físicamente distintas, colapsadas en un único campo `count`.** Peatones y
bicicletas se miden en estaciones distintas (identificadores `PERM_PEA##` /
`PERM_BICI##`, ver docstring del módulo de ingesta, "Dos redes de
estaciones distintas, no una sola con dos columnas"), así que cada registro
Bronze trae dos campos de conteo (`pedestrian_count`/`bicycle_count`) pero
solo uno relleno según `mode`. `transform.to_silver_record` colapsa ambos en
un único campo `count` (el que corresponde al `mode` del registro), mismo
criterio que `calidad_aire`/`meteorologia` (un único campo cuya
interpretación depende de una etiqueta del propio registro -- `pollutant`/
`magnitude` allí, `mode` aquí, solo dos valores fijos en vez de un catálogo
abierto) en vez de conservar dos columnas donde una siempre es `null`.

La puerta de calidad (`transform.validate_record`) exige `station_id`,
`mode` (debe ser `"peatones"` o `"bicicletas"`, ver
`transform.COUNT_FIELD_BY_MODE`), `measured_at`/`ingested_at`
timezone-aware, y el campo de conteo correspondiente al `mode` del registro
no nulo y no negativo -- a diferencia de `aparcamientos` (donde compartir la
ocupación en tiempo real es voluntaria y un `null` es un estado válido y
esperado), aquí un conteo ausente se trata como dato incompleto y el
registro se descarta entero ("descarta estaciones/horas sin dato", pedido
por el enunciado): no hay ninguna señal en la fuente de que un conteo
ausente sea un estado legítimo de una estación de aforo permanente.

Gold agrega por **`(station_id, mode, fecha, hora)`** (mismo criterio de
clave de tres componentes que `calidad_aire`/`meteorologia`, por la misma
razón: incluir `mode` en la clave documenta explícitamente que un conteo
solo tiene sentido dentro del mismo modo). Cada fila agrega
`samples_count`, `total_count` (suma -- la magnitud principal de este
dataset, ya que la fuente publica como mucho una fila por estación+hora, a
diferencia de una magnitud continua como `avg_intensity_vph` en `trafico`
donde promediar tiene más sentido que sumar), `avg`/`max`/`min_count`,
`first`/`last_measured_at`, y `lat`/`lon` (una estación de aforo tiene
ubicación fija, mismo criterio que `bicimad`/`aparcamientos`/`calidad_aire`/
`meteorologia`), además de `district_code`/`district`/`address`/
`address_notes` conservados para legibilidad (mismo criterio que `unit`/
`pollutant_name` en `calidad_aire`).

## Noveno dataset: `cartelera_cines_estrenos` (tarea 055)

Replica la estructura de código del patrón sobre la cartelera y horarios de
cines de Madrid (`ingesta/capturas/cartelera_cines_madrid.py`, agregador
SensaCine para Cinesa y Yelmo, ver doc/023). **Sin `geo.py`**, pero por un
motivo distinto al resto de datasets ya extendidos (que no lo necesitan
porque su fuente ya entrega WGS84): el esquema de este dataset no tiene
ninguna coordenada en absoluto -- ni la ubicación de un cine forma parte de
los campos capturados.

**Diferencia real frente a los ocho datasets anteriores: no es una serie
temporal de medidas, es un catálogo de sesiones de cine.** Los ocho
datasets anteriores miden una magnitud numérica repetidamente en el tiempo
(intensidad, ocupación, un contaminante, un conteo...); aquí cada fila de
Silver es un hecho discreto y único -- una sesión de cine concreta
(película + cine + horario), identificada por `showtime_id` -- no una
medida que tenga sentido promediar. Por eso ni la puerta de calidad ni la
agregación de Gold siguen el patrón numérico del resto (ver
`transform.py`/`aggregate.py` para el razonamiento completo).

**Bronze mezcla dos tipos de registro bajo el mismo `DATASET_NAME`
(`"cartelera_cines_estrenos"`), y este subpaquete solo procesa uno**:
sesiones concretas (`normalize_showtime`: película + cine + horario +
identificador de sesión) y estrenos semanales (`normalize_premiere`:
`record_type == "estreno_semana"`, película + fecha de estreno, sin cine ni
horario -- una lista nacional de estrenos, no desglosada por cine). El
enunciado de la tarea exige explícitamente "título de la película, cine,
horario de sesión" como campos clave de la puerta de calidad, lo que solo
tiene sentido para el primer tipo; `transform.validate_record` rechaza
cualquier registro de estreno semanal con el motivo
`"not_a_screening_session"` en vez de forzarlo en el mismo esquema. Los
estrenos semanales quedan fuera del alcance de este subpaquete -- si una
tarea futura quiere tratarlos como su propia entidad, el criterio a seguir
es un dataset/tabla Silver/Gold aparte, no este mismo esquema de sesiones.

**Aviso importante, descubierto en esta sesión**: el único escritor
programado de Bronze de este dataset hoy es `lambda_handler`
(`ingesta/capturas/cartelera_cines_madrid.py`), y envuelve **únicamente
`sweep_premieres`** -- no hay ningún schedule que escriba sesiones
(`fetch_cinema_showtimes` es solo bajo demanda, pensado para un futuro
servicio conversacional, sin handler Lambda propio). Confirmado en
`doc/033-conectar-lambda-layer-verificar.md`: la única invocación real
registrada de este dataset escribió 6 registros, los 6 de tipo
`estreno_semana`. Con el estado actual de `ingesta/`, esta puerta de
calidad rechazaría el 100% de los lotes reales de Bronze capturados hasta
ahora -- no hay todavía ningún escritor programado que produzca sesiones.
No se ha corregido aquí (fuera de alcance: esta tarea es solo
`procesamiento/`); queda como bloqueante real para una tarea futura, ver
"Relevante para tareas futuras" más abajo.

La puerta de calidad también descarta sesiones cuyo horario ya ha pasado en
el momento de la captura (`showtime_datetime < ingested_at`, motivo
`"showtime_already_passed"`, pedido explícitamente por el enunciado): una
cartelera es, por construcción, una lista de sesiones *futuras* respecto al
momento en que se consulta.

**Decisión de agregación Silver → Gold**: el enunciado sugería "número de
sesiones por película/día, o por cine/día" como alternativas; se decidió
incluir **ambas** dimensiones en la misma clave --
`(movie_url, cinema_id, fecha)` (`movie_url`, no `movie_title`, como
identificador estable de la película: la URL de la ficha en SensaCine no
cambia, un título como texto libre en teoría sí podría colisionar) -- en
vez de elegir solo una, para que un consumidor de Gold pueda obtener
cualquiera de las dos vistas (sumando `sessions_count` por `movie_url` o
por `cinema_id`) sin perder información en la propia agregación; perder
cualquiera de las dos dimensiones haría irreversible la otra vista. Cada
fila agrega `samples_count` (filas Silver, incluye reingestas) y
`sessions_count` (número de `showtime_id` **distintos** -- la magnitud
principal de este dataset, no reingestas contadas como sesiones nuevas),
`first`/`last_showtime_datetime`, y `language_versions` (lista ordenada de
versiones de idioma distintas disponibles ese día en ese cine para esa
película -- p.ej. detectar si hay doblada y V.O.S.E.), además de
`movie_title`/`chain`/`cinema_name`/`address`/`postal_code`/`locality`
conservados para legibilidad.

## Décimo dataset: `agenda_eventos` (tarea 056)

Replica la estructura de código del patrón sobre la agenda de eventos
culturales y de ocio de Madrid (`ingesta/capturas/agenda_eventos_madrid.py`,
dos fuentes combinadas: agenda municipal de datos.madrid.es y agenda
turística de esmadrid.com, distinguidas por el campo `source`). **Sin
`geo.py`**, pero por el mismo motivo que la mayoría del patrón (a diferencia
de `cartelera_cines_estrenos`, que no tiene ninguna coordenada en absoluto):
`normalize_municipal_event`/`normalize_esmadrid_event` ya entregan
`location.lat`/`location.lon` en WGS84 para ambas fuentes.

**Diferencia real frente al resto del patrón: como `cartelera_cines_estrenos`,
no es una serie temporal de medidas, es un catálogo de eventos.** Cada fila
de Silver es un hecho discreto -- un evento concreto, identificado por
`event_id` -- no una magnitud numérica repetida en el tiempo. La puerta de
calidad (`transform.validate_record`) exige los campos clave que pide el
enunciado (`title`, `start_datetime` parseable, `source` en el catálogo
cerrado de dos valores conocidos), más `event_id` (clave natural
imprescindible para poder deduplicar reingestas en `aggregate.py`, mismo
papel que `showtime_id` en `cartelera_cines_estrenos`) y `captured_at`/
`ingested_at` timezone-aware.

**Segunda diferencia: dos fuentes con huecos de esquema distintos, sin que
ninguna sea "la correcta".** La agenda municipal siempre resuelve
`district`/`neighborhood` desde su propio catálogo; la agenda de esMadrid
**nunca** los publica (el XML de origen no trae esa columna). `district`/
`neighborhood` no forman parte de la puerta de calidad -- exigirlos
descartaría sistemáticamente el 100% de una de las dos fuentes.
`start_datetime` también difiere de formato entre fuentes: el dato
municipal trae un `datetime` completo sin zona horaria explícita (ya en
hora de Madrid); esMadrid solo trae la **fecha** del primer rango del
evento, sin hora (la hora real, cuando existe, queda en `schedule_text`
como texto libre -- ver la "Simplificación deliberada" ya documentada en el
docstring de `ingesta/capturas/agenda_eventos_madrid.py`).
`validate_record` solo exige que `start_datetime` sea parseable
(`datetime.fromisoformat` acepta ambos formatos), no que tenga hora ni que
sea timezone-aware.

**Tercera diferencia, explícita frente a `cartelera_cines_estrenos`: no se
descartan eventos "ya pasados" respecto a la captura.** Una sesión de cine
es un instante puntual futuro por construcción de la fuente; un evento de
esta agenda puede ser una exposición de varios meses cuyo `start_datetime`
ya quedó atrás en el momento de la captura pero que sigue vigente (evento
real de muestra: "25 años del Museo de San Isidro...", inicio 2026-07-21,
capturado el 2026-08-15). Comparar `start_datetime < captured_at` aquí
descartaría eventos genuinamente en curso, así que esta puerta de calidad,
a propósito, no reproduce esa regla de `cartelera_cines_estrenos`.

**Decisión de agregación Silver → Gold**: el enunciado sugería "por
barrio/distrito y día, o por categoría y día" como alternativas -- mismo
patrón de dos sugerencias que ya resolvió `cartelera_cines_estrenos`
incluyendo ambas dimensiones en la misma clave. Se agrupa por
**`(category, district, fecha)`**, con `fecha` derivada del día en que el
evento **empieza** (no el día de captura, mismo criterio que
`showtime_datetime` en `cartelera_cines_estrenos`), para poder responder
tanto "¿cuántos eventos de tal categoría hay hoy?" como "¿cuántos eventos
hay hoy en tal distrito?" sin perder información en la propia agregación.
Se usa `district`, no `neighborhood` (barrio): como esMadrid nunca publica
ninguno de los dos, una granularidad más fina que distrito fragmentaría aún
más una dimensión que ya es parcial por diseño de una de las dos fuentes.
Cruzar `lat`/`lon` con `barrios_distritos_madrid` (point-in-polygon) para
rellenar el distrito que falta en esMadrid queda fuera de alcance -- mismo
razonamiento que la tarea 041 ya documentó para `trafico`: es el tipo de
relación espacial que la tarea 043 (grafo Neo4j) modelará de forma
explícita y reutilizable, no una heurística ad-hoc de esta tarea.
`category`/`district` ausentes se agrupan bajo un sentinela
(`"__sin_categoria__"`/`"__sin_distrito__"`) en vez de descartarse de la
agregación -- mismo criterio que `aparcamientos.aggregate` con
`fecha=__sin_medida__` (tarea 048): un evento sin categoría o sin distrito
conocido sigue siendo un evento real y contable.

Cada fila de Gold agrega `samples_count` (filas Silver, incluye
reingestas), `events_count` (número de `event_id` **distintos** -- la
magnitud principal de este dataset), `free_events_count` (eventos distintos
con `free = true`, una pregunta habitual de un consumidor de una agenda
cultural), `sources` (lista ordenada de `source` distintos presentes en el
bucket, para poder distinguir un `__sin_distrito__` "porque esMadrid no
publica distrito" de uno "porque faltó ese dato en un evento municipal
concreto") y `first`/`last_start_datetime`.

`glue_bronze_to_silver.py` de este dataset particiona Silver **solo por
`fecha`** (sin `hora`), derivada con `substring(start_datetime, 1, 10)` en
vez de `to_date(...)`: mismo motivo que `ruido` (tarea 053) -- una de las
dos fuentes no publica ninguna hora de celebración, y forzar una hora
inventada (p.ej. "00" por defecto del parseo) sería engañoso; el recorte de
texto funciona igual para ambos formatos de origen porque los dos siempre
empiezan por `YYYY-MM-DD`.

## Undécimo dataset: `bluesky_menciones` (tarea 057)

Replica la estructura de código del patrón sobre las menciones públicas de
lugares/distritos de Madrid en Bluesky
(`ingesta/capturas/bluesky_menciones_madrid.py`, dos modos combinados bajo
un campo `mode`: `"bajo_demanda"` -- búsqueda puntual de un lugar, pensada
para el asistente conversacional -- y `"distrito_sweep"` -- barrido general
por distrito + términos de evento, pensado para un productor programado
cada hora). **Sin `geo.py`**: Bluesky no publica ninguna coordenada del
post (a diferencia de la mayoría del patrón, ni siquiera hace falta
reproyectar nada porque no hay ninguna posición geográfica en absoluto,
mismo motivo que `cartelera_cines_estrenos`).

**Diferencia real frente al resto del patrón: texto libre, no una medida
numérica ni un catálogo de hechos con clave natural fuerte.** Los diez
datasets anteriores son series temporales de una magnitud numérica o
catálogos de hechos discretos (`showtime_id`, `event_id`). Este dataset son
publicaciones de texto libre -- no hay ninguna magnitud que tenga un "rango
plausible", así que la puerta de calidad (`transform.validate_record`) se
centra en integridad estructural (`mode` en el catálogo cerrado de dos
valores, `match_term`, `text` no vacío, `post_hash`, `created_at`/
`captured_at` timezone-aware), tal como pedía el enunciado.

**A diferencia de `cartelera_cines_estrenos` (que rechazaba por completo uno
de los dos tipos de registro que mezclaba Bronze), aquí los dos `mode` son
datos legítimos.** El enunciado de la tarea 057 describe ambos modos como
parte del mismo dataset, con `mode` como campo a conservar y a usar como
dimensión de agregación ("separado por mode"), no como filtro de exclusión.

**Puerta de calidad, segunda parte: duplicados exactos dentro del mismo
lote.** El enunciado pide explícitamente descartar "contenido vacío o
duplicados exactos". El contenido vacío (`text` vacío o solo espacios) se
detecta por registro, igual que el resto de reglas. Los duplicados exactos,
en cambio, no se pueden detectar mirando un único registro -- hace falta
comparar contra el resto del lote. `ingesta/capturas/bluesky_menciones_madrid.py`
ya anticipó este problema: `post_hash` (SHA-256 truncado del texto) existe
precisamente como "clave de deduplicación barata entre términos de búsqueda
solapados" (ver docstring de ese módulo, sección "Privacidad") -- un mismo
post real puede coincidir con más de un término de búsqueda del mismo
barrido (p.ej. un post sobre un concierto puede coincidir tanto con la
búsqueda de su distrito como con el término de evento "concierto"). Por eso
`transform.bronze_to_silver` (no `validate_record`, que solo ve un registro
a la vez) descarta, dentro del mismo lote, cualquier registro cuyo
`post_hash` ya se haya visto, con el motivo `"duplicate_exact_content"` --
una desviación deliberada del resto del patrón (donde `validate_record`
basta porque cada regla es puramente por registro), documentada en detalle
en el docstring de `transform.py` para que no se confunda con un descuido.
Esto no deduplica entre lotes/ejecuciones distintas -- esa deduplicación la
sigue haciendo `aggregate.py`, contando `post_hash` distintos.

**Decisión de agregación Silver → Gold: `(mode, match_term, fecha, hora)`.**
El enunciado pedía "conteo de menciones por lugar/distrito y periodo
(día/hora, según la cadencia real del productor) separado por mode". Se
eligió granularidad horaria, no solo diaria: a diferencia de `ruido`/
`agenda_eventos` (agregación diaria porque su fuente no tiene ninguna
resolución horaria real), cada post de Bluesky trae un `created_at` con
resolución de segundos, y `search_district_sweep` está pensado para un
productor programado cada hora -- la misma cadencia que ya usan la mayoría
de datasets del patrón. El periodo se deriva de `created_at` (cuándo se
escribió el post), no de `ingested_at` (cuándo corrió el barrido): la
búsqueda de Bluesky no está acotada a "solo lo último", así que un lote
puede mezclar posts de días distintos, y la pregunta que tiene sentido
responder es "cuándo se habló de este lugar", no "cuándo se ejecutó el
scraper" -- mismo criterio que `cartelera_cines_estrenos`/`agenda_eventos`
usaron con `showtime_datetime`/`start_datetime` en vez de `ingested_at`.

Cada fila de Gold agrega `samples_count` (filas Silver, incluye reingestas
entre lotes distintos), `mentions_count` (número de `post_hash`
**distintos** -- la magnitud principal de este dataset), `langs` (lista
ordenada de idiomas distintos presentes), `total_like_count`/
`total_repost_count`/`total_reply_count`/`total_quote_count` (sumas de los
contadores públicos que Bluesky ya expone por post -- no es ningún análisis
de sentimiento ni clasificación de texto, fuera de alcance de esta tarea,
solo una suma numérica de campos que ya existen en Silver, dando una señal
barata de "cuánta atención" recibió un lugar/término) y
`first`/`last_created_at`.

**Timestamps de Bluesky en formato `Z` (UTC), no `+02:00`.** A diferencia
del resto de timestamps del patrón (generados por `now_madrid()`, siempre
con offset explícito), `created_at`/`indexed_at` los genera la propia API de
Bluesky con el sufijo `Z`. Esto importa porque **AWS Glue 4.0 ejecuta Python
3.10**, y `datetime.fromisoformat` solo entiende `Z` directamente desde
Python 3.11 -- en 3.10 lanzaría `ValueError` y rechazaría por error el 100%
de los registros reales. `transform._parse_iso` normaliza `Z` a `+00:00`
antes de parsear (ver docstring de `transform.py`) precisamente para
evitarlo -- primer caso del patrón donde esto importa, porque es el primer
dataset cuyos timestamps clave no los genera `ingesta/capturas/bronze.py`.

## Duodécimo dataset: `aemet_prevision_avisos` (tarea 058)

Replica la estructura de código del patrón sobre la previsión diaria y los
avisos meteorológicos vigentes de AEMET OpenData
(`ingesta/capturas/aemet_prevision_avisos.py`, ver doc/018). **Sin
`geo.py`**: ninguna de las dos formas de dato trae ninguna coordenada
(previsión: municipio por código INE; avisos: zona por nombre de área CCAA).

**Diferencia real frente a todo el resto del patrón: dos formas de dato
completamente distintas bajo un mismo productor, sin ningún campo en
común.** Los once datasets anteriores, aunque varíen entre serie temporal
numérica (`trafico`...) y catálogo de hechos discretos
(`cartelera_cines_estrenos`, `agenda_eventos`) o incluso dos `mode` bajo un
mismo esquema (`bluesky_menciones`), siempre comparten un único esquema
Silver por dataset. Aquí `ingesta/capturas/aemet_prevision_avisos.py` ya
escribe, en producción, **dos** Bronze datasets con nombre propio
(`DATASET_PREDICCION = "aemet_prevision"`, `DATASET_AVISOS = "aemet_avisos"`)
y esquemas que no comparten ni un solo campo de negocio: la previsión trae
`municipio_code`/`valid_date`/magnitudes meteorológicas; los avisos traen
`identifier`/`zone`/`level`/CAP. El enunciado de esta tarea pedía
explícitamente no forzar un único esquema de agregación para ambas, así que
este subpaquete trata ambas formas de dato como dos flujos independientes
de principio a fin: dos puertas de calidad
(`validate_prevision_record`/`validate_aviso_record`), dos normalizadores,
dos agregaciones (`aggregate_prevision_silver_to_gold`/
`aggregate_avisos_silver_to_gold`), dos suites de Great Expectations y dos
pares de prefijos S3 -- pero **un único** rol IAM y **un único** par de
jobs de Glue (Bronze→Silver, Silver→Gold, "job de Glue x2" tal como pedía
el enunciado, no cuatro), porque ambas formas comparten productor,
credencial (`AEMET_API_KEY`) y cadencia real de scheduling.

**Desviación deliberada de la sugerencia de prefijo único del enunciado.**
El enunciado sugería acotar el rol IAM a un único prefijo
`aemet_prevision_avisos/*` en las tres capas. Eso no es viable: los nombres
de dataset Bronze ya están fijados en producción por
`ingesta/capturas/aemet_prevision_avisos.py` (`"aemet_prevision"`/
`"aemet_avisos"`, usados tal cual por `BronzeWriter`), así que un rol
acotado al prefijo combinado que sugería el enunciado no tendría permiso
para leer ningún dato Bronze real. Silver mantiene la misma separación de
prefijos que Bronze ya tiene fijada (`silver/aemet_prevision/*`,
`silver/aemet_avisos/*`); Gold usa nombres propios por agregación
(`gold/aemet_prevision_por_municipio_leadtime/*`,
`gold/aemet_avisos_por_zona_fecha_nivel/*`). El subpaquete de
`procesamiento/` sí se llama `aemet_prevision_avisos` (agrupa el código de
ambas formas, mismo productor/enunciado) -- la desviación es solo en los
prefijos S3 reales, documentada con detalle en el docstring de
`transform.py` y en `infra/terraform/glue.tf`.

**Previsión: puerta de calidad.** `validate_prevision_record` exige,
siguiendo el enunciado: `municipio_code` no nulo, `valid_date` parseable y
no ya pasada respecto a `ingested_at` (`valid_date < ingested_at.date()` se
rechaza con `"valid_date_already_passed"`; el mismo día, `leadtime_days ==
0`, sí es válido -- es un dato legítimo y frecuente, la previsión "de hoy"),
y rangos plausibles de `temperature_max_c`/`temperature_min_c` (`[-20, 50]`,
mismo rango que `meteorologia.PLAUSIBLE_RANGE_BY_MAGNITUDE["temperature_c"]`)
y `precipitation_probability_pct` (`[0, 100]`, rango físico exacto). Otros
campos (`sky_state`, `humidity_*`, `wind_*`, `uv_max`) no forman parte de la
puerta de calidad -- el enunciado no los pide como clave ni tienen un rango
definido aquí, y `ingesta/README.md` ya documenta que algunos (p.ej.
`wind_gust_max_kmh`) son legítimamente `null` en días sin dato, incluso con
datos reales.

**Silver normaliza tipos numéricos a `float`; Bronze no.**
`ingesta/README.md` documenta a propósito que Bronze conserva los tipos tal
como los publica AEMET (`precipitation_probability_pct`/`wind_speed_kmh`
llegan como *string*, p.ej. `"75"`, por "honestidad sobre cómo lo publica la
fuente"). Silver, en cambio, sigue el mismo criterio que
`meteorologia`/`calidad_aire` (`value: float`): `transform._to_float`
normaliza todos los campos numéricos a `float` (acepta `str`/`int`/`float`,
`None` si no es parseable), para que `aggregate.py` -- y cualquier
consumidor de Gold -- no tenga que adivinar el tipo campo a campo.

**Avisos: puerta de calidad.** `validate_aviso_record` exige `identifier`
(clave natural para deduplicar reingestas en `aggregate.py`), `zone`,
`phenomenon` y `effective_from` parseable (necesario para poder agrupar por
día en `aggregate.py`) no nulos, y `level` dentro del catálogo cerrado de
AEMET (`{"amarillo", "naranja", "rojo"}`, documentado en la página de ayuda
oficial de AEMET citada en `ingesta/capturas/aemet_prevision_avisos.py`).

**Agregación de previsión: `(municipio_code, leadtime_days)`, valores
medios/máximos por horizonte.** `leadtime_days` (`valid_date -
ingested_at.date()`, en días) agrupa previsiones de días de calendario
distintos capturadas en momentos distintos bajo el mismo horizonte de
antelación -- responde "en general, ¿qué pinta tiene la previsión a 1 día
vista?", no "qué pasó un día concreto" (eso ya lo responde Silver fila a
fila, sin agregar). No se guarda como columna aparte en Silver, se deriva en
`aggregate.py`/el job de Glue -- mismo criterio que `bluesky_menciones`/
`cartelera_cines_estrenos` derivan `hour`/`fecha` de un timestamp en vez de
duplicarlo. Cada fila de Gold agrega `avg`/`max` de `temperature_max_c` y
`avg`/`min` de `temperature_min_c` (el máximo del máximo y el mínimo del
mínimo son los extremos que importan de cada magnitud) y `avg`/`max` de
`precipitation_probability_pct` -- exactamente "valores medios/máximos"
sobre las mismas dos magnitudes que ya acota la puerta de calidad.

**Agregación de avisos: `(zone, fecha, level)`, conteo de avisos activos.**
`fecha` es el día de `effective_from` (cuándo empieza a estar vigente el
aviso), no el de `ingested_at` -- mismo criterio que
`cartelera_cines_estrenos`/`agenda_eventos`/`bluesky_menciones`: la pregunta
que responde esta agregación es "qué avisos estuvieron activos tal día en
tal zona", no "cuándo corrió el barrido". `alerts_count` (número de
`identifier` **distintos**) es la magnitud principal -- "conteo de avisos
activos" tal como pedía el enunciado --, separada de `samples_count` (filas
Silver, incluye reingestas del mismo aviso vigente capturado varias veces
mientras sigue activo).

## Decimotercer dataset: `cams_calidad_aire` (tarea 059)

Replica la estructura de código del patrón sobre la previsión horaria de
calidad del aire a 4 días vista de Copernicus CAMS para Madrid
(`ingesta/capturas/cams_calidad_aire_madrid.py`, ver doc/019 y doc/045).
**Sin `geo.py`**: `normalize_forecast_file` ya entrega el punto de rejilla
más cercano a Madrid en WGS84 (tras corregir la convención `[0, 360)` de
longitud del NetCDF real, ver doc/045) -- no hace falta ninguna
reproyección.

**Diferencia real frente al resto del patrón: previsión con horizonte, no
medida del instante actual.** A diferencia de `calidad_aire` (tarea 049,
mediciones en tiempo real de la red de estaciones de Madrid), cada registro
de este dataset es un valor *previsto* para un instante futuro
(`valid_datetime`), calculado a partir de una corrida de modelo diaria
concreta (`forecast_issued_at`) con un horizonte de antelación en horas
(`leadtime_hour`). Es la misma naturaleza de dato que
`aemet_prevision_avisos` (tarea 058) -- ambas tareas se diseñaron con un
criterio deliberadamente similar para previsión, tal como pedía el
enunciado de esta tarea --, con dos diferencias: el horizonte se mide en
horas, no en días, y no hay ningún "ya pasado" que rechazar (`leadtime_hour`
sale siempre `>= 0` por construcción de la petición a la API de CAMS, así
que `valid_datetime` nunca es anterior a `forecast_issued_at`; no hace falta
repetir aquí una regla que la fuente ya garantiza -- a diferencia de
`aemet_prevision_avisos.validate_prevision_record`, que sí necesita rechazar
`valid_date_already_passed` porque AEMET puede reemitir una previsión
"vieja" en un lote).

**Puerta de calidad.** `validate_record` exige, tal como pide el enunciado:
`pollutant`/`pollutant_code` no nulos, `valid_datetime`/`forecast_issued_at`
parseables y *timezone-aware*, `leadtime_hour` no nulo y no negativo, y
`value` no nulo dentro de un rango plausible por contaminante
(`PLAUSIBLE_MAX_BY_POLLUTANT`, mismo criterio y mismos órdenes de magnitud
que `calidad_aire.PLAUSIBLE_MAX_BY_POLLUTANT` -- cota laxa para atrapar solo
valores corruptos, no un límite legal de calidad del aire --, pero definida
como su propia tabla en vez de importada: este dataset produce las
etiquetas `NO2`/`NO`/`SO2`/`O3`/`PM2.5`/`PM10`/`polvo`, un conjunto distinto
al de `calidad_aire`, y acoplar ambos subpaquetes por una tabla que podría
evolucionar de forma independiente no aporta nada). `is_mock` (presente en
Bronze) no se propaga a Silver -- dato de procedencia de la captura, no una
dimensión de negocio, mismo criterio que `aemet_prevision_avisos`.

**Agregación decidida por el enunciado, no evaluada aquí: `(pollutant,
fecha_validez)`, valor medio/máximo previsto ese día.** `fecha_validez` se
deriva de `valid_datetime` (el día que predice la fila, no se guarda como
columna aparte en Silver) -- deliberadamente **no** es el horizonte de
antelación (`leadtime_days`, como sí usa `aemet_prevision_avisos` para su
agregación de previsión): esta tarea pide "valor medio/máximo previsto ese
día para ese contaminante", una pregunta distinta a "qué tan certera es la
previsión a N horas vista" (que `leadtime_hours`, lista de horizontes
distintos presentes en cada bucket, conserva sin ser la clave de
agrupación). Cada fila de Gold agrega `samples_count`, `avg_value`/
`max_value` y `first`/`last_forecast_issued_at` (qué corridas contribuyeron
a esa fila).

## Great Expectations: dónde corre, y por qué no es el único filtro

**Decisión (pregunta explícita del enunciado): corre dentro del propio job
de Glue** (`glue_bronze_to_silver.py`), en el mismo `SparkSession`,
inmediatamente después de escribir la puerta de calidad de `transform.py` y
antes de persistir Silver — no como un Glue Job o paso de Step Functions
separado. Razones (desarrolladas en el docstring de `ge_suite.py`):

- El volumen de este piloto (un dataset, ~5 min de cadencia) no justifica
  el coste operativo de una orquestación adicional solo para validar.
- Validar en el mismo `SparkSession` evita una vuelta extra de lectura/
  escritura a S3.
- Las dependencias de GX se instalan igual en tiempo de job vía
  `--additional-python-modules` (parámetro nativo de Glue para paquetes
  puros de PyPI, sin necesidad de una imagen/capa a medida — a diferencia
  de la Lambda Layer de la tarea 032, aquí Glue resuelve la instalación él
  solo) esté el job separado o no, así que separarlo no evita ningún
  problema de empaquetado.

**Great Expectations valida, pero no decide qué filas pasan a Silver** — esa
decisión la toma `transform.validate_record` (Python puro, testeado). GX se
ejecuta *después* del filtro, sobre el Silver ya filtrado, como una capa de
**observabilidad/auditoría**: genera un `ExpectationSuiteValidationResult`
(JSON) que el job escribe junto a la partición de Silver
(`_quality_reports/trafico/`), para poder confirmar más adelante, sin
releer los datos crudos, que un lote de Silver cumplía las expectations
declaradas en el momento en que se procesó. Se ha descartado que GX sea el
único mecanismo de filtrado por dos motivos: (a) la lógica de negocio de la
puerta de calidad necesita poder probarse sin Spark/GX instalados en este
repo, y (b) cada expectation de `ge_suite.py` está anotada con qué regla de
`validate_record` reproduce — la misma regla de negocio expresada dos
veces a propósito (una testable sin GX, otra declarativa y con informe
versionado), no dos fuentes de verdad independientes.

## Qué no se ha podido ejecutar en este entorno

Esta EC2 de desarrollo tiene muy poco disco libre, compartido con el propio
pipeline (ver restricciones de la tarea) — instalar `pyspark` y
`great_expectations` (con su árbol de dependencias: pandas, jsonschema,
marshmallow...) localmente para probarlos de verdad se ha descartado por
riesgo de agotar ese disco compartido, no por falta de intención. En
consecuencia:

- `ge_suite.py`, `glue_bronze_to_silver.py` y `glue_silver_to_gold.py` (de
  **los trece** datasets) importan `pyspark`/`great_expectations`/`awsglue`
  a nivel de módulo y **no se han podido importar ni ejecutar en ninguna de
  las trece sesiones (041/046/047/048/049/050/053/054/055/056/057/058/059)**. Están escritos con el mismo
  cuidado que el resto del proyecto y basados en la API pública documentada
  de Glue/GX (Glue: `awsglue.context.GlueContext`, `awsglue.job.Job`,
  estable desde hace años; GX: `sources.add_or_update_spark`/`Validator`,
  API "Fluent" estable en la serie 0.17-0.18 — versión fijada en
  `var.great_expectations_pip_spec`, `infra/terraform/variables.tf`), pero
  **no verificados por ejecución real**. Antes del primer `terraform apply`
  de esta infraestructura, conviene una prueba de humo en un
  notebook/endpoint de desarrollo de Glue (`aws glue start-job-run` contra
  un lote pequeño, o un Glue Studio Notebook interactivo) para confirmar la
  sintaxis exacta contra la versión real del runtime, antes de dejarlo
  correr contra Bronze de producción.
- Ningún test de este proyecto importa esos módulos por dataset (ver
  `procesamiento/silver_gold/trafico/__init__.py`,
  `procesamiento/silver_gold/transporte_publico_emt/__init__.py`,
  `procesamiento/silver_gold/bicimad/__init__.py`,
  `procesamiento/silver_gold/aparcamientos/__init__.py`,
  `procesamiento/silver_gold/calidad_aire/__init__.py`,
  `procesamiento/silver_gold/meteorologia/__init__.py`,
  `procesamiento/silver_gold/ruido/__init__.py`,
  `procesamiento/silver_gold/aforos_peatones_bicicletas/__init__.py`,
  `procesamiento/silver_gold/cartelera_cines_estrenos/__init__.py`,
  `procesamiento/silver_gold/agenda_eventos/__init__.py`,
  `procesamiento/silver_gold/bluesky_menciones/__init__.py` y
  `procesamiento/silver_gold/aemet_prevision_avisos/__init__.py`, que
  exponen solo `transform`/`aggregate` (y `geo`, solo en tráfico) a
  propósito) — así el resto del paquete sigue siendo importable/testable en
  cualquier entorno sin Spark.
- No se ha procesado ningún dato real de Bronze de ninguno de los doce
  datasets (no hay Glue desplegado todavía): toda la verificación usa
  fixtures construidos a mano —
  `tests/fixtures/trafico_bronze_sample.json` (10 registros, 5 válidos + 5
  que violan cada regla de la puerta de calidad por turnos, incluye el
  punto real de doc/002 para verificar la reproyección),
  `tests/fixtures/transporte_publico_emt_bronze_sample.json` (10 registros,
  mismo criterio 5 válidos + 5 rechazados, con formas reales tomadas de
  `ingesta/capturas/samples/transporte_publico_madrid_sample.json`),
  `tests/fixtures/bicimad_bronze_sample.json` (10 registros: las 5
  estaciones reales de
  `ingesta/capturas/samples/bicimad_sample.json` + 5 que violan cada regla
  de la puerta de calidad por turnos, incluida la consistencia de
  contadores), `tests/fixtures/aparcamientos_bronze_sample.json` (10
  registros: los 5 aparcamientos reales de
  `ingesta/capturas/samples/aparcamientos_madrid_sample.json` + 1 con
  ocupación no compartida en tiempo real (`measured_at`/`free_spaces`/
  `total_spaces` a `null`, válido, ver "Cuarto dataset" arriba) + 4 que
  violan cada regla de rechazo por turnos), `tests/fixtures/calidad_aire_bronze_sample.json`
  (10 registros: las 5 lecturas reales de
  `ingesta/capturas/samples/calidad_aire_madrid_sample.json` -- 2 estaciones,
  4 contaminantes distintos (NOx/NO/NO2/O3) -- + 5 que violan cada regla de
  rechazo por turnos, incluido un valor de NO2 muy por encima de su rango
  plausible pero que sería válido para un contaminante con un rango mayor,
  ver "Quinto dataset" arriba) y `tests/fixtures/meteorologia_bronze_sample.json`
  (10 registros Bronze "anchos": las 5 estaciones reales de
  `ingesta/capturas/samples/meteorologia_madrid_sample.json` -- que expanden
  a 30 registros Silver "largos" -- + 5 que violan cada regla por turnos
  (estación sin id, sin `measured_at`, `measured_at` sin zona horaria, sin
  `ingested_at`, y una estación con la temperatura disparada pero el resto de
  sus magnitudes válidas, para probar el rechazo a nivel de magnitud sin
  perder el resto del registro), ver "Sexto dataset" arriba),
  `tests/fixtures/ruido_bronze_sample.json` (28 registros: las 20 lecturas
  reales de `ingesta/capturas/samples/ruido_madrid_sample.json` -- 5
  estaciones x 4 periodos D/E/N/T -- + 8 que violan cada regla de rechazo
  por turnos, incluido un percentil fuera de rango que no descarta el LAeq
  válido del mismo registro, ver "Séptimo dataset" arriba) y
  `tests/fixtures/aforos_peatones_bicicletas_bronze_sample.json` (13
  registros: 5 lecturas reales de
  `ingesta/capturas/samples/aforos_peatones_bicicletas_madrid_sample.json`
  -- 3 estaciones de peatones + 2 de bicicletas -- + 8 que violan cada
  regla de rechazo por turnos (`station_id` ausente, `mode` inválido,
  `measured_at` ausente/sin zona horaria, `ingested_at` ausente/sin zona
  horaria, conteo ausente y conteo negativo), ver "Octavo dataset" arriba) y
  `tests/fixtures/cartelera_cines_estrenos_bronze_sample.json` (15
  registros: 6 sesiones reales de
  `ingesta/capturas/samples/cartelera_cines_madrid_sample.json` -- 2 cines,
  varias películas -- + 1 registro de estreno semanal real (rechazado por
  `"not_a_screening_session"`) + 8 sintéticos que violan cada regla de
  rechazo por turnos (película/cine/identificador de sesión ausente,
  horario de sesión ausente/sin zona horaria, fecha de captura ausente/sin
  zona horaria, y una sesión cuyo horario ya había pasado en el momento de
  la captura), ver "Noveno dataset" arriba) y
  `tests/fixtures/agenda_eventos_bronze_sample.json` (17 registros: los 10
  eventos reales de
  `ingesta/capturas/samples/agenda_eventos_madrid_sample.json` -- 5
  municipales + 5 de esMadrid, ambas fuentes válidas sin ninguna
  modificación -- + 7 sintéticos que violan cada regla de rechazo por turnos
  (`source` ausente/desconocida, `event_id` ausente, `title` ausente,
  `start_datetime` ausente/no parseable, `captured_at` ausente/sin zona
  horaria), ver "Décimo dataset" arriba) y
  `tests/fixtures/bluesky_menciones_bronze_sample.json` (16 registros: 5
  posts reales de
  `ingesta/capturas/samples/bluesky_menciones_madrid_sample.json` -- 3 del
  modo `bajo_demanda`, 2 del modo `distrito_sweep` -- + 1 duplicado exacto
  de uno de ellos (mismo `post_hash`, otro `match_term`, para probar
  `"duplicate_exact_content"`) + 10 sintéticos que violan cada regla de
  rechazo por turnos (`mode` ausente/inválido, `match_term` ausente,
  `text` vacío, `post_hash` ausente, `created_at` ausente/no parseable/sin
  zona horaria, `captured_at` ausente/sin zona horaria), ver "Undécimo
  dataset" arriba) y `tests/fixtures/aemet_prevision_bronze_sample.json`
  (11 registros: 3 días reales de previsión de
  `ingesta/capturas/samples/aemet_prevision_madrid_sample.json` + 8
  sintéticos que violan cada regla de rechazo por turnos —
  `municipio_code` ausente, `valid_date` ausente/no parseable,
  `captured_at` ausente/sin zona horaria, `valid_date` ya pasada respecto a
  `captured_at`, `temperature_max_c`/`temperature_min_c` fuera de rango,
  `precipitation_probability_pct` fuera de rango) junto con
  `tests/fixtures/aemet_avisos_bronze_sample.json` (8 registros: el único
  aviso real de `ingesta/capturas/samples/aemet_avisos_madrid_sample.json`
  + 7 sintéticos que violan cada regla de rechazo por turnos —
  `identifier`/`zone`/`phenomenon`/`effective_from` ausente, `level`
  inválido, `captured_at` ausente/sin zona horaria), ver "Duodécimo
  dataset" arriba. `AEMET_API_KEY` sigue sin estar disponible como variable
  de entorno en esta EC2 de desarrollo (mismo motivo que las tareas 038/045,
  ver doc/018 y `ingesta/README.md`): se intentó regenerar la muestra en
  esta sesión (`python3 -m ingesta.capturas.aemet_prevision_avisos`) y
  falló explícitamente con el mismo mensaje de `AEMET_API_KEY no está
  configurada` documentado por esas tareas, así que los fixtures de este
  dataset se construyeron a partir de las muestras `is_mock: true` ya
  commiteadas, sin ningún cambio, y
  `tests/fixtures/cams_calidad_aire_bronze_sample.json` (29 registros: los
  16 registros reales (`is_mock: false`) de
  `ingesta/capturas/samples/cams_calidad_aire_madrid_sample.json` -- 4
  contaminantes x 4 `leadtime_hour` (0-3), la misma corrida y el mismo día
  de validez -- + 13 sintéticos que violan cada regla de rechazo por turnos
  (`pollutant`/`pollutant_code` ausente, `valid_datetime`/
  `forecast_issued_at` ausente/no parseable/sin zona horaria, `leadtime_hour`
  ausente/negativo, `captured_at` ausente/sin zona horaria, `value`
  ausente/negativo/fuera de rango plausible para NO2), ver "Decimotercer
  dataset" arriba. A diferencia de `aemet_prevision_avisos`,
  `CAMS_ADS_API_KEY` sí está configurada en el entorno de producción real
  (credenciales y licencia ya aceptadas, ver doc/045) y la muestra
  commiteada ya es un lote real (`is_mock: false`), no simulado -- no hizo
  falta ningún fixture sintético base, solo los sintéticos que violan cada
  regla de rechazo.

## Terraform (`infra/terraform/glue.tf`)

Sin aplicar (ver arriba). Un bloque de recursos por dataset (`trafico`,
tarea 041; `transporte_publico_emt`, tarea 046; `bicimad`, tarea 047;
`aparcamientos`, tarea 048; `calidad_aire`, tarea 049; `meteorologia`, tarea
050; `ruido`, tarea 053; `aforos_peatones_bicicletas`, tarea 054;
`cartelera_cines_estrenos`, tarea 055; `agenda_eventos`, tarea 056;
`bluesky_menciones`, tarea 057; `aemet_prevision_avisos`, tarea 058;
`cams_calidad_aire`, tarea 059), cada uno con su propio rol IAM acotado por
prefijo — no se comparte rol entre datasets, mismo principio de mínimo
privilegio que ya aplicaba `ingesta`. `aemet_prevision_avisos` es la única
excepción parcial: **un** rol IAM y **un** par de jobs de Glue cubren, a
propósito, las dos formas de dato de ese productor (previsión y avisos) en
vez de cuatro jobs — ver "Duodécimo dataset" arriba para el porqué:

- `aws_glue_job.<dataset>_bronze_to_silver` / `<dataset>_silver_to_gold`:
  dos jobs por dataset (uno por transformación, no combinados — para poder
  reintentar/reejecutar cada etapa de forma independiente, p.ej. volver a
  agregar Gold sin releer Bronze). `glue_version = "4.0"`,
  `worker_type = "G.1X"`, `number_of_workers = 2` (mínimo permitido) —
  variables compartidas en `variables.tf` para poder subir esto sin tocar
  `.tf` cuando el volumen crezca.
- `aws_iam_role.glue_trafico` / `glue_transporte_publico_emt` / `glue_bicimad`
  / `glue_aparcamientos` / `glue_calidad_aire` / `glue_meteorologia` /
  `glue_ruido` / `glue_aforos_peatones_bicicletas` /
  `glue_cartelera_cines_estrenos` / `glue_agenda_eventos` /
  `glue_bluesky_menciones` / `glue_aemet_prevision_avisos` /
  `glue_cams_calidad_aire`: la política
  gestionada `AWSGlueServiceRole` (lo que todo job de Glue necesita en su
  propio nombre: API de Glue, logs bajo `/aws-glue/...`) más una política
  propia acotada por prefijo — lectura de `bronze/<dataset>/*`,
  lectura+escritura de `silver/<dataset>/*`, escritura de
  `gold/<tabla_gold>/*`, lectura del script/librería en el bucket de
  artefactos (`aws_s3_bucket.build_artifacts`, reutilizado de la tarea 032
  para los trece datasets en vez de crear un bucket nuevo) y permisos
  acotados sobre el catálogo de Glue de las tablas de cada dataset — ni un
  permiso más. `glue_aemet_prevision_avisos` es la excepción: su política
  acota DOS prefijos Bronze/Silver (`aemet_prevision/*`/`aemet_avisos/*` en
  cada capa) y DOS tablas Gold, no uno de cada — ver "Duodécimo dataset"
  arriba.
- `aws_glue_catalog_database.silver`/`gold` (compartidas entre datasets, una
  base de datos por capa) + `aws_glue_catalog_table.trafico_silver`/
  `trafico_gold`/`transporte_publico_emt_silver`/`transporte_publico_emt_gold`/
  `bicimad_silver`/`bicimad_gold`/`aparcamientos_silver`/`aparcamientos_gold`/
  `calidad_aire_silver`/`calidad_aire_gold`/`meteorologia_silver`/
  `meteorologia_gold`/`ruido_silver`/`ruido_gold`/
  `aforos_peatones_bicicletas_silver`/`aforos_peatones_bicicletas_gold`/
  `cartelera_cines_estrenos_silver`/`cartelera_cines_estrenos_gold`/
  `agenda_eventos_silver`/`agenda_eventos_gold`/
  `bluesky_menciones_silver`/`bluesky_menciones_gold`/
  `aemet_prevision_silver`/`aemet_avisos_silver`/`aemet_prevision_gold`/
  `aemet_avisos_gold` (cuatro tablas, no dos, para `aemet_prevision_avisos`
  — dos formas de dato, ver "Duodécimo dataset" arriba)/
  `cams_calidad_aire_silver`/`cams_calidad_aire_gold`:
  catalogadas para poder consultarlas con Athena sin ningún paso adicional.
  Bronze deliberadamente **no** se cataloga: son lotes JSON crudos sin un
  esquema único garantizado entre los 21 productores, no pensados para
  consultarse vía SQL.
- `data.archive_file.procesamiento_source` (**sin cambios en su
  definición**: ya empaquetaba todo `procesamiento/` salvo `tests/`, así
  que cada subpaquete nuevo, incluido el de la tarea 059, se incluye
  automáticamente) + `aws_s3_object.*` por script de cada dataset, subidos
  al bucket de artefactos con el hash del contenido en la key (mismo patrón
  que `data.archive_file.ingesta_source`/`layer_source_key` de tareas
  anteriores) — un cambio de código sube a una key nueva sin pisar la
  anterior.

`terraform validate` limpio (verificado en las trece tareas, sin backend
real inicializado — `terraform init -backend=false`, tras limpiar
`__pycache__/*.pyc` generados por `python3 -m unittest`, mismo problema
preexistente documentado en doc/046, no introducido por esta tarea);
`terraform fmt -check -diff glue.tf` sin diferencias. No se ha ejecutado
`terraform plan` contra la cuenta real (necesitaría credenciales AWS que
estas tareas no deben usar para aplicar nada).

## Relevante para tareas futuras

- El patrón (fijado por la tarea 041, ya replicado once veces con la
  046/047/048/049/050/053/054/055/056/057/058) para extender Bronze→Silver→Gold a
  más fuentes: un subpaquete `silver_gold/<dataset>/` con `transform.py`
  (Python puro, testable)/`aggregate.py` (idem, de referencia)/`ge_suite.py`
  (GX, ejecutado en Glue)/`glue_*.py` (entry points) — más `geo.py` **solo
  si la fuente necesita reproyectar** (no es parte fija del patrón: ni
  `transporte_publico_emt`, ni `bicimad`, ni `aparcamientos`, ni
  `calidad_aire`, ni `meteorologia`, ni `ruido`, ni
  `aforos_peatones_bicicletas`, ni `cartelera_cines_estrenos` ni
  `agenda_eventos` lo tienen — las primeras siete y la última porque sus
  fuentes ya entregan WGS84, `cartelera_cines_estrenos` porque su esquema no
  tiene ninguna coordenada en absoluto, ver "Segundo dataset"/"Tercer
  dataset"/"Cuarto dataset"/"Quinto dataset"/"Sexto dataset"/"Séptimo
  dataset"/"Octavo dataset"/"Noveno dataset"/"Décimo dataset" arriba) —, más
  un bloque en `glue.tf` con su propio rol IAM acotado por prefijo (no un
  rol compartido entre datasets: mantiene el principio de mínimo privilegio
  ya aplicado en `ingesta`). `cartelera_cines_estrenos` fue el primer
  dataset del patrón que no es una serie temporal de medidas sino un
  catálogo de hechos discretos (sesiones de cine); `agenda_eventos` replica
  ese mismo criterio para un segundo dataset de catálogo (eventos) — si una
  tarea futura añade otro dataset "de catálogo" en vez de "de medida", el
  criterio a replicar es el de `aggregate.py` de cualquiera de los dos:
  agregar un **conteo** de hechos por las dimensiones relevantes, no un
  promedio/suma de ninguna magnitud numérica (no hay ninguna en este tipo de
  fuente).
- Antes de aplicar esta infraestructura: (1) smoke-test de los trece
  `ge_suite.py` contra un Glue Studio Notebook real (ver arriba) —
  `bicimad/ge_suite.py` y `aparcamientos/ge_suite.py` necesitan además
  confirmar que las columnas auxiliares que calculan sus respectivos
  `glue_bronze_to_silver.py` (`bikes_over_capacity`/`docks_over_capacity` y
  `free_spaces_over_total_spaces`) se comportan como se espera contra el
  runtime real de Spark/GX, al no existir una expectation nativa de "suma
  de columnas <= columna" ni de "columna <= columna" (ver docstring de
  ambos `ge_suite.py`); `calidad_aire/ge_suite.py` y `meteorologia/ge_suite.py`
  necesitan confirmar de igual forma sus columnas auxiliares de rango por
  etiqueta (`value_over_plausible_max` en `calidad_aire`;
  `value_below_plausible_min`/`value_over_plausible_max` en `meteorologia`,
  que además tiene mínimo variable, no solo máximo -- ver "Quinto dataset"/
  "Sexto dataset" arriba); `ruido/glue_silver_to_gold.py` necesita confirmar
  contra el runtime real que la ventana `Window.rangeBetween` sobre
  `date_epoch_days` produce la misma media móvil de 7 días que
  `aggregate.py` (ver "Séptimo dataset" arriba) -- a diferencia de las
  columnas auxiliares de GX del resto, esto no es una expectation, sino la
  propia lógica de agregación de Gold; `aforos_peatones_bicicletas/ge_suite.py`
  es el único que no necesita ninguna columna auxiliar (`mode` solo admite
  dos valores fijos, cubierto de forma nativa por
  `expect_column_values_to_be_in_set`, ver "Octavo dataset" arriba);
  `cartelera_cines_estrenos/ge_suite.py` necesita confirmar que
  `expect_column_pair_values_a_to_be_greater_than_b` (comparación
  lexicográfica de dos columnas de texto ISO-8601, no de instantes reales,
  ver docstring de ese módulo) reproduce fielmente el resultado de
  `transform.validate_record`, motivo `"showtime_already_passed"`;
  `agenda_eventos/ge_suite.py` es, como `aforos_peatones_bicicletas`, otro
  que no necesita ninguna columna auxiliar (`source` es un catálogo cerrado
  de dos valores, cubierto de forma nativa por
  `expect_column_values_to_be_in_set`), pero conviene confirmar contra el
  runtime real que `expect_column_values_to_not_be_null("start_datetime")`
  no rechaza por error el formato "solo fecha" de esMadrid (ver "Décimo
  dataset" arriba); las dos suites de `aemet_prevision_avisos/ge_suite.py`
  necesitan la misma confirmación que `cartelera_cines_estrenos` para
  `expect_column_pair_values_a_to_be_greater_than_b` (comparación
  lexicográfica de `valid_date`/`ingested_at` como texto, no de instantes
  reales, ver "Duodécimo dataset" arriba); `cams_calidad_aire/ge_suite.py` es,
  como `calidad_aire`/`meteorologia`, otro que necesita confirmar su columna
  auxiliar de rango por etiqueta (`value_over_plausible_max`, calculada con
  la tabla propia `PLAUSIBLE_MAX_BY_POLLUTANT` de este dataset, no la de
  `calidad_aire` -- ver "Decimotercer dataset" arriba); (2) revisar si `great_expectations==0.18.19` (versión fijada en
  `var.great_expectations_pip_spec`) sigue siendo la última estable de la
  serie 0.18 en el momento de aplicar, y (3) el mismo patrón `terraform
  plan`/`apply` con revisión humana de por medio que ya usaron las tareas
  015/030/039 para la infraestructura ya desplegada.
- La agregación por distrito (en vez de por punto de medida/parada/estación/
  aparcamiento) queda pendiente de la tarea 043 (grafo Neo4j de relaciones
  espaciales) — no se ha aproximado con una heurística ad-hoc a propósito,
  ver "Transformación Silver → Gold" arriba. Aplica igual a
  `transporte_publico_emt`/`bicimad`/`aparcamientos`/`calidad_aire`/
  `meteorologia`/`ruido`/`aforos_peatones_bicicletas`: ni la parada
  (`stop_id`), ni la estación (`station_id`), ni el aparcamiento
  (`parking_id`) se han cruzado con ningún distrito/barrio en ninguna de las
  siete tareas (`ruido` y `aforos_peatones_bicicletas` sí conservan
  `district`/`neighbourhood` o `district`/`district_code` en Silver/Gold,
  tomados de sus respectivos catálogos de origen, pero no los usan como
  clave de agregación). `agenda_eventos` es distinto: sí usa `district` como
  clave de agregación de Gold (ver "Décimo dataset" arriba), pero tampoco es
  un point-in-polygon -- es el distrito que la propia agenda municipal ya
  resuelve en su catálogo de origen (y que la agenda de esMadrid, al no
  publicarlo, deja como sentinela `__sin_distrito__`), no una heurística
  espacial calculada aquí.
- `aemet_prevision_avisos` es el primer dataset del patrón cuyo productor
  escribe, en producción, **más de un dataset Bronze con nombre propio**
  (`aemet_prevision`/`aemet_avisos`, ver "Duodécimo dataset" arriba) en vez
  de un único dataset con un campo discriminador (`mode`, como
  `bluesky_menciones`) o dos tipos de registro mezclados bajo el mismo
  nombre (`cartelera_cines_estrenos`). Si una tarea futura encuentra la
  misma forma (un productor con varios `BronzeWriter(dataset=...)`
  distintos), el criterio a replicar es este: tratar cada forma de dato como
  un flujo Silver/Gold independiente de principio a fin (puerta de calidad,
  normalizador, agregación y prefijos S3 propios), pero compartir un único
  rol IAM y un único par de jobs de Glue si de verdad comparten productor,
  credencial y cadencia — no forzar ni un esquema Silver único ni tampoco
  cuatro jobs de Glue separados. Documentar explícitamente, como se ha hecho
  aquí, cualquier desviación entre el prefijo S3 que sugiera el enunciado de
  la tarea y los nombres de dataset Bronze que la ingesta ya tenga fijados
  en producción — seguir el enunciado al pie de la letra en ese punto
  habría producido un rol IAM sin permisos para leer ningún dato real.
- `aemet_prevision_avisos` (tarea 058) y `cams_calidad_aire` (tarea 059) son
  ahora el precedente del patrón para "previsión con horizonte de
  antelación", deliberadamente diseñados con un criterio similar entre sí
  (ambas tareas lo pedían explícitamente): un valor *previsto* para un
  instante futuro no se rechaza por "ya haber pasado" salvo que la fuente
  pueda reemitir una previsión vieja en un lote nuevo (AEMET sí puede,
  CAMS no -- ver "Decimotercer dataset" arriba para el porqué), y la
  agregación de Gold puede responder a dos preguntas distintas y
  legítimas sobre el mismo tipo de dato: "¿qué tan certera es la previsión a
  N unidades de horizonte vista?" (agrupar por horizonte,
  `aemet_prevision_avisos.aggregate_prevision_silver_to_gold`) o "¿qué se
  predijo en conjunto para tal instante concreto?" (agrupar por el instante
  predicho, `cams_calidad_aire.aggregate_silver_to_gold`). Si una tarea
  futura añade un tercer dataset de previsión, el enunciado de esa tarea
  debería decidir explícitamente cuál de las dos preguntas responde su
  agregación de Gold -- no asumir que una previsión con horizonte siempre se
  agrupa por horizonte.
- El rango de plausibilidad por contaminante de `calidad_aire`
  (`transform.PLAUSIBLE_MAX_BY_POLLUTANT`, ver "Quinto dataset" arriba) es
  la primera pieza de la puerta de calidad del patrón que necesita una
  tabla de constantes en vez de un único rango fijo, porque un mismo campo
  (`value`) representa magnitudes distintas según el valor de otro campo
  (`pollutant`) -- si una tarea futura añade un dataset con la misma forma
  (un valor cuya escala depende de una etiqueta del propio registro), el
  criterio a replicar es este: una tabla `dict[etiqueta, rango]` en
  `transform.py`, con un contaminante/etiqueta ausente de la tabla
  aceptado por defecto (no rechazado por rango, solo por negatividad) en
  vez de fallar o inventar un rango. `meteorologia.PLAUSIBLE_RANGE_BY_MAGNITUDE`
  (ver "Sexto dataset" arriba) extiende ese mismo criterio a rangos con
  mínimo Y máximo (no solo máximo, ya que una temperatura sí puede ser
  negativa) -- si una tarea futura necesita ese mismo patrón, la tabla pasa
  a ser `dict[etiqueta, tuple[mínimo, máximo]]`, no `dict[etiqueta, máximo]`.
- `meteorologia` es el primer dataset del patrón donde Bronze llega en
  formato "ancho" (una fila por estación+instante con varias magnitudes como
  columnas) y hay que pivotarlo a "largo" (una fila por estación+magnitud+
  instante) dentro del propio paso Bronze→Silver, en vez de que la ingesta ya
  lo entregue largo (como `calidad_aire`) -- ver "Sexto dataset" arriba. Es
  también el primer dataset donde una puerta de calidad tiene dos niveles
  (registro completo vs. magnitud individual): un valor fuera de rango en
  una sola magnitud no descarta el resto de magnitudes válidas del mismo
  registro. Si una tarea futura añade un dataset con la misma forma (varias
  magnitudes por registro Bronze, con puerta de calidad por magnitud), el
  criterio a replicar es este: pivotar en `transform.py` (no en
  `aggregate.py` ni en el job de Glue) y separar `validate_record`
  (estación/instante) de una función de validación por magnitud aparte.
- `intensity_ratio` (intensidad / intensidad de saturación) es la magnitud
  pensada para comparar puntos de medida de tráfico con capacidades
  distintas; `occupancy_ratio` (bicis disponibles / capacidad, o plazas
  libres / plazas totales en `aparcamientos`) cumple el mismo papel en
  `bicimad`/`aparcamientos`. `transporte_publico_emt` no tiene ninguna
  magnitud análoga todavía (el tiempo de espera en segundos ya es una
  unidad universal, no necesita normalizarse) — si una tarea futura
  quisiera un "índice de servicio" comparable entre paradas/líneas con
  frecuencias muy distintas, sería la magnitud natural a añadir a
  `aggregate.py` de ese dataset.
- El campo `location` de `transporte_publico_emt` (posición del autobús, no
  de la parada) se conserva en Silver por trazabilidad pero no se agrega en
  Gold ni se usa como ubicación de la parada. Si una tarea futura necesita
  la ubicación real de cada parada (p.ej. para el grafo Neo4j, tarea 043),
  la fuente correcta es el catálogo de paradas de la EMT (fuera del alcance
  de la 003/024/046), no derivarla de las posiciones de autobús observadas.
  `bicimad`/`aparcamientos` no tienen este problema: tanto la estación de
  BiciMAD como el aparcamiento tienen una ubicación fija, por eso su Gold
  sí incluye `lat`/`lon` (mismo criterio que tráfico).
- La comprobación de consistencia entre contadores de `bicimad`
  (`bikes_available + bikes_disabled <= docks_total`, ver "Tercer dataset"
  arriba) usa `<=`, no `==`, porque la fuente real nunca agota la capacidad
  declarada (bicis alquiladas fuera de cualquier estación en ese instante).
  Si una tarea futura quisiera acotar más la puerta de calidad (p.ej. avisar
  si la discrepancia es sospechosamente grande, no solo si supera la
  capacidad), sería una regla adicional sobre esa misma resta, no un cambio
  de `<=` a `==`.
- `aparcamientos` es el primer dataset del patrón donde Silver admite
  registros con campos numéricos a `null` a propósito (ocupación no
  compartida, ver "Cuarto dataset" arriba) — a diferencia del resto, donde
  un registro con datos ausentes se descarta. Si una tarea futura añade un
  quinto dataset con la misma característica (una fuente donde compartir
  parte de los datos es opcional), el criterio a replicar es este, no el de
  `bicimad`/`trafico`/`transporte_publico_emt`: admitir el registro parcial
  en Silver, calcular las magnitudes derivadas como `null` cuando falte
  cualquier operando, y excluir esos registros solo de la agregación
  horaria de Gold (no del propio Silver) cuando no tengan `measured_at`.
  Si una tarea futura quisiera medir explícitamente la cobertura de
  aparcamientos que comparten ocupación en tiempo real (cuántos de los ~75
  del listado real, ver `ingesta/capturas/aparcamientos_madrid.py`), la
  partición `fecha=__sin_medida__` de Silver (ver "Cuarto dataset" arriba)
  ya es la fuente natural para esa métrica, sin necesidad de releer Bronze.
- `ruido` es el primer dataset del patrón cuya fuente ya es diaria, no
  horaria (ver "Séptimo dataset" arriba): Silver se particiona solo por
  `fecha` (sin `hora`) y Gold agrupa por `(station_id, period,
  measured_date)`, no por `(id, fecha, hora)`. Si una tarea futura añade un
  octavo dataset con la misma granularidad diaria, el criterio a replicar es
  este (no forzar una `hora` que no existe), y considerar si aporta valor
  una media móvil similar a `ruido.aggregate.ROLLING_WINDOW_DAYS` (ventana de
  calendario vía `Window.rangeBetween` en Spark, no `rowsBetween`, para que
  huecos de fin de semana/festivo no desplacen la ventana). Es también el
  primer dataset con un rango de plausibilidad único para varios campos
  numéricos relacionados (`transform.PLAUSIBLE_DB_RANGE`, los seis campos de
  nivel sonoro) en vez de una tabla por etiqueta como `calidad_aire`/
  `meteorologia` -- criterio a replicar cuando varios campos del mismo
  registro comparten unidad y escala, a diferencia de cuando un único campo
  representa magnitudes distintas según otro campo (ver bullet de
  `PLAUSIBLE_MAX_BY_POLLUTANT` arriba). La media móvil de `ruido` promedia
  LAeq en dB con una media aritmética simple, no el promedio energéticamente
  correcto (que requeriría revertir a presión sonora lineal) -- imprecisión
  documentada a propósito en `aggregate.py`, pendiente para una tarea futura
  que necesite precisión acústica exacta.
- `aforos_peatones_bicicletas` es el primer dataset del patrón donde Bronze
  trae **dos campos numéricos separados** (`pedestrian_count`/
  `bicycle_count`) que Silver colapsa en uno solo (`count`) según una
  etiqueta del propio registro (`mode`) -- a diferencia de `calidad_aire`/
  `meteorologia` (donde Bronze ya trae un único campo `value` por etiqueta)
  y de `trafico` (donde varios campos numéricos coexisten porque todos
  aplican al mismo registro, no son alternativos). Si una tarea futura añade
  un dataset con la misma forma (varios campos de Bronze, mutuamente
  excluyentes según una etiqueta del registro), el criterio a replicar es
  este: una tabla `dict[etiqueta, nombre_de_campo]`
  (`transform.COUNT_FIELD_BY_MODE`) en vez de conservar todos los campos en
  Silver con la mayoría a `null`. `mode` solo admite un catálogo fijo de dos
  valores (a diferencia de `pollutant`/`magnitude`, catálogos abiertos), así
  que su `ge_suite.py` no necesita ninguna columna auxiliar de Spark:
  `expect_column_values_to_be_in_set` basta de forma nativa.
- **Bloqueante real para poder usar `cartelera_cines_estrenos` en
  producción, descubierto en la tarea 055** (ver "Noveno dataset" arriba):
  el único escritor programado de Bronze de este dataset
  (`lambda_handler` en `ingesta/capturas/cartelera_cines_madrid.py`) solo
  invoca `sweep_premieres` (estrenos semanales, sin cine ni horario) — no
  hay ningún schedule que escriba sesiones concretas
  (`fetch_cinema_showtimes`, la función con la que este subpaquete de
  Silver/Gold sí sabe trabajar). Confirmado con el registro real de
  `doc/033-conectar-lambda-layer-verificar.md`: la única invocación
  registrada de este dataset escribió 6 registros, los 6 de tipo
  `estreno_semana`, ninguno de tipo sesión. Con el estado actual de
  `ingesta/`, este Silver/Gold rechazaría el 100% de los lotes reales de
  Bronze capturados hasta ahora. Antes de poder verificar este dataset con
  datos reales (mismo tipo de verificación que hicieron las tareas
  051/052 para los primeros seis), hace falta una tarea de `ingesta/` que
  añada un escritor programado de sesiones — p.ej. un `lambda_handler`
  adicional (o ampliar el existente) que recorra `CINEMAS` con
  `fetch_cinema_showtimes` en vez de (o además de) `sweep_premieres`.
- `cartelera_cines_estrenos` es el primer dataset del patrón donde Bronze
  mezcla, bajo el mismo `DATASET_NAME`, dos formas de registro genuinamente
  distintas (sesiones de cine vs. estrenos semanales, sin ningún campo
  numérico compartido ni una etiqueta común tipo `pollutant`/`mode`) en vez
  de una única forma con algunos campos opcionales. El criterio aplicado
  aquí — que la puerta de calidad rechace explícitamente, con un motivo de
  rechazo propio y documentado (`"not_a_screening_session"`), el tipo de
  registro que no encaja en el esquema de este subpaquete, en vez de
  intentar unificar ambos en una sola tabla Silver — es el que debería
  replicar cualquier tarea futura que encuentre la misma situación (un
  productor de `ingesta/` que normaliza más de una forma de registro bajo
  un mismo dataset).
- `agenda_eventos` es el primer dataset del patrón que combina, bajo un
  único esquema Silver, **dos fuentes de origen distintas** cuyos campos
  clave (`start_datetime`, `district`/`neighborhood`) tienen huecos
  diferentes (ver "Décimo dataset" arriba): una fuente siempre resuelve
  distrito/barrio y la otra nunca lo hace; una siempre trae hora de
  celebración y la otra solo fecha. El criterio aplicado -- no exigir en la
  puerta de calidad ningún campo que una de las dos fuentes nunca vaya a
  tener, y usar sentinelas (`__sin_categoria__`/`__sin_distrito__`) en la
  agregación de Gold en vez de descartar esos registros -- es el que
  debería replicar cualquier tarea futura que combine varias fuentes con
  cobertura de campos desigual bajo un mismo dataset (a diferencia de
  `ruido`/`aforos_peatones_bicicletas`, donde el campo ausente es opcional
  pero la fuente es única). Es también el segundo dataset del patrón (tras
  `cartelera_cines_estrenos`) que es un catálogo de hechos discretos en vez
  de una serie temporal de medidas, y el primero cuya agregación de Gold sí
  usa una dimensión geográfica (`district`) como parte de la clave --
  aunque, a diferencia de una agregación por distrito point-in-polygon
  (pendiente de la tarea 043, ver bullet de arriba), aquí `district` viene
  ya resuelto por el catálogo de origen de una de las dos fuentes, no
  calculado en esta tarea.
- `bluesky_menciones` es el primer dataset del patrón cuyo Bronze es texto
  libre (contenido de un post) en vez de una magnitud numérica o un catálogo
  de hechos con clave natural fuerte, y el primero cuya puerta de calidad
  necesita deduplicar duplicados exactos **dentro del mismo lote** (por
  `post_hash`) en `bronze_to_silver`, no solo por registro en
  `validate_record` -- ver "Undécimo dataset" arriba para el razonamiento
  completo y por qué es una desviación deliberada del resto del patrón. Es
  también el primer dataset cuyos timestamps clave (`created_at`/
  `indexed_at`) no los genera `ingesta/capturas/bronze.py:now_madrid()`
  sino la propia API de la fuente externa, con el sufijo `Z` en vez de un
  offset explícito -- si una tarea futura añade un dataset cuya fuente
  externa entregue sus propios timestamps en formato distinto al del resto
  del patrón, conviene revisar primero si `datetime.fromisoformat` los
  parsea tal cual bajo **Python 3.10** (el runtime real de Glue 4.0, no la
  versión de Python de esta EC2 de desarrollo, que puede ser más reciente y
  ocultar el problema en los tests locales) antes de asumir que basta con
  `_parse_iso` tal como lo tenía el resto del patrón.
