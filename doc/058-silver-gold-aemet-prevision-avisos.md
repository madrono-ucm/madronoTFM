# 058 — Silver/Gold: previsión y avisos de AEMET (duodécimo dataset del patrón 041)

## Qué se implementó

`procesamiento/silver_gold/aemet_prevision_avisos/` (`transform.py`,
`aggregate.py`, `ge_suite.py`, `glue_bronze_to_silver.py`,
`glue_silver_to_gold.py`, `__init__.py`), replicando el patrón fijado por la
tarea 041 y ya extendido en las tareas 046-057 (ver `procesamiento/README.md`).
Fuente: `ingesta/capturas/aemet_prevision_avisos.py` (previsión diaria por
municipio y avisos meteorológicos vigentes de AEMET OpenData, ver doc/018).
Sin `terraform apply`, alcance limitado a este dataset.

## Diferencia real frente a todo el resto del patrón: dos formas de dato sin ningún campo en común

A diferencia de los once datasets anteriores (siempre un único esquema
Silver por dataset, aunque varíe entre serie temporal numérica, catálogo de
hechos discretos o dos `mode` bajo un mismo esquema como `bluesky_menciones`),
`ingesta/capturas/aemet_prevision_avisos.py` ya escribe, en producción, **dos**
Bronze datasets con nombre propio (`DATASET_PREDICCION = "aemet_prevision"`,
`DATASET_AVISOS = "aemet_avisos"`) con esquemas que no comparten ni un solo
campo de negocio. Este subpaquete trata ambas formas como dos flujos
independientes de principio a fin — dos puertas de calidad, dos
normalizadores, dos agregaciones, dos suites de GX, dos pares de prefijos
S3 — pero comparte **un único** rol IAM y **un único** par de jobs de Glue
(Bronze→Silver, Silver→Gold), tal como pedía el enunciado ("job de Glue
x2", no cuatro), porque ambas formas comparten productor, credencial
(`AEMET_API_KEY`) y cadencia real de scheduling.

## Desviación deliberada frente al enunciado: prefijos S3 reales, no el prefijo único sugerido

El enunciado sugería acotar el rol IAM a un único prefijo
`aemet_prevision_avisos/*` en las tres capas. Los nombres de dataset Bronze
ya están fijados en producción por la propia ingesta (`"aemet_prevision"`/
`"aemet_avisos"`), así que un rol acotado a ese prefijo combinado no tendría
permiso para leer ningún dato Bronze real — se documentó esta desviación en
detalle en `transform.py` y `infra/terraform/glue.tf`, y se usaron los
prefijos reales: `bronze/aemet_prevision/*`/`bronze/aemet_avisos/*`,
`silver/aemet_prevision/*`/`silver/aemet_avisos/*`,
`gold/aemet_prevision_por_municipio_leadtime/*`/
`gold/aemet_avisos_por_zona_fecha_nivel/*`. El subpaquete de
`procesamiento/` sí se llama `aemet_prevision_avisos` (agrupa el código de
ambas formas, mismo productor/enunciado).

## Puerta de calidad

**Previsión**: `municipio_code` no nulo, `valid_date` parseable y no ya
pasada respecto a `ingested_at` (el mismo día, `leadtime_days == 0`, sí es
válido — la previsión "de hoy" es un dato legítimo y frecuente), y rangos
plausibles de `temperature_max_c`/`temperature_min_c` (`[-20, 50]`, mismo
rango que `meteorologia`) y `precipitation_probability_pct` (`[0, 100]`).
Silver normaliza a `float` los campos numéricos que Bronze conserva tal
como los publica AEMET (algunos como `str`, p.ej. `"75"` — ver
`ingesta/README.md`), para que `aggregate.py` no tenga que adivinar el tipo
campo a campo.

**Avisos**: `identifier` (clave natural para deduplicar reingestas),
`zone`, `phenomenon` y `effective_from` parseable no nulos, y `level`
dentro del catálogo cerrado de AEMET (`amarillo`/`naranja`/`rojo`).

## Agregación Silver → Gold (decidida por el enunciado, implementada tal cual)

**Previsión: `(municipio_code, leadtime_days)`.** `leadtime_days` (`valid_date
- ingested_at.date()`) agrupa previsiones de días de calendario distintos
capturadas en momentos distintos bajo el mismo horizonte de antelación. Cada
fila agrega `avg`/`max` de `temperature_max_c`, `avg`/`min` de
`temperature_min_c` y `avg`/`max` de `precipitation_probability_pct`.

**Avisos: `(zone, fecha, level)`**, con `fecha` = día de `effective_from`
(cuándo empieza a estar vigente el aviso, no cuándo se capturó — mismo
criterio que `cartelera_cines_estrenos`/`agenda_eventos`/`bluesky_menciones`).
`alerts_count` (número de `identifier` distintos) es la magnitud principal;
`samples_count` incluye reingestas del mismo aviso vigente capturado varias
veces.

## Tests

37 tests nuevos (`test_aemet_prevision_avisos_transform.py`,
`test_aemet_prevision_avisos_aggregate.py`), fixtures construidos a partir
de las muestras reales ya commiteadas (`aemet_prevision_bronze_sample.json`:
3 días reales + 8 sintéticos que violan cada regla de rechazo por turnos;
`aemet_avisos_bronze_sample.json`: 1 aviso real + 7 sintéticos). Suite
completa en verde: 267 tests de `ingesta` (sin cambios) + 300 de
`procesamiento` (263 previos + 37 nuevos).

`AEMET_API_KEY` sigue sin estar disponible como variable de entorno en esta
EC2 de desarrollo (mismo motivo que las tareas 038/045): se intentó
regenerar la muestra local en esta sesión y falló explícitamente con el
mismo mensaje ya documentado por esas tareas, así que los fixtures se
construyeron a partir de las muestras `is_mock: true` ya commiteadas, sin
ningún cambio.

`ge_suite.py` y los dos `glue_*.py` no se han podido importar/ejecutar en
esta EC2 (sin `pyspark`/`great_expectations` instalados, mismo motivo que
el resto del patrón); ningún test los importa. El informe de Great
Expectations se escribe directamente a S3 vía `boto3` (dos ficheros por
ejecución, uno por forma de dato), no con `saveAsTextFile` (bug de
producción de la tarea 051).

## Terraform (`infra/terraform/glue.tf`)

Bloque completo añadido: rol IAM propio `glue_aemet_prevision_avisos`
(acotado a los DOS prefijos Bronze/Silver reales y las DOS tablas Gold, no
uno de cada); catálogo de 4 tablas Silver/Gold (`aemet_prevision`/
`aemet_avisos` en Silver, `aemet_prevision_por_municipio_leadtime`/
`aemet_avisos_por_zona_fecha_nivel` en Gold); 2 `aws_glue_job` (uno por
transformación, cada uno procesando ambas formas de dato internamente). Sin
tocar los once bloques anteriores.

`terraform validate` limpio (`terraform init -backend=false`, tras limpiar
`__pycache__`); `terraform fmt -check -diff glue.tf` sin diferencias. No se
ha ejecutado `terraform plan`/`apply`. Artefactos de `terraform init`
eliminados al terminar (ya cubiertos por `.gitignore`).

## `procesamiento/README.md`

Actualizado: título, párrafo introductorio, estructura de código, listas de
fixtures/tests, sección "Duodécimo dataset: `aemet_prevision_avisos`" con
el razonamiento completo, y bullets nuevos en "Qué no se ha podido
ejecutar", Terraform y "Relevante para tareas futuras" (patrón de "un
productor, varios Bronze datasets con nombre propio" y la desviación de
prefijo documentada).

## Restricciones respetadas

Alcance limitado a `aemet_prevision_avisos`; sin `terraform apply` ni
comandos `aws`; sin instalar `pyspark`/`great_expectations`; sin procesar
datos reales de Bronze (solo los fixtures, basados en las muestras reales
ya commiteadas); sin nada programado (cron/systemd/bucle) en esta EC2; sin
modificar `ingesta/capturas/aemet_prevision_avisos.py`.
