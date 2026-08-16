# 054 — Silver/Gold: aforos de peatones y bicicletas (octavo dataset del patrón 041)

## Qué se implementó

`procesamiento/silver_gold/aforos_peatones_bicicletas/`, replicando el
patrón que la tarea 041 fijó con tráfico y que las tareas 046/047/048/049/
050/053 ya replicaron con transporte público EMT, BiciMAD, aparcamientos
rotacionales, calidad del aire, meteorología y contaminación acústica (ver
`procesamiento/README.md`): `transform.py` (Bronze→Silver, puerta de
calidad, Python puro), `aggregate.py` (Silver→Gold, Python puro, fuente de
verdad documental/de test), `ge_suite.py` (Great Expectations) y
`glue_bronze_to_silver.py`/`glue_silver_to_gold.py` (entry points reales de
Glue). Fuente: `ingesta/capturas/aforos_peatones_bicicletas_madrid.py`
(conteos horarios de la red de estaciones permanentes de aforo de Madrid,
tecnología de visión artificial Data From Sky). **Alcance: solo este
dataset y solo código/infraestructura, sin `terraform apply`** — mismo
criterio que las tareas 041/046/047/048/049/050/053, el resto de
subpaquetes de `silver_gold/` no se ha tocado.

## Sin `geo.py`

`ingesta/capturas/aforos_peatones_bicicletas_madrid.py` (`normalize_record`)
ya entrega `location.lat`/`location.lon` en WGS84 (convertidas del formato
"agrupado por puntos" del CSV de origen, mismo criterio que `ruido_madrid.py`)
— no hace falta ninguna reproyección.

## Diferencia real frente al resto del patrón: dos campos de conteo, un único `count` en Silver

Peatones y bicicletas se miden en **redes de estaciones físicamente
distintas** (`PERM_PEA##`/`PERM_BICI##`), así que cada registro Bronze trae
dos campos (`pedestrian_count`/`bicycle_count`) pero solo uno relleno según
`mode`. Es el primer dataset del patrón donde Bronze trae varios campos
numéricos mutuamente excluyentes en vez de un único campo `value` por
etiqueta (`calidad_aire`/`meteorologia`) o varios campos que sí coexisten en
el mismo registro (`trafico`). Se decidió colapsar ambos campos en un único
`count` en Silver (el que corresponde al `mode` del registro), vía una tabla
`transform.COUNT_FIELD_BY_MODE = {"peatones": "pedestrian_count",
"bicicletas": "bicycle_count"}`, en vez de conservar las dos columnas con
una siempre a `null` — mismo espíritu que la tabla `dict[etiqueta, rango]`
de `calidad_aire`, pero mapeando a un **nombre de campo**, no a un rango.
`mode` es, junto con la estación y la hora, parte de la clave natural de
agregación en `aggregate.py`.

## Puerta de calidad: sin dato = se descarta (a diferencia de `aparcamientos`)

El enunciado pedía explícitamente "descarta estaciones/horas sin dato": un
registro cuyo campo de conteo correspondiente a su `mode` venga a `null` o
sea negativo se rechaza entero, a diferencia de `aparcamientos` (donde
compartir la ocupación en tiempo real es voluntaria y un `null` es un estado
válido). Aquí no hay ninguna señal en la fuente de que un conteo ausente sea
legítimo — ambos CSV de origen siempre traen la columna de conteo rellena
para las filas reales, verificado en la muestra real. Un conteo de `0` sí es
válido y se acepta (una estación real sin ningún peatón/bicicleta contado en
esa hora).

## Agregación Silver → Gold: `(station_id, mode, fecha, hora)`, con `total_count` como magnitud principal

Gold agrupa por estación, modo y hora (mismo criterio de clave de tres
componentes que `calidad_aire`/`meteorologia`, por la misma razón: mezclar
peatones y bicicletas en un único agregado no tendría sentido). A diferencia
de `trafico`/`calidad_aire` (donde `avg_value` es la magnitud principal
porque las lecturas son continuas), aquí `total_count` (suma) es la
magnitud principal: la fuente publica como mucho una fila por
estación+hora, así que un conteo horario es, por construcción, un total.
`samples_count`/`avg_count`/`max_count`/`min_count` se conservan también
para que un consumidor pueda detectar reingestas (`samples_count > 1`) sin
que queden ocultas en el total.

## Tests

25 tests nuevos en `procesamiento/tests/` (`test_aforos_peatones_bicicletas_transform.py`,
`test_aforos_peatones_bicicletas_aggregate.py`), más un fixture de 13
registros Bronze (`tests/fixtures/aforos_peatones_bicicletas_bronze_sample.json`:
5 lecturas reales de
`ingesta/capturas/samples/aforos_peatones_bicicletas_madrid_sample.json`
—3 estaciones de peatones + 2 de bicicletas— + 8 que violan cada regla de
rechazo por turnos: `station_id`/`mode` ausente o inválido, `measured_at`/
`ingested_at` ausente o sin zona horaria, conteo ausente y conteo negativo).
Suite completa del proyecto en verde: 267 tests de `ingesta` (sin cambios) +
191 de `procesamiento` (166 previos + 25 nuevos),
`python3 -m unittest discover -s procesamiento/tests -t .` y
`-s ingesta/tests -t .`.

Igual que en las tareas 041/046/047/048/049/050/053, `ge_suite.py` y los dos
`glue_*.py` de este dataset importan `pyspark`/`great_expectations`/
`awsglue` a nivel de módulo y **no se han podido importar ni ejecutar en
esta sesión** (mismo motivo: disco compartido muy limitado en esta EC2) —
ningún test los importa a propósito
(`procesamiento/silver_gold/aforos_peatones_bicicletas/__init__.py` solo
expone `transform`/`aggregate`).

