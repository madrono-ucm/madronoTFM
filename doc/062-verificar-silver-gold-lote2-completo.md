# 062 — Verificar Silver→Gold para el segundo lote, parte 1/2 (`ruido`, `aforos_peatones_bicicletas`, `agenda_eventos`, `bluesky_menciones`)

## Contexto: alcance reducido de 8 a 4 datasets

Esta tarea (id 62 en `tasks/062-verificar-silver-gold-lote2-completo.md`) ya se había
intentado dos veces cubriendo los 8 datasets del segundo lote a la vez y las dos
terminó sin crear ningún commit (mismo patrón que las tareas 051/061). El segundo
intento sí llegó a completar con éxito, fuera de esta sesión de `claude`, el job
Bronze→Silver de los 8 datasets (ejecución real del 2026-08-19 ~22:01-22:06 UTC,
verificada manualmente con `aws s3 ls`/`aws glue get-job-runs` antes de abrir esta
sesión). Por eso el prompt de esta sesión concreta acota el trabajo a solo 4 datasets
(`ruido`, `aforos_peatones_bicicletas`, `agenda_eventos`, `bluesky_menciones`) y deja
los otros 4 (`aemet_prevision_avisos`, `cams_calidad_aire`,
`cartelera_cines_estrenos`, `afluencia_lugares`) para una tarea 063 aparte — que
**todavía no existe como fichero en `tasks/`** en el momento de cerrar esta sesión (el
fichero `tasks/063-diseno-scheduling-silver-gold.md` que sí existe es una tarea
distinta, sobre el diseño del scheduling de la tarea 065, no sobre estos 4 datasets).

El fichero `tasks/062-verificar-silver-gold-lote2-completo.md` commiteado en el
repositorio sigue describiendo el alcance original de 8 datasets (no se ha
actualizado entre intentos) — esta sesión sigue el alcance reducido tal como lo
especifica el prompt recibido, no el fichero de tarea, y no se ha modificado ese
fichero (el ciclo de vida de `tasks/*.md` — mover a `tasks/done/`, actualizar
`status` — lo gestiona el demonio orquestador, no esta sesión).

**No se ha relanzado el job Bronze→Silver de estos 4 datasets** (ya estaba hecho y
verificado antes de empezar, ver arriba) — el trabajo de esta sesión es únicamente
lanzar y verificar la etapa Silver→Gold, que nunca se había llegado a lanzar en los
intentos anteriores.

## Ejecución real: Silver → Gold (4/4 con éxito)

Lanzados con `aws glue start-job-run` (región `eu-west-1`, cuenta `222234418587`),
sin overrides de `--silver_path`/`--gold_path` (los valores por defecto de cada job ya
apuntan a la raíz del dataset en Silver/Gold):

| Dataset | Job | Run ID | Resultado | Duración |
|---|---|---|---|---|
| `ruido` | `madrono-tfm-dev-ruido-silver-to-gold` | `jr_970e54dded5910aa0fee4390c3dcd6dd825e65a1489278119c8c0ee530b46f56` | `SUCCEEDED` | 63 s |
| `aforos_peatones_bicicletas` | `madrono-tfm-dev-aforos-peatones-bicicletas-silver-to-gold` | `jr_20024c19169b6b60d5eb9af15c90c2ab60a35a0039a7bd08458393345b6a2110` | `SUCCEEDED` | 76 s |
| `agenda_eventos` | `madrono-tfm-dev-agenda-eventos-silver-to-gold` | `jr_cc28b82daf7b46abad926ba37ced0a5a4a2b4a13524a972cbc780767cc03ad94` | `SUCCEEDED` | 180 s |
| `bluesky_menciones` | `madrono-tfm-dev-bluesky-menciones-silver-to-gold` | `jr_8f687d66d726e63daaf07686fa16309c2b438d003d463c79fa19d4ddcfbb7076` | `SUCCEEDED` | 83 s |

Ninguno resultó sorprendentemente lento: los cuatro terminan en 1-3 minutos, en línea
con los tiempos ya documentados en la tarea 052 para el primer lote (58-192 s) y en la
061 para el job de sanidad Bronze→Silver de este mismo lote (173-181 s) — no hay
ningún hallazgo aquí que cambie la cadencia prevista para la tarea 064/065.

