# 074 — Verificar la reconstrucción de `bicimad` y completar Gold

## Resumen

Cierra la serie 073+074 de limpieza de duplicados de `bicimad`. El
`JobRunId` de Silver que dejó la tarea 073 (`jr_6f09053f6eea77a852b5ff8e6db22fb984a459a4238648cf66204f1e0d8f5731`)
había terminado en **`FAILED`** cuando esta tarea empezó a comprobarlo (no
seguía `RUNNING` como decía el cierre de la 073 — terminó poco después de
ese cierre). Esta tarea diagnosticó el fallo, relanzó Silver una vez con la
causa entendida (**`SUCCEEDED`**), verificó que quedó deduplicado, y
completó Gold con el mismo patrón de job de un solo uso.

## Estado final: Silver y Gold de `bicimad`, ambos reconstruidos y verificados

## 1. Diagnóstico del `JobRunId` heredado de la tarea 073

`aws glue get-job-run --job-name madrono-tfm-dev-bicimad-silver-backfill-dedup
--run-id jr_6f09053f6eea77a852b5ff8e6db22fb984a459a4238648cf66204f1e0d8f5731`
→ `JobRunState: FAILED`, `ExecutionTime: 471s`, `DPUSeconds: 943`.

`ErrorMessage`: `An error occurred while calling o854.parquet. Failed to
delete key: bicimad` (truncado por la API; el mensaje completo, obtenido de
CloudWatch Logs, es una `MultiObjectDeleteException` de S3). El log
completo (`/aws-glue/jobs/error/<run-id>`) muestra que el job intentó
`silver_partitioned.write.mode("overwrite").partitionBy(...)` sobre un
prefijo Silver que **ya tenía objetos** (4417, dejados por los intentos
previos de la tarea 073) — Spark, antes de escribir, ejecuta
`deleteMatchingPartitions`, que borra los objetos existentes en batches de
hasta 1000 vía `DeleteObjects`. Los 5 batches (una por cada 1000 keys, más
un resto de 417) tiraron **todos** `MultiObjectDeleteException` con un
subconjunto de keys en error cada uno — un fallo intermitente de S3 a esa
escala de borrado masivo, no un bug de lógica ni de permisos (no hay
`AccessDenied` en el log, y `trafico` había completado un `overwrite`
equivalente sin problema en la tarea 072/073 sobre un volumen menor). El
propio docstring de `glue_backfill_dedup.py` (escrito en la tarea 073) ya
advertía de esto: *"Requiere que el prefijo de destino ya esté vacío antes
de lanzarlo"* — condición que el sexto intento de la 073 no cumplió antes
de lanzar el job.

Verificado con Athena (`SELECT station_id, measured_at, COUNT(*) ...`) que,
tras el fallo, Silver seguía en el mismo estado sin deduplicar que antes
del intento (`n=1380` en la fila con más duplicados) — el fallo abortó la
escritura completa antes de escribir ningún dato nuevo, no dejó un Silver a
medias con datos corruptos.

## 2. Relanzamiento de Silver (un único reintento, con la causa entendida)

Siguiendo la instrucción explícita del docstring, se borró el prefijo
manualmente antes de relanzar:

```
aws s3 rm s3://madrono-tfm-dev-silver-222234418587/bicimad/ --recursive
# 4417 objetos borrados, prefijo confirmado vacío
aws glue start-job-run --job-name madrono-tfm-dev-bicimad-silver-backfill-dedup
# JobRunId: jr_049b04032c72ecc804ac512e60a789a61b7920da2e707ebf76a73e9bd60509e7
```

Resultado: **`SUCCEEDED`** en 407s (815 DPUSeconds).

### Verificación de Silver

Consulta exacta pedida por el enunciado:

```sql
SELECT station_id, measured_at, COUNT(*) AS n
FROM bicimad GROUP BY station_id, measured_at ORDER BY n DESC LIMIT 5
```

Resultado: **`n=1`** en las 5 filas (sin duplicados).

Cobertura de fechas: Silver cubre `fecha=2026-08-14` a `2026-08-23`, el
mismo rango que las particiones de ingesta de Bronze (`fecha=2026-08-14` a
`2026-08-23`, 2322 objetos reales en el momento de esta verificación — más
que los 2249 citados en el enunciado de la tarea, por datos nuevos
ingeridos entre que se escribió la tarea y esta verificación; sin huecos en
ningún caso), **sin ningún hueco** en ese rango (789 objetos Silver
repartidos en 96 objetos/día para los días completos, coherente con la
partición horaria).

