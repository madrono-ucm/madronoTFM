# 053 — Silver/Gold: contaminación acústica (séptimo dataset del patrón 041)

## Qué se implementó

`procesamiento/silver_gold/ruido/`, replicando el patrón que la tarea 041
fijó con tráfico y que las tareas 046/047/048/049/050 ya replicaron con
transporte público EMT, BiciMAD, aparcamientos rotacionales, calidad del
aire y meteorología (ver `procesamiento/README.md`): `transform.py`
(Bronze→Silver, puerta de calidad, Python puro), `aggregate.py`
(Silver→Gold, Python puro, fuente de verdad documental/de test),
`ge_suite.py` (Great Expectations) y `glue_bronze_to_silver.py`/
`glue_silver_to_gold.py` (entry points reales de Glue). Fuente:
`ingesta/capturas/ruido_madrid.py` (valores diarios de la Red Fija del
SIVCA, ver doc/007). **Alcance: solo este dataset y solo código/
infraestructura, sin `terraform apply`** — mismo criterio que las tareas
041/046/047/048/049/050, el resto de subpaquetes de `silver_gold/` no se ha
tocado.

## Sin `geo.py`

`ingesta/capturas/ruido_madrid.py` (`normalize_record`) ya entrega
`location.lat`/`location.lon` en WGS84 (`_parse_grouped_decimal` sobre el
catálogo de estaciones acústicas de datos.madrid.es) y `location.altitude_m`
resuelto — no hace falta ninguna reproyección.

## Diferencia real frente al resto del patrón: granularidad diaria, no horaria

La Red Fija del SIVCA no publica ningún feed en tiempo real: solo un
agregado diario por estación y periodo horario (`D`iurno, `E`vespertino,
`N`octurno, `T`otal), con LAeq y los percentiles L1/L10/L50/L90/L99. No hay
ningún campo de hora que agregar. Consecuencias, decididas explícitamente en
vez de forzar el patrón `(id, fecha, hora)`:

- **Silver se particiona solo por `fecha`** (derivada de `measured_date`),
  sin `hora` — a diferencia de los seis datasets anteriores.
- **Gold agrupa por `(station_id, period, measured_date)`**, no por
  `(id, fecha, hora)`.
- La puerta de calidad usa **un único rango de plausibilidad en dB**
  (`transform.PLAUSIBLE_DB_RANGE = (20.0, 120.0)`) para los seis campos
  numéricos (`laeq_db`, `l1_db`..`l99_db`), no una tabla por etiqueta como
  `calidad_aire.PLAUSIBLE_MAX_BY_POLLUTANT`/
  `meteorologia.PLAUSIBLE_RANGE_BY_MAGNITUDE`: aquí todos los campos son
  niveles sonoros en la misma unidad, no magnitudes heterogéneas. Un
  registro sin `laeq_db` (columna `LAeq` vacía en la fuente) se rechaza
  entero ("descarta periodos sin dato", pedido por el enunciado); los
  percentiles pueden ser `null` de forma independiente sin rechazar el
  registro.

## Decisión de agregación Silver → Gold: media móvil de 7 días de LAeq

El enunciado pedía decidir con criterio propio qué aporta Gold a esta
granularidad diaria, sin forzar una agregación horaria que la fuente no
soporta. Se descartó un simple paso a través (no añadiría ningún cálculo) y
se optó por una **media móvil de 7 días naturales de LAeq**
(`laeq_rolling_7d_avg_db`/`laeq_rolling_7d_days`, por cada `(station_id,
period)`), con ventana de **calendario** (día actual − 6 hasta día actual,
no "últimas 7 lecturas") para que un hueco de fin de semana/festivo (la
fuente no publica esos días) reduzca `laeq_rolling_7d_days` en vez de
desplazar la ventana. En Spark se implementa con
`Window.partitionBy("station_id", "period").orderBy("date_epoch_days").rangeBetween(-6, 0)`
sobre una columna auxiliar de días desde época, no con `rowsBetween`, por la
misma razón.

