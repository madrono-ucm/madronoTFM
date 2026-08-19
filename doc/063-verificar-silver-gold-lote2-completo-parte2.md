# 063 — Verificar Silver→Gold para el segundo lote, parte 2/2 (`aemet_prevision_avisos`, `cams_calidad_aire`, `cartelera_cines_estrenos`, `afluencia_lugares`)

## Contexto

Segunda mitad de la tarea 062 (ver `doc/062-verificar-silver-gold-lote2-completo.md`):
esa sesión verificó Silver→Gold de `ruido`, `aforos_peatones_bicicletas`,
`agenda_eventos` y `bluesky_menciones`; esta cubre los 4 datasets restantes del
segundo lote. El job Bronze→Silver de estos 4 (5 jobs contando los dos pares de
AEMET, aunque en realidad es un único job Glue que procesa ambas formas
internamente — ver más abajo) ya se había relanzado y verificado fuera de esta
sesión el 2026-08-19 ~22:01-22:06 UTC (ver enunciado de la tarea); no se ha vuelto
a lanzar en esta sesión.

## Aclaración: `aemet_prevision_avisos` es UN job Silver→Gold, no dos

El enunciado de esta tarea habla de "los dos jobs Silver→Gold, previsión y
avisos" de AEMET, pero en la infraestructura real (`infra/terraform/glue.tf`,
recurso `aws_glue_job.aemet_prevision_avisos_silver_to_gold`, tarea 058) solo
existe **un** job Glue (`madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold`)
que procesa ambas formas de dato en la misma ejecución, escribiendo a los dos
destinos Gold (`aemet_prevision_por_municipio_leadtime` y
`aemet_avisos_por_zona_fecha_nivel`) — mismo patrón "un productor, un job, varias
formas de dato" ya usado en Bronze→Silver del mismo dataset (tarea 058) y
documentado en el contexto acumulado de esta tarea. Se ha lanzado una única
ejecución (`aws glue start-job-run` de ese job) y se han verificado los dos
resultados Gold que produce.

## Ejecución real: Silver → Gold

Lanzados con `aws glue start-job-run` (región `eu-west-1`, cuenta `222234418587`),
sin overrides de argumentos (los valores por defecto de cada job ya apuntan a la
raíz del dataset en Silver/Gold):

| Job | Run ID | Resultado | Duración |
|---|---|---|---|
| `madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold` | `jr_7ce380af59b8ffe7ef14718fc3df8417c3f9adc089fc06270a5c642b82b90688` | `SUCCEEDED` | 115 s |
| `madrono-tfm-dev-cams-calidad-aire-silver-to-gold` | `jr_42c999f05cdeb2c18a698f3083ce1a055603334da3b751121d720f5f84686aba` | `SUCCEEDED` | 83 s |
| `madrono-tfm-dev-cartelera-cines-estrenos-silver-to-gold` | `jr_b554590edd32bcd56cb5c9861086053511242855bff73e869ef0bf4402c97f89` | **`FAILED`** | 104 s |
| `madrono-tfm-dev-afluencia-lugares-silver-to-gold` | `jr_1c05d6e5d447871439f9dfab510a6ac683b5a88d310b284071cc650c526f88f8` | **`FAILED`** | 41 s |

2 de los 4 (5 de las 6 "salidas" contando los dos destinos Gold de AEMET)
terminan con éxito y contenido verificado. Los otros 2 fallan con un **error real
de ejecución**, no con "0 registros" — se documentan como bugs reales, siguiendo
el mismo criterio que la tarea 052 aplicó al bug de `aparcamientos_silver_to_gold`
(documentar, no arreglar espontáneamente fuera del alcance descrito por el
prompt de la tarea).

## `aemet_prevision_avisos`: verificado, coincide exactamente con Silver

### Previsión — clave `(municipio_code, leadtime_days)`

- Silver: 40 filas reales → 4 grupos `(28079, leadtime_days)` para
  `leadtime_days ∈ {0,1,2,3}` (11, 11, 11, 7 filas respectivamente).