## Verificación de contenido: Gold coincide exactamente con la agregación manual de Silver

Sin `pyspark`/`pandas`/`pyarrow` instalados en esta EC2 (mismo motivo documentado por
las tareas 049-061: entorno con disco muy limitado, sin entorno virtual del proyecto
preparado para procesamiento), se descargó el binario estático de `duckdb` CLI (~60 MB,
sin dependencias, un único fichero) a `/tmp` para leer directamente los ficheros
Parquet reales de Silver y Gold (descargados también a `/tmp`, nunca al disco raíz —
confirmado con `df -h /`, 2.0G libres sin cambios antes/después) y comparar sus
agregaciones con SQL. Todo lo descargado a `/tmp` (el binario de `duckdb` y los
ficheros Parquet) se ha borrado al terminar la verificación — no queda nada de esto en
el repositorio ni en disco persistente.

Para cada dataset: se comparó el recuento total de filas Silver frente a Gold, el
número de grupos distintos de la clave de agregación (debe coincidir exactamente con
las filas de Gold) y, para al menos un grupo por dataset, la agregación calculada a
mano con SQL (`GROUP BY` + `count`/`sum`/`avg`/`max`/`min`/`count(DISTINCT ...)`)
frente a la fila real de Gold — con coincidencia exacta en los cuatro:

### `ruido` — clave `(station_id, period, date)`

- Silver: 620 filas reales → 372 grupos `(station_id, period, fecha)` distintos.
- Gold: 372 filas — coincide 1:1 con el número de grupos.
- Verificado a mano para `RF-01`/período `D` (grupo con 3 fechas: 2026-08-13,
  2026-08-16, 2026-08-17): `avg_laeq_db`/`max_laeq_db`/`min_laeq_db` coinciden
  exactamente para las 3 fechas, y la media móvil de 7 días
  (`laeq_rolling_7d_avg_db`) también coincide: `62.6` (1 día en ventana) →
  `61.85` (2 días, media de 62.6/61.1) → `62.233...` (3 días, media de
  62.6/61.1/63.0) — confirma que la ventana de calendario de
  `procesamiento/silver_gold/ruido/aggregate.py` está bien portada al job de Glue
  real.
- `samples_count=3` en varios grupos: no es una reingesta real de datos distintos,
  es el resultado esperado de que el job de sanidad Bronze→Silver de este dataset se
  ha ejecutado 3 veces sobre el mismo Bronze en sesiones anteriores (tareas 061 y
  los dos intentos previos de la 062) — cada ejecución añade una copia idéntica del
  mismo valor, así que `avg`/`max`/`min` coinciden trivialmente con el valor único
  real. No requiere ninguna acción: es un efecto de la falta de scheduling/bookmark
  (pendiente de las tareas 064/065), no un bug de agregación.

### `aforos_peatones_bicicletas` — clave `(station_id, mode, fecha, hora)`

- Silver: 5913 filas reales → 1971 grupos distintos.
- Gold: 1971 filas — coincide 1:1.
- Verificado a mano para `PERM_BICI01_PM01`/`bicicletas` en varias horas
  consecutivas: `total_count` (suma), `avg_count`, `max_count`, `min_count`
  coinciden exactamente fila a fila (ejemplo: hora 22 del 2024-06-29,
  `samples_count=3`, `total_count=48`, `avg_count=16.0` = 3 lecturas idénticas de
  16, mismo efecto de reingesta de sanidad que en `ruido`).

### `agenda_eventos` — clave `(category, district, fecha)` (con sentinelas `__sin_categoria__`/`__sin_distrito__`)

- Silver: 11957 filas reales → 1578 grupos distintos.
- Gold: 1578 filas — coincide 1:1.
- Verificado a mano que `events_count` deduplica correctamente por `event_id`
  distinto (no es un recuento de filas): grupo `1ciudad21distritos`/`Arganzuela`/
  `2026-10-16` tiene `samples_count=7` (7 filas Silver, reingestas del mismo evento
  a través de las distintas ejecuciones de sanidad) pero `events_count=1` (un único
  evento real) — coincide exactamente con la fila real de Gold, incluida la columna
  `sources` (`[agenda_eventos_madrid_municipal]`).