Se documenta a propósito, en el docstring de `aggregate.py`, una
imprecisión física conocida y aceptada: tanto `avg_laeq_db` (cuando hay más
de una lectura Silver el mismo día) como la media móvil de 7 días usan una
media aritmética simple de valores en dB, no el promedio energéticamente
correcto (que requeriría revertir a presión sonora lineal, promediar y
volver a dB). Mismo criterio de simplicidad que el resto del patrón
(`calidad_aire`/`trafico`/`meteorologia` también promedian sus magnitudes
con media aritmética simple); en el caso normal (una sola lectura Silver por
estación+periodo+día) `avg_laeq_db` coincide exactamente con el valor
publicado por la fuente, así que el error solo aparece en la media móvil de
varios días. Queda documentado como pendiente si una tarea futura necesita
precisión acústica exacta.

## Tests

22 tests nuevos en `procesamiento/tests/` (`test_ruido_transform.py`,
`test_ruido_aggregate.py`), más un fixture de 28 registros Bronze
(`tests/fixtures/ruido_bronze_sample.json`: las 20 lecturas reales de
`ingesta/capturas/samples/ruido_madrid_sample.json` —5 estaciones × 4
periodos— + 8 que violan cada regla por turnos: `station_id`/`period`/
`measured_date`/`ingested_at` ausentes, `ingested_at` sin zona horaria,
`laeq_db` ausente, `laeq_db` fuera de rango, y un percentil fuera de rango
que no descarta el LAeq válido del mismo registro). Los tests de
`aggregate.py` cubren específicamente el nuevo comportamiento: dedupe por
reingesta del mismo día, ventana de calendario de 7 días con huecos, y que
la media móvil no mezcla periodos distintos de la misma estación. Suite
completa del proyecto en verde: 267 tests de `ingesta` (sin cambios) + 166
de `procesamiento` (144 previos + 22 nuevos de `ruido`),
`python3 -m unittest discover -s procesamiento/tests -t .` y
`-s ingesta/tests -t .`.

Igual que en las tareas 041/046/047/048/049/050, `ge_suite.py` y los dos
`glue_*.py` de este dataset importan `pyspark`/`great_expectations`/
`awsglue` a nivel de módulo y **no se han podido importar ni ejecutar en
esta sesión** (mismo motivo: disco compartido muy limitado en esta EC2) —
ningún test los importa a propósito
(`procesamiento/silver_gold/ruido/__init__.py` solo expone
`transform`/`aggregate`).

## Terraform (`infra/terraform/glue.tf`, extendido)

Sin aplicar. Se añadió un bloque completo para este dataset (rol IAM propio
`glue_ruido`, acotado por prefijo `bronze/ruido/*` · `silver/ruido/*` ·
`gold/ruido_por_estacion_periodo_fecha/*`, incluidos desde el principio los
dos huecos de permisos que las tareas 051/052 tuvieron que descubrir y
arreglar a posteriori para los seis datasets anteriores —
`s3:PutObject` sobre `_quality_reports/ruido/*` y sobre el marcador
`ruido_por_estacion_periodo_fecha_$folder$`—, más el catálogo de sus dos
tablas Silver/Gold; dos `aws_glue_job`, Bronze→Silver y Silver→Gold),
**sin tocar** los bloques de los seis datasets anteriores ni compartir su
rol IAM. La tabla Silver del catálogo declara una única `partition_keys`
(`fecha`, sin `hora`) — la única diferencia estructural frente a las tablas
Silver del resto del patrón. `data.archive_file.procesamiento_source` no
necesitó ningún cambio: ya empaquetaba todo `procesamiento/` (salvo
`tests/`), así que el subpaquete nuevo se incluye automáticamente en el
artefacto de librería compartido.

`terraform validate` limpio, verificado con `terraform init -backend=false`
(sin backend real, sin credenciales AWS) tras limpiar los `__pycache__/*.pyc`
generados por `python3 -m unittest` (mismo problema preexistente de
`lambda.tf` documentado en doc/046, no introducido por esta tarea).
`terraform fmt -check -recursive` limpio. No se ha ejecutado `terraform
plan`/`apply` contra la cuenta real. `.terraform/`, `.terraform.lock.hcl` y
`backend.hcl` (copia local de `backend.hcl.example`, ya cubierta por
`.gitignore`) generados por `terraform init`/`validate` se eliminaron al
terminar — nada de esto se commitea.

## `procesamiento/README.md`: actualizado para reflejar el séptimo dataset

Título, párrafo introductorio, estructura de código y las secciones de
Great Expectations, "Qué no se ha podido ejecutar", Terraform y "Relevante
para tareas futuras" se actualizaron para cubrir los siete datasets. Se
añadió una sección "Séptimo dataset: `ruido`" con el razonamiento completo
de la granularidad diaria, el rango único de plausibilidad y la decisión de
la media móvil de 7 días.