- Gold: 4 filas — coincide 1:1 con el número de grupos y con `samples_count`.
- Verificado a mano con SQL para `leadtime_days=1`: `avg_temperature_max_c=35.3636…`,
  `max_temperature_max_c=38.0`, `avg_temperature_min_c=22.3636…`,
  `min_temperature_min_c=19.0`, `avg_precipitation_probability_pct=9.5454…`,
  `max_precipitation_probability_pct=55.0` — coincide exactamente con la fila real
  de Gold.

### Avisos — clave `(zone, fecha, level)`

- Silver: 13 grupos `(zone, fecha, level)` distintos entre las 3 zonas de aviso de
  Madrid (`Metropolitana y Henares`, `Sierra de Madrid`, `Sur, Vegas y Oeste`) y 5
  fechas (2026-08-15/17/18/19).
- Gold: 13 filas — coincide 1:1.
- Verificado a mano que `alerts_count` deduplica por `identifier` distinto (no
  cuenta filas): p.ej. `Metropolitana y Henares`/`2026-08-18`/`amarillo` tiene
  `samples_count=7` pero `alerts_count=3`; `Sierra de Madrid`/`2026-08-18`/`amarillo`
  tiene `samples_count=18` pero `alerts_count=3` — ambos coinciden exactamente con
  la fila real de Gold, incluida la columna `phenomena` (lista ordenada de
  fenómenos distintos del grupo).

## `cams_calidad_aire`: verificado, coincide exactamente con Silver

Clave `(pollutant, fecha_validez)`:

- Silver: 20 grupos `(pollutant, fecha_validez)` distintos — 4 contaminantes
  (`NO2`, `O3`, `PM10`, `PM2.5`) × 5 días de validez (2026-08-15 a 2026-08-19).
- Gold: 20 filas — coincide 1:1.
- Verificado a mano con SQL las 20 combinaciones completas (no solo una muestra):
  `samples_count`, `avg_value` y `max_value` calculados a mano sobre Silver
  coinciden exactamente (dentro del redondeo de punto flotante esperable, p.ej.
  `9.99075` vs `9.99075`, `4.4014999999999995` vs `4.4014999999999995`) con las 20
  filas reales de Gold.

## `cartelera_cines_estrenos`: `FAILED` con error real — Silver vacío, `spark.read.parquet` no puede inferir esquema

```
AnalysisException: Unable to infer schema for Parquet. It must be specified manually.
```

**No es un bug de código de este dataset ni de esta tarea**: Silver de
`cartelera_cines_estrenos` tiene **0 objetos** (`aws s3 ls
s3://madrono-tfm-dev-silver-222234418587/cartelera_cines_estrenos/ --recursive`
no devuelve nada, ni siquiera el marcador `_$folder$` que sí se vio en la
ejecución de la tarea 061) — coherente con lo ya documentado en las tareas 061/062:
la muestra de origen tiene fecha de sesión ya pasada respecto al momento de la
ejecución del job Bronze→Silink del 2026-08-19, así que la puerta de calidad
(`showtime_already_passed`, tarea 055) descarta todas las filas del job
Bronze→Silver del 2026-08-19 y Silver sale sin ningún fichero Parquet. `glue_silver_to_gold.py` de este dataset llama
`spark.read.parquet(args["silver_path"])` sin ninguna comprobación de "path vacío"
— cuando el prefijo S3 no tiene ningún objeto Parquet (ni siquiera un marcador de
partición vacía), Spark no tiene ninguna base de la que inferir el esquema y falla
con excepción en vez de devolver un DataFrame vacío. Esto es distinto del caso que
sí cubre `procesamiento/README.md` (Gold vacío pero job `SUCCEEDED`, como en la
tarea 061 para el job de sanidad Bronze→Silver): aquí Gold no llega ni a
ejecutarse, el job entero falla.

