# 077 (resto) — Backfill deduplicado de `aforos_peatones_bicicletas`, `ruido` y `cams_calidad_aire`

## Estado: los 3 datasets reconstruidos y verificados. Serie 072-077 completamente cerrada.

Última pieza pendiente de la serie de limpieza de duplicados (072-077). El
código y los 6 `aws_glue_job` de backfill (Silver + Gold × 3 datasets) ya
estaban escritos y aplicados en AWS desde la tarea 077 anterior (ver
`doc/077-limpieza-duplicados-grupo-diario.md`) — esta tarea solo lanza,
espera y verifica, sin escribir código nuevo ni tocar Terraform.

## 0. Comprobación previa de drift

`terraform plan` acotado con `-target` a los 6 `aws_glue_job` de backfill y
sus 6 `aws_s3_object` de script → **"No changes"**. No hizo falta ningún
`terraform apply`.

## 1. `ruido`

- Prefijo Silver vaciado (`s3://.../silver/ruido/`), backfill lanzado
  (`madrono-tfm-dev-ruido-silver-backfill-dedup`) → **`SUCCEEDED`** en 223s
  (446 DPU-s).
- Verificación Athena (tras `MSCK REPAIR TABLE ruido`, la tabla tenía 0
  particiones registradas pese a tener datos reales, igual que en la tarea
  077 anterior):
  ```sql
  SELECT station_id, period, measured_date, COUNT(*) AS n
  FROM ruido GROUP BY station_id, period, measured_date ORDER BY n DESC LIMIT 5
  ```
  **`n=1`** en las 5 filas (antes: `n=6`, confirmado en la tarea anterior).
- Prefijo Gold vaciado (`gold/ruido_por_estacion_periodo_fecha/`), backfill
  lanzado → **`SUCCEEDED`** en 61s (123 DPU-s).
- Verificación Gold: 5 fechas (`2026-08-13`, `16`-`19`), **124 filas/día,
  31 estaciones × 4 periodos, sin huecos** en ese rango — coherente con las
  fechas reales de `measured_date` (recalculadas desde el dato, no copiadas
  de la partición de ingesta de Bronze, mismo patrón que `bicimad`/tarea
  074: Bronze solo tiene ingesta `fecha=2026-08-17` a `21`, pero
  `measured_date` trae fechas ligeramente distintas del propio contenido).

## 2. `cams_calidad_aire`

- Prefijo Silver vaciado, backfill lanzado
  (`madrono-tfm-dev-cams-calidad-aire-silver-backfill-dedup`) →
  **`SUCCEEDED`** en 211s (423 DPU-s).
- Verificación Athena (tras `MSCK REPAIR TABLE`):
  ```sql
  SELECT pollutant, latitude, longitude, valid_datetime, forecast_issued_at, COUNT(*) AS n
  FROM cams_calidad_aire GROUP BY pollutant, latitude, longitude, valid_datetime, forecast_issued_at
  ORDER BY n DESC LIMIT 5
  ```
  **`n=1`** en las 5 filas (antes: `n=10`).
- Prefijo Gold vaciado, backfill lanzado → **`SUCCEEDED`** en 63s
  (126 DPU-s).
- Verificación Gold (columnas reales de la tabla: `pollutant`,
  `fecha_validez`, no `latitude`/`longitude`/`valid_datetime` — la
  agregación de Gold resume por contaminante y fecha de validez, sin
  desglosar por punto de rejilla):
  ```sql
  SELECT pollutant, fecha_validez, COUNT(*) rows, SUM(samples_count) samples
  FROM cams_calidad_aire_por_contaminante_fecha_validez
  GROUP BY pollutant, fecha_validez ORDER BY pollutant, fecha_validez
  ```
  **4 contaminantes (NO2, O3, PM10, PM2.5) × 9 fechas (`2026-08-15` a
  `2026-08-23`), 1 fila y 4 muestras cada combinación, sin huecos.**

## 3. `aforos_peatones_bicicletas`

Igual que documentó la tarea anterior, **este dataset no es consultable con
Athena** (su tabla tiene `partition projection` con
`projection.fecha.range = "2026-08-01,NOW+1DAY"`, pero los datos reales son
de 2024 — cualquier `SELECT` devuelve 0 filas en silencio). Verificado
descargando los parquet reales y agregando con `pyarrow` (sin pandas
disponible en este entorno, se usó `pyarrow.dataset`/`Table.group_by`
directamente).

- Prefijo Silver vaciado, backfill lanzado
  (`madrono-tfm-dev-aforos-peatones-bicicletas-silver-backfill-dedup`) →
  **`SUCCEEDED`** en 182s (364 DPU-s).
