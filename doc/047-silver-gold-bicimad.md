# 047 — Silver/Gold: BiciMAD (tercer dataset del patrón 041)

## Qué se implementó

`procesamiento/silver_gold/bicimad/`, replicando el patrón que la tarea 041
fijó con tráfico y la 046 ya replicó con transporte público EMT (ver
`procesamiento/README.md`): `transform.py` (Bronze→Silver, puerta de
calidad, Python puro), `aggregate.py` (Silver→Gold, Python puro, fuente de
verdad documental/de test), `ge_suite.py` (Great Expectations, requiere
`pyspark`/GX) y `glue_bronze_to_silver.py`/`glue_silver_to_gold.py` (entry
points reales de Glue). Fuente: `ingesta/capturas/bicimad.py` (estado de
estaciones de BiciMAD vía feed GBFS público, ver doc/004). **Alcance: solo
este dataset y solo código/infraestructura, sin `terraform apply`** — mismo
criterio que las tareas 041/046, `procesamiento/silver_gold/trafico/` y
`procesamiento/silver_gold/transporte_publico_emt/` no se han tocado.

## Sin `geo.py` (como en `transporte_publico_emt`)

`ingesta/capturas/bicimad.py` (`normalize_record`) ya entrega
`location.lat`/`location.lon` en WGS84 (coordenadas del propio feed GBFS
estándar), así que no hace falta ninguna reproyección. El subpaquete no
tiene ningún fichero `geo.py`, tal como anticipaba el enunciado de la tarea.

## Puerta de calidad (`transform.validate_record`)

- `station_id`/`measured_at`/`ingested_at` no nulos, `measured_at`/
  `ingested_at` parseables y timezone-aware.
- Descarta estaciones con `is_installed = false` (retiradas de la red o en
  mantenimiento, sin contadores fiables).
- Contadores (`bikes_available`, `bikes_disabled`, `docks_available`,
  `docks_disabled`, `docks_total`) no negativos cuando están presentes.
- **Consistencia entre contadores, con `<=` en vez de `==`**: el enunciado
  de la tarea planteaba una igualdad exacta como posibilidad si la fuente
  real la cumplía, pero se decidió `<=` tras contrastar contra las 5
  estaciones reales de `ingesta/capturas/samples/bicimad_sample.json` (p.ej.
  estación `1406`: `bikes_available=1 + bikes_disabled=5 = 6 <=
  docks_total=47`, con una discrepancia de 41 respecto a la capacidad). Esa
  discrepancia es sistemática y esperada, no un error de datos: una bici
  alquilada en ese instante (fuera de cualquier estación) no aparece en
  ningún contador de ninguna estación, así que la suma real observada nunca
  puede superar la capacidad, pero tampoco tiene por qué agotarla. Reglas
  aplicadas: `bikes_available + bikes_disabled <= docks_total` y
  `docks_available + docks_disabled <= docks_total` (cuando los tres campos
  de cada regla están presentes; ausentes se aceptan, igual que el resto de
  campos opcionales del patrón).

## Normalización (`transform.to_silver_record`)

Conserva los campos en bruto de Bronze y añade `occupancy_ratio` =
`bikes_available / docks_total` — magnitud 0-1 comparable entre estaciones
de capacidades distintas, mismo criterio que `occupancy_ratio`/
`intensity_ratio` en `trafico/transform.py`.

## Agregación Silver → Gold (`aggregate.py`)

Por `(station_id, fecha, hora)`. A diferencia de `transporte_publico_emt`
(donde `location` es la posición de un autobús en movimiento, sin sentido
agregado), una estación de BiciMAD sí tiene una ubicación fija — Gold sí
incluye `lat`/`lon` (mismo criterio que `trafico/aggregate.py`). Cada fila
agrega `samples_count`, `avg_bikes_available`/`avg_bikes_disabled`/
`avg_docks_available`/`avg_docks_disabled`, `avg_occupancy_ratio`,
`docks_total` (capacidad, constante en la práctica) y
`first`/`last_measured_at`.

## `ge_suite.py`: sin expectation nativa para la consistencia de contadores

Great Expectations no tiene una expectation de columna única para "suma de
columnas <= otra columna". Se resuelve calculando dos columnas auxiliares
(`bikes_over_capacity`, `docks_over_capacity`) en el propio
`glue_bronze_to_silver.py` antes de validar, y comprobando con GX que esas
columnas son `<= 0` — documentado explícitamente en el docstring de
`ge_suite.py` para que no parezca una omisión al leerlo junto a
`transform.validate_record`.

## Tests

23 tests nuevos en `procesamiento/tests/` (`test_bicimad_transform.py`,
`test_bicimad_aggregate.py`), más un fixture de 10 registros
(`tests/fixtures/bicimad_bronze_sample.json`: las 5 estaciones reales de
`ingesta/capturas/samples/bicimad_sample.json` + 5 que violan cada regla de
la puerta de calidad por turnos — `station_id` nulo, `measured_at` nulo,
`is_installed=false`, contador negativo, bicis por encima de la capacidad).
Suite completa del proyecto en verde: 267 tests de `ingesta` (sin cambios) +
70 de `procesamiento` (27 de tráfico + 20 de transporte público EMT + 23
nuevos de BiciMAD), `python3 -m unittest discover -s procesamiento/tests -t
.` y `-s ingesta/tests -t .`.

