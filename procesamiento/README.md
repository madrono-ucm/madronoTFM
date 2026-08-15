# `procesamiento/` — Bronze → Silver → Gold (tarea 041, piloto de tráfico)

Este directorio es el análogo de `ingesta/` para la fase 2 del proyecto
(limpieza/normalización y agregación, ver memoria del TFM, apartados 5.5 y
6.2-6.4): mientras `ingesta/` lleva datos reales de las fuentes de Madrid a
la capa Bronze del lakehouse, `procesamiento/` transforma Bronze en Silver
(datos limpios, reproyectados, validados) y Silver en Gold (datos agregados,
listos para consumo analítico/BI o para el grafo de la tarea 043).

Esta tarea (041) es un **piloto de un único dataset** (tráfico — el más
maduro y mejor documentado de los 21 productores de `ingesta/`, ver
doc/002, doc/035, doc/037, doc/039): establece el patrón (estructura de
código, motor de procesamiento, dónde vive la puerta de calidad, cómo se
despliega) antes de extenderlo al resto de fuentes en tareas futuras. **Solo
se ha escrito código e infraestructura, sin aplicar nada en AWS** —mismo
alcance que la tarea 001 con el lakehouse; aplicar (con revisión de plan de
por medio) es una tarea posterior, igual que las tareas 014/015 lo fueron
para esa infraestructura base.

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
  tests/
    fixtures/trafico_bronze_sample.json
    test_geo.py
    test_transform.py
    test_aggregate.py
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

- `ge_suite.py`, `glue_bronze_to_silver.py` y `glue_silver_to_gold.py`
  importan `pyspark`/`great_expectations`/`awsglue` a nivel de módulo y
  **no se han podido importar ni ejecutar en esta sesión**. Están escritos
  con el mismo cuidado que el resto del proyecto y basados en la API
  pública documentada de Glue/GX (Glue: `awsglue.context.GlueContext`,
  `awsglue.job.Job`, estable desde hace años; GX: `sources.
  add_or_update_spark`/`Validator`, API "Fluent" estable en la serie
  0.17-0.18 — versión fijada en `var.great_expectations_pip_spec`,
  `infra/terraform/variables.tf`), pero **no verificados por ejecución
  real**. Antes del primer `terraform apply` de esta infraestructura,
  conviene una prueba de humo en un notebook/endpoint de desarrollo de Glue
  (`aws glue start-job-run` contra un lote pequeño, o un Glue Studio
  Notebook interactivo) para confirmar la sintaxis exacta contra la versión
  real del runtime, antes de dejarlo correr contra Bronze de producción.
- Ningún test de este proyecto importa esos tres módulos (ver
  `procesamiento/silver_gold/trafico/__init__.py`, que expone solo
  `geo`/`transform`/`aggregate` a propósito) — así el resto del paquete
  sigue siendo importable/testable en cualquier entorno sin Spark.
- No se ha procesado ningún dato real de Bronze (no hay Glue desplegado
  todavía): toda la verificación de esta tarea usa el fixture
  `tests/fixtures/trafico_bronze_sample.json` (10 registros de ejemplo, 5
  válidos + 5 que violan cada regla de la puerta de calidad por turnos,
  construido a mano — incluye el punto real de doc/002 para verificar la
  reproyección contra una coordenada de producción conocida).

## Terraform (`infra/terraform/glue.tf`)

Sin aplicar (ver arriba). Recursos declarados:

- `aws_glue_job.trafico_bronze_to_silver` / `trafico_silver_to_gold`: dos
  jobs (uno por transformación, no combinados — para poder reintentar/
  reejecutar cada etapa de forma independiente, p.ej. volver a agregar Gold
  sin releer Bronze). `glue_version = "4.0"`, `worker_type = "G.1X"`,
  `number_of_workers = 2` (mínimo permitido) — variables en `variables.tf`
  para poder subir esto sin tocar `.tf` cuando el volumen crezca.
- `aws_iam_role.glue_trafico`: la política gestionada
  `AWSGlueServiceRole` (lo que todo job de Glue necesita en su propio
  nombre: API de Glue, logs bajo `/aws-glue/...`) más una política propia
  acotada por prefijo — lectura de `bronze/trafico/*`, lectura+escritura de
  `silver/trafico/*`, escritura de `gold/trafico_por_punto_hora/*`, lectura
  del script/librería en el bucket de artefactos (`aws_s3_bucket.build_artifacts`,
  reutilizado de la tarea 032 en vez de crear un bucket nuevo solo para dos
  ficheros .py y un .zip pequeño) y permisos acotados sobre el catálogo de
  Glue de las dos tablas de este dataset — ni un permiso más.
- `aws_glue_catalog_database.silver`/`gold` + `aws_glue_catalog_table.trafico_silver`/
  `trafico_gold`: catalogadas para poder consultarlas con Athena sin ningún
  paso adicional. Bronze deliberadamente **no** se cataloga: son lotes JSON
  crudos sin un esquema único garantizado entre los 21 productores, no
  pensados para consultarse vía SQL.
- `data.archive_file.procesamiento_source` + `aws_s3_object.*`: empaquetan
  `procesamiento/` (salvo `tests/`) y los dos scripts de job, subidos al
  bucket de artefactos con el hash del contenido en la key (mismo patrón
  que `data.archive_file.ingesta_source`/`layer_source_key` de tareas
  anteriores) — un cambio de código sube a una key nueva sin pisar la
  anterior.

`terraform validate` limpio (verificado en esta tarea, sin backend real
inicializado — `terraform init -backend=false`); no se ha ejecutado
`terraform plan` contra la cuenta real (necesitaría credenciales AWS que
esta tarea no debe usar para aplicar nada).

## Relevante para tareas futuras

- Este piloto fija el patrón para extender Bronze→Silver→Gold al resto de
  fuentes: un subpaquete `silver_gold/<dataset>/` con `transform.py`
  (Python puro, testable)/`aggregate.py` (idem, de referencia)/`ge_suite.py`
  (GX, ejecutado en Glue)/`glue_*.py` (entry points), más un bloque en
  `glue.tf` con su propio rol IAM acotado por prefijo (no un rol
  compartido entre datasets: mantiene el principio de mínimo privilegio ya
  aplicado en `ingesta`).
- Antes de aplicar esta infraestructura: (1) smoke-test de `ge_suite.py`
  contra un Glue Studio Notebook real (ver arriba), (2) revisar si
  `great_expectations==0.18.19` (versión fijada en
  `var.great_expectations_pip_spec`) sigue siendo la última estable de la
  serie 0.18 en el momento de aplicar, y (3) el mismo patrón
  `terraform plan`/`apply` con revisión humana de por medio que ya usaron
  las tareas 015/030/039 para la infraestructura ya desplegada.
- La agregación por distrito (en vez de por punto de medida) queda
  pendiente de la tarea 043 (grafo Neo4j de relaciones espaciales) — no se
  ha aproximado con una heurística ad-hoc a propósito, ver "Transformación
  Silver → Gold" arriba.
- `intensity_ratio` (intensidad / intensidad de saturación) es la magnitud
  pensada para comparar puntos de medida con capacidades distintas; si una
  tarea futura necesita comparar directamente con otros datasets de
  movilidad (BiciMAD, EMT), esta es la columna de Silver/Gold más
  directamente reutilizable como "nivel de congestión" normalizado.
