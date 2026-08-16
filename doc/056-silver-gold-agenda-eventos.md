# 056 — Silver/Gold: agenda de eventos culturales (décimo dataset del patrón 041)

## Qué se implementó

`procesamiento/silver_gold/agenda_eventos/`, replicando la estructura de
código del patrón que la tarea 041 fijó con tráfico y que las tareas
046/047/048/049/050/053/054/055 ya replicaron con transporte público EMT,
BiciMAD, aparcamientos rotacionales, calidad del aire, meteorología,
contaminación acústica, aforos de peatones/bicicletas y cartelera de cines
(ver `procesamiento/README.md`): `transform.py` (Bronze→Silver, puerta de
calidad, Python puro), `aggregate.py` (Silver→Gold, Python puro, fuente de
verdad documental/de test), `ge_suite.py` (Great Expectations) y
`glue_bronze_to_silver.py`/`glue_silver_to_gold.py` (entry points reales de
Glue). Fuente: `ingesta/capturas/agenda_eventos_madrid.py` (dos orígenes
combinados bajo un campo `source`: `agenda_eventos_madrid_municipal`,
dataset municipal de datos.madrid.es, y `agenda_turismo_esmadrid`, agenda
turística de Madrid Destino/esmadrid.com). **Alcance: solo este dataset y
solo código/infraestructura, sin `terraform apply`** — mismo criterio que
las tareas anteriores del patrón; el resto de subpaquetes de `silver_gold/`
no se ha tocado.

## Sin `geo.py`

`ingesta/capturas/agenda_eventos_madrid.py` (`normalize_municipal_event` y
`normalize_esmadrid_event`) ya entrega `location.lat`/`location.lon` en
WGS84 para ambas fuentes (`"srid": "EPSG:4326"` cuando hay coordenadas) — no
hace falta ninguna reproyección.

## Diferencia real frente al resto del patrón: catálogo de eventos, no serie temporal

Igual que `cartelera_cines_estrenos` (tarea 055), cada fila de Silver es un
hecho discreto — un evento concreto, identificado por `event_id` — no una
medida numérica repetida en el tiempo. La puerta de calidad
(`transform.validate_record`) exige los campos clave que pide el enunciado
(`title`, `start_datetime` parseable, `source` conocida) más `event_id`
(clave natural imprescindible para deduplicar reingestas en
`aggregate.py`) y `captured_at`/`ingested_at` timezone-aware.

## Dos fuentes con huecos de esquema distintos

`district`/`neighborhood` los resuelve siempre la agenda municipal (desde
su propio catálogo de datos.madrid.es) y **nunca** la agenda de esMadrid (el
XML de origen no publica esa columna) — no forman parte de la puerta de
calidad, para no descartar sistemáticamente el 100% de una de las dos
fuentes. `start_datetime` también difiere de formato: el dato municipal
trae un `datetime` completo sin zona horaria explícita; esMadrid solo trae
la **fecha** del primer rango del evento, sin hora (la hora real, cuando
existe, queda en `schedule_text` como texto libre — simplificación ya
documentada en el módulo de ingesta). `validate_record` solo exige que
`start_datetime` sea parseable (`datetime.fromisoformat` acepta ambos
formatos), no que tenga hora ni que sea timezone-aware.

## Diferencia explícita frente a `cartelera_cines_estrenos`: no se descartan eventos "ya pasados"

Una sesión de cine es un instante puntual futuro por construcción de la
fuente; un evento de esta agenda puede ser una exposición de varios meses
cuyo `start_datetime` ya quedó atrás en el momento de la captura pero que
sigue vigente (evento real de muestra: "25 años del Museo de San Isidro...",
inicio 2026-07-21, capturado el 2026-08-15). Comparar
`start_datetime < captured_at` aquí descartaría eventos genuinamente en
curso, así que esta puerta de calidad, a propósito, no reproduce la regla
`"showtime_already_passed"` de `cartelera_cines_estrenos`.

## Decisión de agregación Silver → Gold: `(category, district, fecha)`

El enunciado sugería "por barrio/distrito y día, o por categoría y día"
como alternativas — mismo patrón de dos sugerencias que ya resolvió
`cartelera_cines_estrenos` incluyendo ambas dimensiones en la misma clave.
Se agrupa por categoría, distrito y el día en que el evento **empieza** (no
el día de captura), para poder responder tanto "¿cuántos eventos de tal
categoría hay hoy?" como "¿cuántos eventos hay hoy en tal distrito?" sin
perder información en la propia agregación. Se usa `district`, no
`neighborhood` (barrio): como esMadrid nunca publica ninguno de los dos, una
granularidad más fina que distrito fragmentaría aún más una dimensión que
ya es parcial por diseño de una de las dos fuentes. Cruzar `lat`/`lon` con
`barrios_distritos_madrid` (point-in-polygon) para rellenar el distrito que
falta en esMadrid queda fuera de alcance, igual que ya documentó la tarea
041 para `trafico` — es el tipo de relación espacial que la tarea 043
(grafo Neo4j) modelará de forma explícita y reutilizable.
`category`/`district` ausentes se agrupan bajo un sentinela
(`__sin_categoria__`/`__sin_distrito__`, mismo criterio que
`aparcamientos.aggregate` con `fecha=__sin_medida__`, tarea 048) en vez de
descartarse.