**Hallazgo de calidad de datos, no bloqueante**: Silver trae también 5
fechas fuera de ese rango con muy pocos objetos cada una
(`fecha=1970-01-01` [2 objetos], `2026-08-06` [1], `2026-08-08` [4],
`2026-08-11` [2], `2026-08-13` [2]) que **no existen como partición de
ingesta en Bronze** (Bronze solo tiene particiones `fecha=` de ingesta
`2026-08-14` a `2026-08-23`). Esto no es un hueco ni un bug de esta
reconstrucción: `fecha`/`hora` de Silver se recalculan siempre desde el
propio campo `measured_at` del registro (no se copian de la partición de
ingesta de Bronze, ver `glue_bronze_to_silver.py`/`glue_backfill_dedup.py`)
— significa que unos pocos registros dentro de los ficheros de Bronze ya
ingeridos (`fecha=2026-08-14` en adelante) traen un `measured_at` con una
fecha muy anterior o inválida (`1970-01-01` es el patrón clásico de un
timestamp nulo/no parseable cayendo al epoch Unix). No se ha investigado
más a fondo ni corregido — fuera del alcance de esta tarea (verificar y
completar la reconstrucción, no auditar la calidad del feed GBFS de
origen); queda anotado para una tarea futura si se considera relevante.

## 3. Reconstrucción de Gold

Con Silver confirmado limpio, se creó el job de Gold de un solo uso, mismo
patrón que el de Silver de la tarea 073:

- **`procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`**
  (nuevo): misma agregación que la de producción
  (`glue_silver_to_gold.py`, `groupBy(station_id, fecha, hora)` con los
  mismos `agg(...)`), pero leyendo `--silver_path` completo (todo el
  histórico, sin acotar a una partición horaria) y escribiendo con
  `mode("overwrite")` en vez de `append`. **Sin `dropDuplicates`**: el
  Silver de origen ya está deduplicado por el paso anterior — es una
  agregación normal, no una limpieza. Sin `--extra-py-files`: a diferencia
  de `glue_silver_to_gold.py`, este script no importa nada de
  `procesamiento.silver_gold.incremental` (no necesita acotar a una hora
  concreta), así que no necesita el paquete compartido en el path de Glue.
- **`infra/terraform/glue.tf`**: `aws_s3_object.glue_script_bicimad_backfill_dedup_gold`
  + `aws_glue_job.bicimad_gold_backfill_dedup` (`timeout = 90` min, mismo
  criterio que el de Silver — lee todo el histórico de una vez). Sin
  trigger ni schedule, igual que el de Silver.
- Aplicado con `terraform apply` acotado a esos 2 recursos
  (`-target=aws_s3_object.glue_script_bicimad_backfill_dedup_gold
  -target=aws_glue_job.bicimad_gold_backfill_dedup`). Verificado con
  `terraform plan` con el mismo `-target` tras el apply: **"No changes"**.
- `aws s3 rm s3://madrono-tfm-dev-gold-222234418587/bicimad_por_estacion_hora/
  --recursive` (498 objetos borrados) antes de lanzar, mismo criterio que
  Silver (el job escribe con `overwrite`, pero un prefijo con miles/cientos
  de objetos preexistentes puede disparar el mismo `MultiObjectDeleteException`
  visto en el paso 1 — más barato evitarlo de antemano que arriesgar un
  segundo fallo).
- `aws glue start-job-run --job-name madrono-tfm-dev-bicimad-gold-backfill-dedup`
  → `JobRunId: jr_e34e45f3a506791b200a7aec1c333ab9383f1f253c63947f2b2fe8804ca138ae`
  → **`SUCCEEDED`** en 121s (242 DPUSeconds).

### Verificación de Gold

`aws s3 ls` confirma las mismas fechas que Silver (`date=2026-08-14` a
`2026-08-23`, más las mismas 5 fechas outlier ya explicadas arriba) — sin
huecos en el rango real de ingesta.

Consulta de agregación Athena (`madrono-tfm_dev_gold.bicimad_por_estacion_hora`):

| date | rows (estación×hora) | estaciones distintas | suma de `samples_count` |
|---|---|---|---|
| 2026-08-14 | 2 | 2 | 2 |
| 2026-08-15 | 16073 | 673 | 192017 |
| 2026-08-16 | 16086 | 673 | 191827 |
| 2026-08-17 | 16038 | 673 | 191030 |
| 2026-08-18 | 16154 | 677 | 192764 |
| 2026-08-19 | 16180 | 677 | 193037 |
| 2026-08-20 | 16203 | 677 | 193429 |
| 2026-08-21 | 16171 | 678 | 192890 |
| 2026-08-22 | 16213 | 678 | 193440 |
| 2026-08-23 (parcial, día en curso) | 1353 | 678 | 10512 |

Números coherentes: ~670-680 estaciones × 24h ≈ 16000-16200 filas/día
completo, `2026-08-14` solo con 2 filas porque la ingesta de Bronze empezó
mediado ese día.

## Recursos AWS creados/aplicados en esta sesión (región `eu-west-1`, cuenta `222234418587`)