**Bug real de código pendiente para una tarea de seguimiento** (mismo criterio que
el bug de `aparcamientos_silver_to_gold` documentado en la tarea 052 — no se
corrige en esta tarea porque el prompt no lo describe explícitamente): todos los
`glue_silver_to_gold.py` de este patrón que leen Silver con
`spark.read.parquet(path)` sin schema explícito comparten esta misma fragilidad
ante un Silver que, en una ejecución concreta, no produce ningún fichero (puerta
de calidad que rechaza el 100% de las filas, o fuente aún sin ninguna captura
válida como `afluencia_lugares`). Una solución típica es leer con un esquema
explícito (`spark.read.schema(...).parquet(path)`, tolera un path vacío) o
comprobar de antemano si el prefijo tiene objetos antes de leer.

## `afluencia_lugares`: `FAILED` con error real — falta `--extra-py-files` en el job Terraform

```
ModuleNotFoundError: No module named 'procesamiento'
```

**Bug real de infraestructura, distinto del caso anterior.**
`procesamiento/silver_gold/afluencia_lugares/glue_silver_to_gold.py` importa en
tiempo de ejecución:

```python
from procesamiento.silver_gold.afluencia_lugares.transform import WEEKDAY_KEYS_ES
```

Es el **único** `glue_silver_to_gold.py` de los 14 datasets del patrón que importa
algo del paquete `procesamiento` (confirmado con `grep` sobre los 14 ficheros); el
resto son autocontenidos y no necesitan el paquete en el cluster de Glue. Sin
embargo, el recurso `aws_glue_job.afluencia_lugares_silver_to_gold`
(`infra/terraform/glue.tf`) no incluye el argumento
`--extra-py-files = ".../procesamiento_source.key"` que sí llevan los 14 jobs
Bronze→Silver del patrón (que si necesitan el paquete completo, para
`ge_suite.py`) — nadie lo añadió al job Silver→Gold de este dataset en concreto
porque, hasta esta tarea, nunca se había llegado a ejecutar contra un Silver con
al menos algún objeto (aunque sea 0 filas) que hiciera avanzar la ejecución hasta
el punto de import real del módulo. El error aparece a los 41 s, en el arranque
del job, antes de llegar siquiera a leer Silver — así que, adicionalmente, no se
ha podido confirmar si el job también tropezaría con el mismo problema de
"Silver vacío, `Unable to infer schema`" que `cartelera_cines_estrenos` una vez
resuelto el `ModuleNotFoundError` (Silver de `afluencia_lugares` también tiene 0
objetos, igual que `cartelera_cines_estrenos` — sigue bloqueado sin
`GOOGLE_MAPS_API_KEY` real, ver tarea 060/061).

**No corregido en esta tarea**: el prompt de esta tarea autoriza `terraform
apply` únicamente para lo que describe explícitamente (lanzar y verificar jobs
Silver→Gold ya existentes), no para modificar y reaplicar la definición del job.
Se deja documentado como bug real de infraestructura para una tarea de
seguimiento — el arreglo previsible es añadir el mismo argumento
`--extra-py-files` que ya llevan los jobs Bronze→Silver del patrón al recurso
`aws_glue_job.afluencia_lugares_silver_to_gold`.

## Verificación de contenido: metodología

Sin `pyspark`/`pandas`/`pyarrow` instalados en esta EC2 (mismo motivo documentado
en la tarea 062: disco muy limitado, sin entorno de procesamiento preparado), se
descargó el binario estático de `duckdb` CLI (~20 MB, sin dependencias) a `/tmp`
(tmpfs, no al disco raíz — confirmado con `df -h /`, 2.0G libres sin cambios
antes/después) para leer los ficheros Parquet reales de Silver y Gold (también
descargados a `/tmp`, ~628 KB en total) y comparar agregaciones con SQL. Todo lo
descargado a `/tmp` se ha borrado al terminar — no queda nada en el repositorio ni
en disco persistente.

## Discrepancias encontradas