Cada fila de Gold agrega `samples_count` (filas Silver, incluye
reingestas), `events_count` (número de `event_id` distintos — la magnitud
principal), `free_events_count` (eventos distintos con `free = true`),
`sources` (lista ordenada de `source` distintos presentes en el bucket) y
`first`/`last_start_datetime`.

`glue_bronze_to_silver.py` particiona Silver **solo por `fecha`** (sin
`hora`), derivada con `substring(start_datetime, 1, 10)` en vez de
`to_date(...)`: mismo motivo que `ruido` (tarea 053) — una de las dos
fuentes no publica ninguna hora de celebración, y forzar una hora inventada
sería engañoso; el recorte de texto funciona igual para ambos formatos de
origen porque los dos siempre empiezan por `YYYY-MM-DD`.

## Tests

24 tests nuevos en `procesamiento/tests/` (`test_agenda_eventos_transform.py`,
`test_agenda_eventos_aggregate.py`), más un fixture de 17 registros Bronze
(`tests/fixtures/agenda_eventos_bronze_sample.json`: los 10 eventos reales
de `ingesta/capturas/samples/agenda_eventos_madrid_sample.json` — 5
municipales + 5 de esMadrid, ambas fuentes válidas sin modificación — + 7
sintéticos que violan cada regla de rechazo por turnos: `source`
ausente/desconocida, `event_id` ausente, `title` ausente, `start_datetime`
ausente/no parseable, `captured_at` ausente/sin zona horaria). Suite
completa del proyecto en verde: 267 tests de `ingesta` (sin cambios) + 237
de `procesamiento` (213 previos + 24 nuevos),
`python3 -m unittest discover -s procesamiento/tests -t .` y
`-s ingesta/tests -t .`.

Igual que en las tareas anteriores del patrón, `ge_suite.py` y los dos
`glue_*.py` de este dataset importan `pyspark`/`great_expectations`/
`awsglue` a nivel de módulo y **no se han podido importar ni ejecutar en
esta sesión** (mismo motivo: disco compartido muy limitado en esta EC2) —
ningún test los importa a propósito
(`procesamiento/silver_gold/agenda_eventos/__init__.py` solo expone
`transform`/`aggregate`). `glue_bronze_to_silver.py` escribe el informe de
Great Expectations directamente a S3 vía `boto3.client("s3").put_object`,
NO con `sc.parallelize(...).saveAsTextFile(...)` — se copió el arreglo de
la tarea 051 desde el principio (ya lo tenían `ruido`/
`aforos_peatones_bicicletas`/`cartelera_cines_estrenos`, y el enunciado de
esta tarea lo pedía explícitamente).

## Terraform (`infra/terraform/glue.tf`, extendido)

Sin aplicar. Se añadió un bloque completo para este dataset (rol IAM propio
`glue_agenda_eventos`, acotado por prefijo `bronze/agenda_eventos/*` ·
`silver/agenda_eventos/*` ·
`gold/agenda_eventos_por_categoria_distrito_fecha/*`, incluidos desde el
principio los dos statements de permisos que las tareas 051/052 tuvieron
que descubrir empíricamente y añadir a posteriori para los seis primeros
datasets — `s3:PutObject` sobre `_quality_reports/agenda_eventos/*` y sobre
el marcador `agenda_eventos_por_categoria_distrito_fecha_$folder$` —, más
el catálogo de sus dos tablas Silver/Gold; dos `aws_glue_job`, Bronze→Silver
y Silver→Gold), **sin tocar** los bloques de los nueve datasets anteriores
ni compartir su rol IAM. La tabla Silver del catálogo declara una única
`partition_keys` (`fecha`, sin `hora` — mismo criterio que `ruido`, tarea
053). `data.archive_file.procesamiento_source` no necesitó ningún cambio:
ya empaquetaba todo `procesamiento/` (salvo `tests/`), así que el
subpaquete nuevo se incluye automáticamente en el artefacto de librería
compartido.

