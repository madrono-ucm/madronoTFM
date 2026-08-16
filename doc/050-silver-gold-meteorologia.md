# 050 — Silver/Gold: meteorología (sexto dataset del patrón 041)

## Qué se implementó

`procesamiento/silver_gold/meteorologia/`, replicando el patrón que la
tarea 041 fijó con tráfico y que las tareas 046/047/048/049 ya replicaron
con transporte público EMT, BiciMAD, aparcamientos rotacionales y calidad
del aire (ver `procesamiento/README.md`): `transform.py` (Bronze→Silver,
puerta de calidad, Python puro), `aggregate.py` (Silver→Gold, Python puro,
fuente de verdad documental/de test), `ge_suite.py` (Great Expectations,
requiere `pyspark`/GX) y `glue_bronze_to_silver.py`/`glue_silver_to_gold.py`
(entry points reales de Glue). Fuente: `ingesta/capturas/meteorologia_madrid.py`
(lecturas horarias de la red de ~25 estaciones meteorológicas de Madrid, ver
doc/008). **Alcance: solo este dataset y solo código/infraestructura, sin
`terraform apply`** — mismo criterio que las tareas 041/046/047/048/049, el
resto de subpaquetes de `silver_gold/` no se ha tocado.

## Sin `geo.py`

`ingesta/capturas/meteorologia_madrid.py` (`normalize_station_record`) ya
entrega `location.lat`/`location.lon` en WGS84 (coordenadas del CSV de
metadatos "Estaciones de control" de datos.madrid.es), no hace falta ninguna
reproyección.

## Diferencia real frente a `calidad_aire`: Bronze llega "ancho", no "largo"

El enunciado apuntaba a "mismo backend/formato que calidad_aire" (registro
por estación+magnitud+hora), pero al examinar el esquema real de
`meteorologia_madrid.normalize_station_record` resultó ser distinto:
agrega deliberadamente **todas** las magnitudes de una estación (hasta 8:
temperatura, humedad, viento -velocidad y dirección-, presión, radiación
solar, radiación UV, precipitación) en un único registro Bronze "ancho" —
el objetivo original de la tarea 008 pedía explícitamente un esquema con
"temperatura, humedad, viento, precipitación" como campos de un mismo
registro, a diferencia de `calidad_aire` (un registro por
estación+contaminante). No todas las estaciones miden todas las magnitudes;
un campo ausente en Bronze es simplemente `null`.

`transform.py` resuelve esto pivotando de ancho a largo **dentro del propio
paso Bronze→Silver**: `bronze_to_silver` puede producir hasta 8 registros
Silver por cada registro Bronze (uno por magnitud presente y válida), cada
uno con su propio campo `magnitude` (el nombre de campo Bronze, p.ej.
`"temperature_c"`, que ya codifica la unidad) y `value`. Esto mantiene
Silver/Gold en el mismo formato "largo por magnitud" que el resto del
patrón, y permite que `aggregate.py` agrupe por `(station_id, magnitude,
fecha, hora)` sin tener que repivotar.

## Puerta de calidad de dos niveles

Consecuencia directa del pivote: la puerta de calidad tiene dos funciones
separadas.

1. `validate_record(record)`: comprobaciones a nivel de estación+instante
   (`station_id`/`measured_at`/`ingested_at` no nulos, timestamps
   timezone-aware). Si fallan, **ninguna** magnitud de ese registro llega a
   Silver — no hay estación/instante al que atribuirlas.
2. `validate_magnitude_value(magnitude, value)`: rango de plausibilidad por
   magnitud (`transform.PLAUSIBLE_RANGE_BY_MAGNITUDE`, con mínimo Y máximo
   — a diferencia de `calidad_aire.PLAUSIBLE_MAX_BY_POLLUTANT`, donde el
   mínimo siempre es 0). Si falla, se descarta **solo esa magnitud**: un
   sensor de temperatura estropeado no debe tirar también la humedad o el
   viento válidos de la misma estación.