## Terraform (`infra/terraform/glue.tf`, extendido)

Sin aplicar. Se añadió un bloque completo para este dataset (rol IAM propio
`glue_aforos_peatones_bicicletas`, acotado por prefijo
`bronze/aforos_peatones_bicicletas/*` ·
`silver/aforos_peatones_bicicletas/*` ·
`gold/aforos_peatones_bicicletas_por_estacion_modo_hora/*`, incluidos desde
el principio los dos huecos de permisos que las tareas 051/052 tuvieron que
descubrir y arreglar a posteriori para los seis primeros datasets —
`s3:PutObject` sobre `_quality_reports/aforos_peatones_bicicletas/*` y sobre
el marcador `aforos_peatones_bicicletas_por_estacion_modo_hora_$folder$`—,
más el catálogo de sus dos tablas Silver/Gold; dos `aws_glue_job`,
Bronze→Silver y Silver→Gold), **sin tocar** los bloques de los siete
datasets anteriores ni compartir su rol IAM. La tabla Silver del catálogo
declara dos `partition_keys` (`fecha`/`hora`, el patrón horario estándar).
`data.archive_file.procesamiento_source` no necesitó ningún cambio: ya
empaquetaba todo `procesamiento/` (salvo `tests/`), así que el subpaquete
nuevo se incluye automáticamente en el artefacto de librería compartido.

`terraform validate` limpio, verificado con `terraform init -backend=false`
(sin backend real, sin credenciales AWS) tras limpiar los `__pycache__/*.pyc`
generados por `python3 -m unittest` (mismo problema preexistente de
`lambda.tf` documentado en doc/046, no introducido por esta tarea).
`terraform fmt -check -recursive` limpio. No se ha ejecutado `terraform
plan`/`apply` contra la cuenta real. `.terraform/`, `.terraform.lock.hcl` y
`backend.hcl` (copia local de `backend.hcl.example`, ya cubierta por
`.gitignore`) generados por `terraform init`/`validate` se eliminaron al
terminar — nada de esto se commitea.

## `procesamiento/README.md`: actualizado para reflejar el octavo dataset

Título, párrafo introductorio, estructura de código y las secciones de
Great Expectations, "Qué no se ha podido ejecutar", Terraform y "Relevante
para tareas futuras" se actualizaron para cubrir los ocho datasets. Se
añadió una sección "Octavo dataset: `aforos_peatones_bicicletas`" con el
razonamiento completo del colapso de dos campos de conteo en uno y de la
puerta de calidad "sin dato = se descarta".

## Restricciones respetadas

- Alcance limitado a `aforos_peatones_bicicletas` — no se ha tocado ningún
  otro subpaquete de `procesamiento/silver_gold/`.
- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales.
- No se ha instalado `pyspark`/`great_expectations` en esta EC2.
- No se ha procesado ningún dato real de Bronze: toda la verificación usa
  el fixture de ejemplo, construido a partir de la muestra real ya
  commiteada por `ingesta/capturas/samples/aforos_peatones_bicicletas_madrid_sample.json`.
- No se ha dejado nada programado (cron, systemd timer, bucle) en esta EC2.

## Relevante para tareas futuras

- El patrón fijado por la 041 ya se ha replicado siete veces
  (041→046→047→048→049→050→053→054): un subpaquete `silver_gold/<dataset>/`
  con `transform.py`/`aggregate.py` (Python puro, testable)/`ge_suite.py`/
  `glue_*.py`, más `geo.py` **solo si la fuente lo necesita** (ninguno de
  los últimos siete datasets lo tiene), más un bloque en `glue.tf` con su
  propio rol IAM.
- `aforos_peatones_bicicletas` es el primer dataset del patrón donde Bronze
  trae **varios campos numéricos mutuamente excluyentes según una etiqueta
  del propio registro** (`pedestrian_count`/`bicycle_count` según `mode`),
  que Silver colapsa en un único campo (`count`) vía una tabla
  `dict[etiqueta, nombre_de_campo]` (`transform.COUNT_FIELD_BY_MODE`). Si
  una tarea futura añade un dataset con la misma forma, el criterio a
  replicar es este — distinto del `dict[etiqueta, rango]` de
  `calidad_aire`/`meteorologia` (que mapean a un rango de plausibilidad, no
  a un nombre de campo). Como `mode` solo admite un catálogo fijo de dos
  valores, su `ge_suite.py` no necesita ninguna columna auxiliar de Spark
  (`expect_column_values_to_be_in_set` basta de forma nativa) — a diferencia
  de `calidad_aire`/`meteorologia`, cuyos catálogos de etiquetas son
  abiertos y sí necesitan una columna auxiliar calculada en
  `glue_bronze_to_silver.py`.
- Antes de aplicar cualquiera de los ocho bloques de infraestructura de
  Glue: smoke-test de los ocho `ge_suite.py` en un Glue Studio Notebook
  real, y revisar si `great_expectations==0.18.19` sigue siendo la versión
  adecuada en el momento de aplicar (misma pendiente que dejaron las tareas
  041/046/047/048/049/050/053, ahora aplica a ocho datasets).
- Esta tarea incluyó desde el principio, en la política IAM del rol
  `glue_aforos_peatones_bicicletas`, los dos statements de permisos
  (`_quality_reports/*` y el marcador `_$folder$` de Gold) que las tareas
  051/052 tuvieron que descubrir empíricamente y añadir a posteriori para
  los seis primeros datasets — cualquier dataset futuro del patrón debería
  copiar la política de `aforos_peatones_bicicletas`/`ruido`/`meteorologia`
  (ya completa) en vez de la de `trafico` tal como quedó en la tarea 041
  original.
