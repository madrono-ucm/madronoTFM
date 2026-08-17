# 059 — Silver/Gold: previsión de calidad del aire CAMS (decimotercer dataset del patrón 041)

## Qué se implementó

`procesamiento/silver_gold/cams_calidad_aire/` (`transform.py`,
`aggregate.py`, `ge_suite.py`, `glue_bronze_to_silver.py`,
`glue_silver_to_gold.py`, `__init__.py`), replicando el patrón fijado por la
tarea 041 y ya extendido en las tareas 046-058 (ver
`procesamiento/README.md`). Fuente: `ingesta/capturas/cams_calidad_aire_madrid.py`
(previsión horaria de calidad del aire a 4 días vista de Copernicus CAMS
para Madrid, ver doc/019 y doc/045). Sin `terraform apply`, alcance limitado
a este dataset.

## Sin `geo.py`

`normalize_forecast_file` ya entrega el punto de rejilla más cercano a
Madrid en WGS84 (tras corregir en doc/045 la convención `[0, 360)` de
longitud del NetCDF real) — no hace falta ninguna reproyección.

## Diferencia real frente al resto del patrón: previsión con horizonte, no medida del instante actual

Cada registro es un valor *previsto* para un instante futuro
(`valid_datetime`), calculado a partir de una corrida de modelo diaria
(`forecast_issued_at`) con un horizonte de antelación en horas
(`leadtime_hour`) — misma naturaleza de dato que `aemet_prevision_avisos`
(tarea 058), ambas diseñadas con un criterio deliberadamente similar tal
como pedía el enunciado. Diferencias con AEMET: el horizonte se mide en
horas, no en días, y no hace falta ninguna regla de "ya pasado" — CAMS
siempre pide `leadtime_hour >= 0` en la petición a la API, así que
`valid_datetime` nunca es anterior a `forecast_issued_at` por construcción
(a diferencia de AEMET, que sí puede reemitir una previsión "vieja" en un
lote y necesita rechazar `valid_date_already_passed`).

## Puerta de calidad

`validate_record` exige campos clave no nulos (`pollutant`,
`pollutant_code`, `valid_datetime`/`forecast_issued_at` parseables y
timezone-aware, `leadtime_hour` no negativo, `captured_at`→`ingested_at`
timezone-aware) y `value` dentro de un rango plausible por contaminante
(`PLAUSIBLE_MAX_BY_POLLUTANT`). Esta tabla reutiliza el mismo criterio y
órdenes de magnitud que `calidad_aire.PLAUSIBLE_MAX_BY_POLLUTANT` (cota laxa
para atrapar solo valores corruptos, no un límite legal), pero está
definida como su propia tabla (etiquetas `NO2`/`NO`/`SO2`/`O3`/`PM2.5`/
`PM10`/`polvo`, un conjunto distinto al de `calidad_aire`) para no acoplar
ambos subpaquetes por un detalle que podría divergir con el tiempo.
`is_mock` (presente en Bronze) no se propaga a Silver — dato de procedencia
de la captura, no una dimensión de negocio, mismo criterio que
`aemet_prevision_avisos`.

## Agregación Silver → Gold (decidida por el enunciado, implementada tal cual): `(pollutant, fecha_validez)`

`fecha_validez` se deriva de `valid_datetime` (el día que predice la fila,
no el horizonte de antelación `leadtime_hour`, y no el día de la corrida
`forecast_issued_at`) — responde "valor medio/máximo previsto ese día para
ese contaminante", tal como pedía el enunciado. Deliberadamente **no** es
`leadtime_days`, la clave que sí usa `aemet_prevision_avisos` para su
agregación de previsión: son dos preguntas distintas y legítimas sobre el
mismo tipo de dato ("¿qué tan certera es la previsión a N horas vista?" vs.
"¿qué se predijo en conjunto para tal día concreto?"); esta tarea pide
explícitamente la segunda. `leadtime_hours` (lista de horizontes distintos
presentes en el bucket) se conserva en cada fila sin ser la clave de
agrupación, para no perder esa información. Cada fila agrega
`samples_count`, `avg_value`/`max_value` y `first`/`last_forecast_issued_at`.