Es el primer dataset del patrón donde una parte de un registro Bronze puede
rechazarse sin rechazar el registro completo. Los rangos por magnitud (ver
docstring de `transform.py` para el razonamiento completo de cada cota) son
deliberadamente laxos y no proceden de ningún límite legal/oficial —p.ej.
temperatura en [-20, 50]°C (muy por encima/debajo de cualquier registro
histórico de Madrid), presión en [850, 1050] mb (Madrid está a ~600-700m de
altitud, su presión típica ~930-950 mb ya es más baja que a nivel del mar).

## Agregación Silver → Gold (`aggregate.py`)

Por `(station_id, magnitude, fecha, hora)` — mismo criterio de clave de tres
componentes que `calidad_aire`: una estación reporta varias magnitudes
simultáneamente, mezclarlas en un único agregado por estación+hora
produciría una media sin significado. Cada fila agrega `samples_count`,
`avg`/`max`/`min_value`, `first`/`last_measured_at` y `lat`/`lon`/
`altitude_m` (una estación tiene ubicación fija; `altitude_m` es un campo
propio de este dataset, ausente en el resto — la fuente publica la altitud
de cada emplazamiento).

## Tests

26 tests nuevos en `procesamiento/tests/` (`test_meteorologia_transform.py`,
`test_meteorologia_aggregate.py`), más un fixture de 10 registros Bronze
"anchos" (`tests/fixtures/meteorologia_bronze_sample.json`: las 5 estaciones
reales de `ingesta/capturas/samples/meteorologia_madrid_sample.json` —que
expanden a 30 registros Silver "largos" al pivotar— + 5 que violan cada
regla por turnos: estación sin id, sin `measured_at`, `measured_at` sin zona
horaria, sin `ingested_at`, y una estación con la temperatura disparada pero
el resto de sus magnitudes válidas —prueba específica de que el rechazo a
nivel de magnitud no descarta el resto del registro—). Suite completa del
proyecto en verde: 267 tests de `ingesta` (sin cambios) + 144 de
`procesamiento` (27 de tráfico + 20 de transporte público EMT + 23 de
BiciMAD + 23 de aparcamientos + 22 de calidad del aire + 26 nuevos de
meteorología), `python3 -m unittest discover -s procesamiento/tests -t .` y
`-s ingesta/tests -t .`.

Igual que en las tareas 041/046/047/048/049, `ge_suite.py` y los dos
`glue_*.py` de este dataset importan `pyspark`/`great_expectations`/
`awsglue` a nivel de módulo y **no se han podido importar ni ejecutar en
esta sesión** (mismo motivo: disco compartido muy limitado en esta EC2) —
ningún test los importa a propósito
(`procesamiento/silver_gold/meteorologia/__init__.py` solo expone
`transform`/`aggregate`).

## Terraform (`infra/terraform/glue.tf`, extendido)

Sin aplicar. Se añadió un bloque completo para este dataset (rol IAM propio
`glue_meteorologia`, acotado por prefijo `bronze/meteorologia/*` ·
`silver/meteorologia/*` · `gold/meteorologia_por_estacion_magnitud_hora/*`,
más el catálogo de sus dos tablas Silver/Gold; dos `aws_glue_job`,
Bronze→Silver y Silver→Gold), **sin tocar** los bloques de tráfico,
transporte público EMT, BiciMAD, aparcamientos ni calidad del aire, ni
compartir su rol IAM (mismo principio de mínimo privilegio por dataset).
`data.archive_file.procesamiento_source` no necesitó ningún cambio: ya
empaquetaba todo `procesamiento/` (salvo `tests/`), así que el subpaquete
nuevo se incluye automáticamente en el artefacto de librería compartido.