### `bluesky_menciones` — clave `(mode, match_term, fecha, hora)`

- Silver: 1037 filas reales → 268 grupos distintos.
- Gold: 268 filas — coincide 1:1.
- Verificado a mano que `mentions_count` deduplica por `post_hash` distinto (no
  cuenta filas): grupo `distrito_sweep`/`Arganzuela`/`2026-07-18`/hora 21 tiene
  `samples_count=6` pero `mentions_count=1` (un único post real, reingestado 6
  veces a través de las ejecuciones de sanidad) — y las sumas
  `total_like_count`/`total_repost_count`/`total_reply_count`/`total_quote_count`
  coinciden exactamente con la suma manual sobre las 6 filas Silver (582/492/72/84
  respectivamente para ese grupo).

## Discrepancias encontradas

Ninguna. Los cuatro jobs `SUCCEEDED` sin error, y el contenido de Gold coincide
exactamente con la agregación esperada en los cuatro casos verificados a mano — no
hay ningún bug de código que documentar en esta tarea (a diferencia de la tarea 052,
que sí encontró un bug real en `aparcamientos_silver_to_gold`).

## Restricciones respetadas

- Alcance limitado a los 4 datasets indicados (`ruido`, `aforos_peatones_bicicletas`,
  `agenda_eventos`, `bluesky_menciones`); los otros 4 quedan para la tarea 063 (aún
  no creada en el repositorio en el momento de cerrar esta sesión).
- No se ha relanzado el job Bronze→Silver de estos 4 datasets — ya estaba hecho y
  verificado antes de empezar esta sesión.
- No se ha creado ningún trigger/schedule de Glue (queda para la tarea 065).
- No se ha ejecutado `terraform destroy` ni ningún `terraform apply`/`plan` — la
  infraestructura de este lote ya estaba aplicada desde la tarea 061 y no ha hecho
  falta ningún cambio de código/infraestructura para completar esta verificación.
- No se ha tocado `infra/terraform/lambda.tf` ni el primer lote de 6 datasets.
- El binario de `duckdb` y los ficheros Parquet descargados a `/tmp` para la
  verificación de contenido se han borrado al terminar; no se ha escrito nada en el
  disco raíz (persistente) de la EC2 ni queda nada programado (cron/systemd/bucle).

## Relevante para tareas futuras

- Los `samples_count` > 1 observados en los cuatro datasets de este lote (factor
  ~3x en `ruido`/`aforos_peatones_bicicletas`/`agenda_eventos`, ~6x en
  `bluesky_menciones`) son el resultado acumulado de las múltiples ejecuciones de
  sanidad Bronze→Silver lanzadas en sesiones anteriores (061 y los dos intentos
  previos de la 062) sobre el mismo Bronze, sin `job-bookmark` habilitado
  (`--job-bookmark-option = job-bookmark-disable`, deliberado en todo el patrón
  desde la tarea 041). No es un bug: todas las agregaciones de Gold que dependen de
  contar registros distintos en vez de filas (`events_count` por `event_id`,
  `mentions_count` por `post_hash`) ya deduplican correctamente, confirmado en esta
  tarea. Cuando la tarea 064/065 programe una cadencia real con Glue Bookmarks o un
  particionado por lote de ingesta, este efecto de "misma medición contada varias
  veces" en `ruido`/`aforos_peatones_bicicletas` (que no tienen una clave natural de
  deduplicación como `event_id`/`post_hash`) debería desaparecer por construcción
  (cada ejecución solo procesaría datos nuevos) — no hace falta ningún cambio de
  código para eso, ya está resuelto por diseño.
- Sin `pyspark`/`pandas`/`pyarrow` disponibles en esta EC2, descargar el binario
  estático de `duckdb` CLI a `/tmp` (no al disco raíz) es una forma ligera y sin
  huella de verificar contenido real de Parquet en S3 con SQL, sin instalar nada de
  forma permanente ni escribir en el disco raíz limitado de la EC2 — recomendable
  para cualquier tarea futura de este patrón que necesite volver a comparar
  Silver/Gold reales a mano (el intento de usar `aws s3api select-object-content`
  sobre estos buckets falló con `MethodNotAllowed`, no investigado más allá porque
  `duckdb` resolvió la verificación igualmente).