- `aws_glue_job.bicimad_gold_backfill_dedup` (nombre real:
  `madrono-tfm-dev-bicimad-gold-backfill-dedup`) — job de un solo uso, sin
  trigger, `timeout=90min`. Aplicado con `terraform apply -target=...`.
- `aws_s3_object.glue_script_bicimad_backfill_dedup_gold` — script subido a
  `s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/
  bicimad_backfill_dedup_gold-<hash>.py`.
- Ejecuciones de Glue: 1 relanzamiento de
  `madrono-tfm-dev-bicimad-silver-backfill-dedup` (815 DPU-s) + 1 ejecución
  de `madrono-tfm-dev-bicimad-gold-backfill-dedup` (242 DPU-s) — ~0.29
  DPU-horas totales en esta sesión, sobre el job ya existente de Silver
  (creado en la 073) y el nuevo de Gold.
- Borrados S3 (Silver y Gold de `bicimad`, nunca Bronze): 4417 objetos en
  `silver/bicimad/` + 498 objetos en `gold/bicimad_por_estacion_hora/`,
  ambos antes de relanzar su job de reconstrucción correspondiente.

## Restricciones respetadas

- **`trafico` no se ha tocado en ningún momento** (ni Silver ni Gold ni su
  job ni su trigger) — solo se han inspeccionado sus triggers de forma
  read-only para confirmar que seguían en el mismo estado.
- **Bronze no se ha tocado** (ni `bicimad` ni `trafico`) — solo lecturas
  (`aws s3 ls`, `spark.read` dentro de los jobs).
- **Los triggers y el pipeline incremental de la tarea 072 no se han
  tocado.** Se comprobó su estado (read-only,
  `aws glue get-trigger`) y se encontraron ambos `SCHEDULED` de
  `trafico`/`bicimad` en `DEACTIVATED` — distinto de como los dejó la
  tarea 072 (`ACTIVATED`); lo más probable es que algún intento fallido de
  la tarea 073 los desactivara de nuevo como medida de precaución mientras
  manipulaba Silver de `bicimad`. Esta tarea **no los reactiva** (fuera de
  su alcance explícito: "no toques... los triggers ni los jobs de
  producción existentes") — queda documentado aquí para que una tarea
  futura decida conscientemente si reactivarlos.
- El único reintento del job de Silver se hizo **con la causa del fallo ya
  entendida** (`MultiObjectDeleteException` intermitente de S3 al borrar
  ~4400 objetos existentes antes de un `overwrite`, resuelto vaciando el
  prefijo a mano primero, tal como ya anticipaba el propio docstring del
  script) — no fue un reintento a ciegas.

## Relevante para tareas futuras

- **Antes de lanzar cualquier job de Glue en modo `overwrite` sobre un
  prefijo S3 con miles de objetos preexistentes, vacía el prefijo a mano
  primero** (`aws s3 rm --recursive`) en vez de confiar en que
  `deleteMatchingPartitions` de Spark lo haga de forma fiable — a esta
  escala (~4400 objetos) el borrado por lotes de S3 (`DeleteObjects`,
  hasta 1000 keys/batch) puede fallar de forma intermitente y aborta todo
  el `write` sin escribir nada, dejando el dataset en su estado previo
  (no lo corrompe, pero tampoco avanza). Aplicado también, por precaución,
  al backfill de Gold de esta misma tarea aunque el volumen fuera mucho
  menor (498 objetos).
- El hallazgo de calidad de datos de `bicimad` (5 fechas outlier con
  `measured_at` muy anterior o inválido, incluido el patrón clásico
  `1970-01-01` de timestamp epoch/nulo, dentro de ficheros de Bronze ya
  ingeridos entre el 14 y el 23 de agosto) no se ha investigado ni
  corregido — si una tarea futura decide auditar la calidad del feed GBFS
  de origen de `bicimad`, este es un punto de partida conocido.
- Los triggers `SCHEDULED` de `trafico`/`bicimad` (Bronze→Silver) están
  `DEACTIVATED` en este momento, pese a que la tarea 072 los dejó
  `ACTIVATED` al cerrar — su `CONDITIONAL` de Silver→Gold hermano no se ha
  comprobado en esta tarea. Antes de dar por reactivable el pipeline
  incremental de producción de estos dos datasets, una tarea futura
  debería decidir conscientemente si reactivarlos (y confirmar que no hay
  ninguna razón pendiente por la que se desactivaran de nuevo tras la
  tarea 072).
- Con esto, la serie 072 (arreglo de lectura incremental) + 073 (lanzar
  backfill deduplicado de `bicimad`) + 074 (verificar y completar Gold)
  queda cerrada: Silver y Gold de `bicimad` están reconstruidos,
  deduplicados y verificados con datos reales.