`glue_bronze_to_silver.py` traduce `transform.PLAUSIBLE_RANGE_BY_MAGNITUDE`
a dos columnas auxiliares (`value_below_plausible_min`,
`value_over_plausible_max`) para que `ge_suite.py` pueda validar el rango
por magnitud con GX (que no tiene una expectation nativa de "el rango
depende del valor de otra columna") — mismo mecanismo que `calidad_aire`,
extendido con un segundo límite porque aquí el mínimo también varía por
magnitud.

`terraform validate` limpio, verificado con `terraform init -backend=false`
(sin backend real, sin credenciales AWS) tras limpiar los `__pycache__/*.pyc`
generados por `python3 -m unittest` (mismo problema preexistente de
`lambda.tf` documentado en doc/046, no introducido por esta tarea).
`terraform fmt -check -recursive` limpio. No se ha ejecutado `terraform
plan`/`apply` contra la cuenta real. `.terraform/` y `.terraform.lock.hcl`
generados por `terraform init`/`validate` se eliminaron al terminar — nada
de esto se commitea.

## `procesamiento/README.md`: actualizado para reflejar el sexto dataset

Título, párrafo introductorio, estructura de código y las secciones de
Great Expectations, "Qué no se ha podido ejecutar", Terraform y "Relevante
para tareas futuras" se actualizaron para cubrir los seis datasets. Se
añadió una sección "Sexto dataset: `meteorologia`" con el razonamiento
completo del pivote ancho→largo y la puerta de calidad de dos niveles.

## Restricciones respetadas

- Alcance limitado a `meteorologia` — no se ha tocado
  `procesamiento/silver_gold/trafico/`,
  `procesamiento/silver_gold/transporte_publico_emt/`,
  `procesamiento/silver_gold/bicimad/`,
  `procesamiento/silver_gold/aparcamientos/` ni
  `procesamiento/silver_gold/calidad_aire/`.
- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales.
- No se ha instalado `pyspark`/`great_expectations` en esta EC2.
- No se ha procesado ningún dato real de Bronze: toda la verificación usa
  el fixture de ejemplo, construido a partir de la muestra real ya
  commiteada por `ingesta/capturas/samples/meteorologia_madrid_sample.json`.
- No se ha dejado nada programado (cron, systemd timer, bucle) en esta EC2.

## Relevante para tareas futuras

- El patrón fijado por la 041 ya se ha replicado cinco veces
  (041→046→047→048→049→050): un subpaquete `silver_gold/<dataset>/` con
  `transform.py`/`aggregate.py` (Python puro, testable)/`ge_suite.py`/
  `glue_*.py`, más `geo.py` **solo si la fuente lo necesita** (ninguno de
  los cinco últimos datasets lo tiene), más un bloque en `glue.tf` con su
  propio rol IAM.
- `meteorologia` es el primer dataset del patrón donde Bronze llega en
  formato "ancho" (una fila por estación+instante con varias magnitudes
  como columnas) y hay que pivotarlo a "largo" dentro del propio paso
  Bronze→Silver, y el primero con una puerta de calidad de dos niveles
  (registro completo vs. magnitud individual). Si una tarea futura añade
  un dataset con la misma forma, el criterio a replicar es: pivotar en
  `transform.py` (no en `aggregate.py` ni en el job de Glue) y separar la
  validación de estación/instante de la validación por magnitud.
- `meteorologia.PLAUSIBLE_RANGE_BY_MAGNITUDE` extiende el criterio de tabla
  `dict[etiqueta, rango]` que ya introdujo `calidad_aire.PLAUSIBLE_MAX_BY_POLLUTANT`,
  pero con mínimo Y máximo por etiqueta (no solo máximo) — si una tarea
  futura necesita ese mismo patrón con límites en ambos extremos, la tabla
  pasa a ser `dict[etiqueta, tuple[mínimo, máximo]]`.
- Antes de aplicar cualquiera de los seis bloques de infraestructura de
  Glue: smoke-test de los seis `ge_suite.py` en un Glue Studio Notebook
  real (el de `meteorologia`, como los de `bicimad`/`aparcamientos`/
  `calidad_aire`, necesita además confirmar en el runtime real que sus
  columnas auxiliares funcionan como se espera, al no existir una
  expectation nativa de "el rango depende del valor de otra columna"), y
  revisar si `great_expectations==0.18.19` sigue siendo la versión
  adecuada en el momento de aplicar (misma pendiente que dejaron las
  tareas 041/046/047/048/049, ahora aplica a seis datasets).
- `altitude_m` (Silver y Gold de `meteorologia`) es el primer campo
  geográfico del patrón distinto de `lat`/`lon` — si una tarea futura
  necesita la altitud de otras ubicaciones del proyecto (p.ej. para el
  grafo Neo4j, tarea 043), esta es la única fuente del patrón que ya la
  publica.