## Tests

26 tests nuevos (`test_cams_calidad_aire_transform.py`,
`test_cams_calidad_aire_aggregate.py`), fixture de 29 registros
(`cams_calidad_aire_bronze_sample.json`: los 16 registros reales
`is_mock: false` de `ingesta/capturas/samples/cams_calidad_aire_madrid_sample.json`
— 4 contaminantes x 4 `leadtime_hour`, misma corrida y mismo día de validez
— + 13 sintéticos que violan cada regla de rechazo por turnos). A
diferencia de `aemet_prevision_avisos` (tarea 058), `CAMS_ADS_API_KEY` sí
está configurada en producción (credenciales y licencia ya aceptadas, ver
doc/045) y la muestra commiteada ya es un lote real, no simulado — no hizo
falta regenerar ni construir un fixture base sintético, solo los 13
registros que violan cada regla. Suite completa del proyecto en verde: 267
tests de `ingesta` (sin cambios) + 326 de `procesamiento` (300 previos + 26
nuevos).

`ge_suite.py` y los dos `glue_*.py` no se han podido importar/ejecutar en
esta EC2 (sin `pyspark`/`great_expectations` instalados, mismo motivo que el
resto del patrón); ningún test los importa. El informe de Great Expectations
se escribe directamente a S3 vía `boto3`, no con `saveAsTextFile` (bug de
producción de la tarea 051).

## Terraform (`infra/terraform/glue.tf`)

Bloque completo añadido: rol IAM propio `glue_cams_calidad_aire` (acotado
por prefijo `bronze/cams_calidad_aire/*` · `silver/cams_calidad_aire/*` ·
`gold/cams_calidad_aire_por_contaminante_fecha_validez/*`, incluidos desde
el principio los dos statements de permisos que las tareas 051/052 tuvieron
que añadir a posteriori en los seis primeros datasets; catálogo de sus dos
tablas Silver/Gold; dos `aws_glue_job`), sin tocar los doce bloques
anteriores. Silver particiona por `fecha`/`hora` (derivadas de
`valid_datetime`, el instante previsto — no de `forecast_issued_at` ni de
`ingested_at`); Gold particiona por `pollutant` (el número de contaminantes
es reducido y estable, a diferencia de `fecha_validez`, menos selectivo aquí
porque cada corrida diaria predice varios días de horizonte para todos los
contaminantes a la vez).

`terraform validate` limpio (`terraform init -backend=false`, tras limpiar
`__pycache__`); `terraform fmt -check -diff glue.tf` sin diferencias. No se
ha ejecutado `terraform plan`/`apply`. Artefactos de `terraform init`
eliminados al terminar (ya cubiertos por `.gitignore`).

## `procesamiento/README.md`

Actualizado: título, párrafo introductorio, estructura de código, listas de
fixtures/tests, sección "Decimotercer dataset: `cams_calidad_aire`" con el
razonamiento completo, y bullets nuevos en "Qué no se ha podido ejecutar",
Terraform y "Relevante para tareas futuras" — en particular, un bullet
nuevo que documenta explícitamente que `aemet_prevision_avisos` y
`cams_calidad_aire` forman ahora el precedente del patrón para "previsión
con horizonte", y que una tarea futura con un tercer dataset de este tipo
debe decidir explícitamente cuál de las dos preguntas (por horizonte, o por
instante predicho) responde su agregación de Gold.

## Restricciones respetadas

Alcance limitado a `cams_calidad_aire`; sin `terraform apply` ni comandos
`aws`; sin instalar `pyspark`/`great_expectations`; sin procesar datos
reales de Bronze (solo el fixture, basado en la muestra real ya commiteada,
que ya es `is_mock: false`); sin nada programado (cron/systemd/bucle) en
esta EC2; sin modificar `ingesta/capturas/cams_calidad_aire_madrid.py`.