`terraform validate` limpio, verificado con `terraform init -backend=false`
(sin backend real, sin credenciales AWS) tras limpiar los `__pycache__/*.pyc`
generados por `python3 -m unittest` (mismo problema preexistente ya
documentado en doc/046, no introducido por esta tarea). `terraform fmt
-check -diff glue.tf` sin diferencias. No se ha ejecutado `terraform
plan`/`apply` contra la cuenta real. `.terraform/`, `.terraform.lock.hcl` y
`backend.hcl` (copia local de `backend.hcl.example`, ya cubierta por
`.gitignore`) generados por `terraform init`/`validate` se eliminaron al
terminar — nada de esto se commitea.

## `procesamiento/README.md`: actualizado para reflejar el décimo dataset

Título, párrafo introductorio, estructura de código, lista de fixtures/tests
y las secciones de Great Expectations, "Qué no se ha podido ejecutar",
Terraform y "Relevante para tareas futuras" se actualizaron para cubrir los
diez datasets. Se añadió una sección "Décimo dataset: `agenda_eventos`" con
el razonamiento completo (catálogo de eventos en vez de serie temporal, las
dos fuentes con huecos de esquema distintos, la diferencia explícita frente
a `cartelera_cines_estrenos` sobre eventos "ya pasados", y la justificación
de la clave de agregación de Gold), y bullets nuevos en "Relevante para
tareas futuras" documentando el criterio de combinar varias fuentes con
cobertura de campos desigual, y aclarando que el uso de `district` como
clave de agregación aquí no es un point-in-polygon (viene ya resuelto por
el catálogo de origen de la agenda municipal).

## Restricciones respetadas

- Alcance limitado a `agenda_eventos` — no se ha tocado ningún otro
  subpaquete de `procesamiento/silver_gold/`.
- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales.
- No se ha instalado `pyspark`/`great_expectations` en esta EC2.
- No se ha modificado `ingesta/capturas/agenda_eventos_madrid.py`.
- No se ha procesado ningún dato real de Bronze: toda la verificación usa
  el fixture de ejemplo, construido a partir de la muestra real ya
  commiteada por `ingesta/capturas/samples/agenda_eventos_madrid_sample.json`.
- No se ha dejado nada programado (cron, systemd timer, bucle) en esta EC2.
- No se ha intentado ningún cruce point-in-polygon con
  `barrios_distritos_madrid` — la agregación por distrito usa directamente
  el campo `district` que ya resuelve el catálogo municipal de origen,
  siguiendo la instrucción explícita de la tarea de no reintentar aquí lo
  que corresponde a la tarea 043.

## Relevante para tareas futuras

- El patrón fijado por la 041 ya se ha replicado nueve veces
  (041→046→047→048→049→050→053→054→055→056): un subpaquete
  `silver_gold/<dataset>/` con `transform.py`/`aggregate.py` (Python puro,
  testable)/`ge_suite.py`/`glue_*.py`, más `geo.py` **solo si la fuente lo
  necesita** (ninguno de los últimos nueve datasets lo tiene), más un bloque
  en `glue.tf` con su propio rol IAM.
- `agenda_eventos` es el primer dataset del patrón que combina, bajo un
  único esquema Silver, dos fuentes de origen distintas cuyos campos clave
  tienen huecos diferentes entre sí (una siempre resuelve distrito/barrio y
  hora de celebración, la otra nunca). El criterio a replicar para un caso
  similar: no exigir en la puerta de calidad ningún campo que una de las
  fuentes nunca vaya a tener, y usar sentinelas en la agregación de Gold en
  vez de descartar esos registros.
- Es también el segundo dataset del patrón (tras `cartelera_cines_estrenos`)
  que es un catálogo de hechos discretos en vez de una serie temporal, y el
  primero cuya agregación de Gold usa una dimensión geográfica (`district`)
  como parte de la clave — sin que sea un point-in-polygon: ese distrito
  viene ya resuelto por el catálogo de origen de una de las dos fuentes, no
  calculado en esta tarea. La agregación por distrito point-in-polygon
  genérica (para los datasets de punto de medida: `trafico`,
  `transporte_publico_emt`, `bicimad`, `aparcamientos`, `calidad_aire`,
  `meteorologia`, `ruido`, `aforos_peatones_bicicletas`) sigue pendiente de
  la tarea 043.
- Antes de aplicar cualquiera de los diez bloques de infraestructura de
  Glue: smoke-test de los diez `ge_suite.py` en un Glue Studio Notebook
  real — el de `agenda_eventos` necesita en particular confirmar que
  `expect_column_values_to_not_be_null("start_datetime")` no rechaza por
  error el formato "solo fecha" de esMadrid contra el runtime real —, y
  revisar si `great_expectations==0.18.19` sigue siendo la versión adecuada
  en el momento de aplicar (misma pendiente que dejaron las tareas
  anteriores, ahora aplica a diez datasets).