Dos, ambas documentadas arriba con su causa raíz identificada:

1. `cartelera_cines_estrenos_silver_to_gold`: `spark.read.parquet` sin esquema
   explícito falla cuando Silver no tiene ningún objeto — afecta potencialmente a
   cualquier dataset del patrón si su Silver sale completamente vacío en una
   ejecución concreta.
2. `afluencia_lugares_silver_to_gold`: falta `--extra-py-files` en la definición
   Terraform del job — específico de este dataset, el único cuyo script Silver→Gold
   importa del paquete `procesamiento`.

Ninguna se ha corregido en esta sesión (fuera del alcance explícito del prompt);
ambas quedan documentadas para una tarea de seguimiento.

## Restricciones respetadas

- Alcance limitado a estos 4 datasets (5 "salidas" Gold contando las dos de
  AEMET); no se ha tocado `ruido`/`aforos_peatones_bicicletas`/`agenda_eventos`/
  `bluesky_menciones` (tarea 062) ni el primer lote de 6 datasets.
- No se ha relanzado el job Bronze→Silver de ninguno de los 4 — ya estaba hecho y
  verificado antes de empezar esta sesión (ver Contexto).
- No se ha creado ningún trigger/schedule de Glue (queda para la tarea 065).
- No se ha ejecutado `terraform destroy` ni ningún `terraform apply`/`plan` — no
  ha hecho falta ningún cambio de infraestructura para completar la verificación
  pedida (los dos bugs encontrados se documentan, no se corrigen, siguiendo el
  criterio ya usado por la tarea 052).
- No se ha tocado `infra/terraform/lambda.tf` ni el primer lote de 6 datasets.
- El binario de `duckdb` y los ficheros Parquet descargados a `/tmp` para la
  verificación de contenido se han borrado al terminar; no se ha escrito nada en
  el disco raíz persistente de la EC2 ni queda nada programado
  (cron/systemd/bucle).

## Relevante para tareas futuras

- `aemet_prevision_avisos` tiene **un único** job Glue Silver→Gold que produce
  **dos** salidas Gold (previsión y avisos) en la misma ejecución — al hablar de
  "los jobs de AEMET" en el contexto de Silver→Gold, contar 1 ejecución con 2
  verificaciones de contenido, no 2 `start-job-run` distintos.
- Dos bugs reales de código/infraestructura quedan pendientes de una tarea de
  seguimiento (mismo patrón que el bug de `aparcamientos_silver_to_gold` de la
  tarea 052, aún sin corregir tampoco): (1) `cartelera_cines_estrenos_silver_to_gold`
  (y potencialmente cualquier otro `glue_silver_to_gold.py` del patrón) falla con
  `AnalysisException` en vez de producir un Gold vacío cuando su Silver de origen
  no tiene ningún objeto — el arreglo típico es leer con `spark.read.schema(...)`
  en vez de inferencia automática, o comprobar de antemano si el prefijo tiene
  contenido; (2) al `aws_glue_job.afluencia_lugares_silver_to_gold` de
  `infra/terraform/glue.tf` le falta el argumento `--extra-py-files` que sí llevan
  los 14 jobs Bronze→Silver del patrón, necesario porque su script importa
  `WEEKDAY_KEYS_ES` del paquete `procesamiento` — es el único
  `glue_silver_to_gold.py` de los 14 datasets que lo hace, así que ningún otro job
  Silver→Gold del patrón necesita este mismo arreglo.
- Antes de asumir que "Gold vacío = job `SUCCEEDED` sin error" (como documentó
  correctamente la tarea 061 para el job de sanidad **Bronze→Silver**), conviene
  comprobarlo explícitamente para cada etapa: en esta tarea, la etapa
  **Silver→Gold** de un dataset con Silver vacío sí puede fallar con una excepción
  real en vez de completar con 0 filas, dependiendo de cómo esté escrito el
  script de Glue concreto (aquí, de si usa `spark.read.parquet` con inferencia de
  esquema automática o no).