## Restricciones respetadas

- Alcance limitado a `ruido` — no se ha tocado
  `procesamiento/silver_gold/trafico/`,
  `procesamiento/silver_gold/transporte_publico_emt/`,
  `procesamiento/silver_gold/bicimad/`,
  `procesamiento/silver_gold/aparcamientos/`,
  `procesamiento/silver_gold/calidad_aire/` ni
  `procesamiento/silver_gold/meteorologia/`.
- No se ha ejecutado `terraform apply` ni ningún comando `aws` con efectos
  reales.
- No se ha instalado `pyspark`/`great_expectations` en esta EC2.
- No se ha procesado ningún dato real de Bronze: toda la verificación usa
  el fixture de ejemplo, construido a partir de la muestra real ya
  commiteada por `ingesta/capturas/samples/ruido_madrid_sample.json`.
- No se ha dejado nada programado (cron, systemd timer, bucle) en esta EC2.

## Relevante para tareas futuras

- El patrón fijado por la 041 ya se ha replicado seis veces
  (041→046→047→048→049→050→053): un subpaquete `silver_gold/<dataset>/` con
  `transform.py`/`aggregate.py` (Python puro, testable)/`ge_suite.py`/
  `glue_*.py`, más `geo.py` **solo si la fuente lo necesita** (ninguno de
  los seis últimos datasets lo tiene), más un bloque en `glue.tf` con su
  propio rol IAM.
- `ruido` es el primer dataset del patrón cuya fuente ya es diaria, no
  horaria: Silver se particiona solo por `fecha` y Gold agrupa por
  `(station_id, period, measured_date)`. Si una tarea futura añade un octavo
  dataset con la misma granularidad diaria, el criterio a replicar es este
  (no inventar una `hora` que la fuente no tiene), y considerar si aporta
  valor una media móvil de calendario similar a
  `ruido.aggregate.ROLLING_WINDOW_DAYS`.
- `ruido.transform.PLAUSIBLE_DB_RANGE` es el primer rango de plausibilidad
  del patrón compartido por **varios campos del mismo registro** (los seis
  niveles sonoros) en vez de una tabla por etiqueta como
  `calidad_aire.PLAUSIBLE_MAX_BY_POLLUTANT`/
  `meteorologia.PLAUSIBLE_RANGE_BY_MAGNITUDE` — el criterio a replicar
  cuando varios campos comparten unidad/escala es un único rango simple, no
  una tabla, reservando la tabla `dict[etiqueta, rango]` para cuando un
  único campo (`value`) representa magnitudes distintas según otro campo
  del registro.
- La media móvil de `ruido` usa una media aritmética simple de dB, no el
  promedio energéticamente correcto (log-sum-exp de presión sonora lineal)
  — imprecisión aceptada y documentada en `aggregate.py`, pendiente para una
  tarea futura que necesite precisión acústica exacta en vez de una
  aproximación consistente con el resto del patrón.
- Antes de aplicar cualquiera de los siete bloques de infraestructura de
  Glue: smoke-test de los siete `ge_suite.py` en un Glue Studio Notebook
  real (el de `ruido` necesita además confirmar que la ventana
  `Window.rangeBetween` de `glue_silver_to_gold.py` produce la misma media
  móvil que `aggregate.py` — a diferencia de las columnas auxiliares de GX
  del resto de datasets, aquí no es una expectation sino la propia lógica de
  Gold), y revisar si `great_expectations==0.18.19` sigue siendo la versión
  adecuada en el momento de aplicar (misma pendiente que dejaron las tareas
  041/046/047/048/049/050, ahora aplica a siete datasets).
- Esta tarea incluyó desde el principio, en la política IAM del rol
  `glue_ruido`, los dos statements de permisos (`_quality_reports/*` y el
  marcador `_$folder$` de Gold) que las tareas 051/052 tuvieron que
  descubrir empíricamente y añadir a posteriori para los seis datasets
  anteriores — cualquier dataset futuro del patrón debería copiar la
  política de `ruido`/`meteorologia` (ya completa) en vez de la de
  `trafico` tal como quedó en la tarea 041 original (que necesitó los
  parches de las tareas 051/052).