Igual que en las tareas 041/046, `ge_suite.py` y los dos `glue_*.py` de este
dataset importan `pyspark`/`great_expectations`/`awsglue` a nivel de módulo
y **no se han podido importar ni ejecutar en esta sesión** (mismo motivo:
disco compartido muy limitado en esta EC2) — ningún test los importa a
propósito (`procesamiento/silver_gold/bicimad/__init__.py` solo expone
`transform`/`aggregate`).

## Terraform (`infra/terraform/glue.tf`, extendido)

Sin aplicar. Se añadió un bloque completo para este dataset (rol IAM propio
`glue_bicimad`, acotado por prefijo `bronze/bicimad/*` ·
`silver/bicimad/*` · `gold/bicimad_por_estacion_hora/*`, más el catálogo de
sus dos tablas Silver/Gold; dos `aws_glue_job`, Bronze→Silver y
Silver→Gold), **sin tocar** los bloques de tráfico ni de transporte público
EMT ni compartir su rol IAM (mismo principio de mínimo privilegio por
dataset). `data.archive_file.procesamiento_source` no necesitó ningún
cambio: ya empaquetaba todo `procesamiento/` (salvo `tests/`), así que el
subpaquete nuevo se incluye automáticamente en el artefacto de librería
compartido.

`terraform validate` limpio, verificado con `terraform init -backend=false`
(sin backend real, sin credenciales AWS) tras limpiar los `__pycache__/*.pyc`
generados por `python3 -m unittest` (mismo problema preexistente de
`lambda.tf` documentado en doc/046, no introducido por esta tarea).
`terraform fmt -check -recursive` limpio. No se ha ejecutado `terraform
plan`/`apply` contra la cuenta real.

## `procesamiento/README.md`: actualizado para reflejar el tercer dataset

Título, párrafo introductorio, estructura de código y las secciones de
Great Expectations, "Qué no se ha podido ejecutar", Terraform y "Relevante
para tareas futuras" se actualizaron para cubrir los tres datasets. Se
añadió una sección "Tercer dataset: `bicimad`" con el razonamiento de la
consistencia `<=` frente a `==`.

## Restricciones respetadas

- Alcance limitado a `bicimad` — no se ha tocado
  `procesamiento/silver_gold/trafico/` ni
  `procesamiento/silver_gold/transporte_publico_emt/`.
- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales.
- No se ha instalado `pyspark`/`great_expectations` en esta EC2.
- No se ha procesado ningún dato real de Bronze: toda la verificación usa
  el fixture de ejemplo, construido a partir de la muestra real ya
  commiteada por `ingesta/capturas/samples/bicimad_sample.json`.
- No se ha dejado nada programado (cron, systemd timer, bucle) en esta EC2.

## Relevante para tareas futuras

- El patrón fijado por la 041 ya se ha replicado tres veces (041→046→047):
  un subpaquete `silver_gold/<dataset>/` con `transform.py`/`aggregate.py`
  (Python puro, testable)/`ge_suite.py`/`glue_*.py`, más `geo.py` **solo si
  la fuente lo necesita** (ni `transporte_publico_emt` ni `bicimad` lo
  tienen), más un bloque en `glue.tf` con su propio rol IAM.
- Antes de aplicar cualquiera de los tres bloques de infraestructura de
  Glue: smoke-test de los tres `ge_suite.py` en un Glue Studio Notebook
  real (el de `bicimad` necesita además confirmar en el runtime real que
  las columnas auxiliares de consistencia funcionan como se espera, al no
  existir una expectation nativa de "suma de columnas <= columna"), y
  revisar si `great_expectations==0.18.19` sigue siendo la versión adecuada
  en el momento de aplicar (misma pendiente que dejaron las tareas
  041/046, ahora aplica a tres datasets).
- La regla de consistencia `<=` de `bicimad` (en vez de `==`) es la primera
  pieza de calidad de datos de este proyecto que se calibra explícitamente
  contra el comportamiento real de la fuente en vez de aplicar una regla
  "de manual" — si una tarea futura extiende la puerta de calidad de este
  dataset (p.ej. para detectar discrepancias sospechosamente grandes, no
  solo violaciones de capacidad), debería mantener el `<=` como base y
  añadir una regla adicional, no sustituirlo por `==`.
- Si una tarea futura necesita la ubicación de las estaciones de BiciMAD
  para el grafo Neo4j (tarea 043), a diferencia de `transporte_publico_emt`
  (donde hay que ir al catálogo de paradas de la EMT), aquí la propia
  `location` de Silver/Gold ya es la ubicación real y fija de la estación
  — no hace falta ninguna fuente adicional.