- Verificación: descargados los 96 objetos parquet resultantes (768 KB) vía
  `aws s3 sync`, agregados por `(station_id, mode, measured_at)` con
  `pyarrow.Table.group_by(...).aggregate([([], "count_all")])`:
  **1971 filas totales, 1971 grupos, `max n=1`** (antes: `n=6`, confirmado
  en la tarea anterior). Todos los `measured_at` caen en `2024-06-30` (el
  CSV histórico de origen es de un único día, tarea 040) — coherente, no es
  un hueco.
- Prefijo Gold vaciado
  (`gold/aforos_peatones_bicicletas_por_estacion_modo_hora/`), backfill
  lanzado → **`SUCCEEDED`** en 62s (124 DPU-s).
- Verificación Gold: **1971 filas** (mismo número que los grupos de Silver,
  la agregación es por `station_id`/`mode`/`hora` con un único día de
  datos, así que coincide 1:1), 83 estaciones distintas, 2 modos
  (`peatones`/`bicicletas`), `sum(samples_count) = 1971` (1 muestra por
  grupo, coherente con un único CSV sin repeticiones).

## Resumen antes/después

| Dataset | Clave de deduplicación | `n` antes | `n` después | Gold verificado |
|---|---|---|---|---|
| `ruido` | `(station_id, period, measured_date)` | 6 | **1** | Sí, sin huecos |
| `cams_calidad_aire` | `(pollutant, latitude, longitude, valid_datetime, forecast_issued_at)` | 10 | **1** | Sí, sin huecos |
| `aforos_peatones_bicicletas` | `(station_id, mode, measured_at)` | 6 | **1** | Sí, coherente (pyarrow) |

## Recursos AWS tocados en esta sesión (región `eu-west-1`, cuenta `222234418587`)

- **Ningún recurso nuevo de Terraform** — toda la infraestructura ya
  estaba aplicada; `terraform plan -target=...` confirmó "No changes"
  antes de lanzar nada.
- Ejecuciones de Glue lanzadas y esperadas hasta terminar: 6 (Silver+Gold
  × 3 datasets), todas `SUCCEEDED` — **~1.6 DPU-horas totales**
  (446+123+423+126+364+124 = 1606 DPU-s).
- Borrados S3 (Silver y Gold de estos 3 datasets únicamente, nunca
  Bronze, nunca `trafico`/`bicimad`/`agenda_eventos`/`bluesky_menciones`):
  antes de cada backfill se vació el prefijo de destino correspondiente
  (`aws s3 rm --recursive`), siguiendo la lección de la tarea 074
  (`overwrite` de Spark sobre miles de objetos preexistentes puede fallar
  con `MultiObjectDeleteException` intermitente).

## Restricciones respetadas

- No se ha tocado Bronze en ningún dataset.
- No se ha tocado `trafico`, `bicimad`, `agenda_eventos`,
  `bluesky_menciones`, `cartelera_cines_estrenos`, `aemet_prevision_avisos`
  ni `afluencia_lugares`.
- No se ha ejecutado ningún `terraform apply` (no hizo falta, sin drift).
- No se ha reabierto ninguna clave de deduplicación — se usaron
  literalmente las ya documentadas en la tarea anterior.
- Los 3 datasets se completaron enteros (Silver + Gold + verificado) uno
  a uno, sin dejar ninguno a medias.

## Relevante para tareas futuras

- **Serie 072-077 completamente cerrada**: los 8 datasets del grupo diario
  y los 6 del grupo horario tienen ya el arreglo de lectura incremental
  desplegado, y los que tenían duplicación histórica confirmada
  (`trafico`, `bicimad`, `agenda_eventos`, `bluesky_menciones`, `ruido`,
  `cams_calidad_aire`, `aforos_peatones_bicicletas`) están reconstruidos y
  verificados sin duplicados en Silver y Gold.
- Los 6 `aws_glue_job` de backfill de esta tarea (y los del resto de la
  serie) siguen existiendo en AWS como jobs de un solo uso, sin trigger —
  no se han borrado (fuera de alcance; no hay instrucción de limpiarlos y
  no tienen coste salvo que se lancen explícitamente). Si se quiere reducir
  el número de jobs de Glue en la cuenta, una tarea futura podría
  evaluar borrarlos ahora que ya cumplieron su propósito.
- La tabla de Glue Catalog de `aforos_peatones_bicicletas` sigue sin
  corregir su `partition projection` (rango de fechas que excluye sus
  datos reales de 2024) — no forma parte del alcance de esta tarea
  (verificar duplicados, no arreglar la tabla), pero sigue siendo un punto
  a resolver si se quiere consultar este dataset por Athena con
  normalidad en el futuro.
