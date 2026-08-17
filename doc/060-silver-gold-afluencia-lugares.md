# 060 — Silver/Gold: afluencia de lugares (decimocuarto dataset del patrón 041)

## Qué se implementó

`procesamiento/silver_gold/afluencia_lugares/` (`transform.py`,
`aggregate.py`, `ge_suite.py`, `glue_bronze_to_silver.py`,
`glue_silver_to_gold.py`, `__init__.py`), replicando el patrón fijado por la
tarea 041 y ya extendido en las tareas 046-059 (ver `procesamiento/README.md`).
Fuente: `ingesta/capturas/afluencia_lugares_madrid.py` (afluencia estimada,
tipo Google, de una muestra de lugares conocidos de Madrid vía la librería
de terceros `populartimes`, ver doc/012). Sin `terraform apply`, alcance
limitado a este dataset.

## Sin `geo.py`

`normalize_record` ya entrega `location.lat`/`location.lon` en WGS84
(resuelto por la propia API oficial "Find Place" de Google) — no hace falta
ninguna reproyección; `lat`/`lon` se aplanan a columnas de primer nivel en
Silver, mismo criterio que `agenda_eventos` (tarea 056).

## Este dataset sigue bloqueado: sin `GOOGLE_MAPS_API_KEY` real

Como documenta doc/012, no existe ninguna forma autónoma de dar de alta una
cuenta de Google Cloud en este pipeline, así que tanto la muestra local
como cualquier dato en Bronze siguen siendo `"is_mock": true`. Esto no ha
impedido implementar ni verificar el subpaquete: toda la lógica se ha
verificado contra el fixture mock, construido a partir de los 5 registros
reales de `ingesta/capturas/samples/afluencia_lugares_madrid_sample.json`
(incluido el caso real "Plaza Mayor", con `live_pct`/`typical_by_hour`
ambos `null`). El código queda listo para funcionar tal cual el día que
haya una clave real.

## Diferencia real frente al resto del patrón: dos magnitudes independientes, ambas opcionales

Cada registro puede traer `live_pct` (afluencia en vivo, 0-100) y
`typical_by_hour` (patrón habitual por día de la semana, `dict[día_es,
list[24 valores]]`), cada una legítimamente `null` por separado (Google sin
datos suficientes, o el handler Lambda de patrón típico que fuerza
`live_pct=None` a propósito, ver doc/012). `transform.validate_record` no
descarta un registro solo por tener cualquiera de las dos a `null` — cuando
están presentes, valida que cada valor esté en `0-100`.

## Agregación Silver → Gold (decidida por el enunciado, implementada tal cual): `(place_id, fecha, hora)`

`live_pct` medio del bucket cuando esté disponible, junto con el valor de
`typical_by_hour` correspondiente a ese día de la semana/hora, tomado del
propio registro. Como todos los registros de un bucket comparten, por
construcción de la clave, el mismo día de la semana y hora, ese valor
típico es el mismo para todos salvo que a alguno le falte
`typical_by_hour` — por eso se promedia (`typical_pct`) igual que
`live_pct` (`avg_live_pct`), en vez de tomar solo el primero. Un lugar sin
ningún dato en un bucket (caso "Plaza Mayor") sigue produciendo una fila de
Gold con ambas métricas a `null`, no se descarta.

## Tests

26 tests nuevos (`test_afluencia_lugares_transform.py`,
`test_afluencia_lugares_aggregate.py`), fixture de 11 registros
(`afluencia_lugares_bronze_sample.json`: los 5 lugares reales de la muestra
existente, todos válidos, + 6 sintéticos que violan cada regla de rechazo
por turnos: `place_id` ausente, `name` ausente, `captured_at`
ausente/sin zona horaria, `live_pct` fuera de rango, un valor de
`typical_by_hour` fuera de rango). Suite completa del proyecto en verde:
267 tests de `ingesta` (sin cambios) + 352 de `procesamiento` (326 previos +
26 nuevos).

`ge_suite.py` y los dos `glue_*.py` no se han podido importar/ejecutar en
esta EC2 (sin `pyspark`/`great_expectations` instalados, mismo motivo que
el resto del patrón); ningún test los importa. El informe de Great
Expectations se escribe directamente a S3 vía `boto3`, no con
`saveAsTextFile` (bug de producción de la tarea 051), tal como pedía
explícitamente el enunciado de esta tarea.

`typical_by_hour` no tiene una expectation nativa de GX para "cada valor de
cada array anidado de un struct está en rango": se aproxima con dos
columnas auxiliares (`typical_by_hour_min_value`/`typical_by_hour_max_value`)
calculadas en `glue_bronze_to_silver.py` aplanando los 7 arrays del struct,
mismo criterio que las columnas auxiliares de `calidad_aire`/`meteorologia`/
`cams_calidad_aire`. En Silver, `typical_by_hour` se modela como un
`StructType` de 7 campos `array<int>` (uno por día de la semana) en vez de
un `MapType` genérico — el conjunto de días es fijo y conocido de antemano,
así que un struct es más natural para Parquet/Athena. `glue_silver_to_gold.py`
necesita indexar ese struct por el día de la semana de cada fila (un valor
que no se conoce hasta tiempo de ejecución); Spark no permite indexar un
campo de struct dinámicamente por el valor de otra columna, así que se
aproxima con una cadena `when/otherwise` por día, equivalente a
`aggregate._typical_value_for`.

## Terraform (`infra/terraform/glue.tf`)

Bloque completo añadido: rol IAM propio `glue_afluencia_lugares` (acotado
por prefijo `bronze/afluencia_lugares/*` · `silver/afluencia_lugares/*` ·
`gold/afluencia_lugares_por_lugar_fecha_hora/*`, incluidos desde el
principio los dos statements de permisos que las tareas 051/052 tuvieron
que añadir a posteriori en los seis primeros datasets; catálogo de sus dos
tablas Silver/Gold; dos `aws_glue_job`), sin tocar los trece bloques
anteriores. Silver particiona por `fecha`/`hora` (derivadas de
`ingested_at`, único timestamp de este dataset); Gold particiona por
`date`.

`terraform validate` limpio (`terraform init -backend=false`, tras limpiar
`__pycache__`); `terraform fmt -check -diff glue.tf` sin diferencias. No se
ha ejecutado `terraform plan`/`apply`. Artefactos de `terraform init`
eliminados al terminar (ya cubiertos por `.gitignore`).

## `procesamiento/README.md`

Actualizado: título, párrafo introductorio, estructura de código, listas de
fixtures/tests, sección "Decimocuarto dataset: `afluencia_lugares`" con el
razonamiento completo, y bullets nuevos en "Qué no se ha podido ejecutar",
Terraform y "Relevante para tareas futuras" — en particular, documentando
el criterio de dos magnitudes numéricas independientes y opcionales dentro
del mismo registro, y que este dataset sigue sin ningún precedente de
ejecución contra la API real de Google.

## Restricciones respetadas

Alcance limitado a `afluencia_lugares`; sin `terraform apply` ni comandos
`aws`; sin instalar `pyspark`/`great_expectations`; sin procesar datos
reales de Bronze (solo el fixture, basado en la muestra mock existente);
sin nada programado (cron/systemd/bucle) en esta EC2; sin modificar
`ingesta/capturas/afluencia_lugares_madrid.py`; no se ha intentado obtener
ni configurar ninguna `GOOGLE_MAPS_API_KEY`.
