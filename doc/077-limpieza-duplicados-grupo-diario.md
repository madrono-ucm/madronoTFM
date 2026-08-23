# 077 — Limpieza de duplicados del grupo diario (agenda_eventos, bluesky_menciones; verificación del resto)

## Estado: `agenda_eventos` y `bluesky_menciones` limpios y verificados. 3 datasets más con duplicación confirmada, backfill listo en AWS pero sin lanzar (queda para una tarea de seguimiento).

## 1. Verificación de los 3 datasets sin confirmar (paso 1 del enunciado)

Consulta real sobre la clave natural de cada uno, vía Athena (`madrono-tfm_dev_silver`, tras `MSCK REPAIR TABLE` — los 5 datasets de esta tarea tenían 0 particiones registradas en el Glue Catalog pese a tener datos reales en S3; ver nota sobre `aforos_peatones_bicicletas` más abajo):

| Dataset | Clave natural consultada | Resultado |
|---|---|---|
| `ruido` | `(station_id, period, measured_date)` | **Duplicación real, `n=6`** (p.ej. `RF-03/T/2026-08-13`) |
| `cams_calidad_aire` | `(pollutant, latitude, longitude, valid_datetime, forecast_issued_at)` | **Duplicación real, `n=10`** (p.ej. `NO2/40.45/-3.75/2026-08-17T04:00...`) |
| `aforos_peatones_bicicletas` | `(station_id, mode, measured_at)` | **Duplicación real, `n=6`** — ver nota abajo, no verificable con Athena directamente |

Los tres tienen duplicación real, a la misma escala (decenas, `n=6`-`n=10`) que `agenda_eventos`/`bluesky_menciones`, coherente con la cadencia diaria del grupo (mucha menos que `trafico`/`bicimad`).

### Nota: `aforos_peatones_bicicletas` no es consultable con Athena tal cual

La tabla de Glue Catalog de este dataset tiene `partition projection` habilitada con `projection.fecha.range = "2026-08-01,NOW+1DAY"` — pero los datos reales de este dataset son un único CSV histórico de 2024 (`fecha=2024-06-29`/`2024-06-30`, ver tarea 040), **fuera de ese rango**. Con partition projection activa, Athena calcula qué prefijos S3 mirar a partir del rango configurado, sin consultar nunca las particiones reales registradas en el Glue Catalog — cualquier `SELECT` sobre esta tabla devuelve 0 filas silenciosamente, sin error, aunque `MSCK REPAIR TABLE`/`SHOW PARTITIONS` sí las liste. Se verificó la duplicación descargando los 144 objetos parquet reales (1.7 MB) y agregando con `pyarrow` directamente en Python, sin pasar por Athena: `n=6` para `(station_id, mode, measured_at)` — exactamente el patrón esperado (6 ejecuciones históricas del pipeline, cada una reescribiendo el CSV completo de un año de golpe, mismo bug que el resto del grupo). No se ha corregido el rango de projection de esta tabla (fuera de alcance de esta tarea); una tarea futura que necesite consultar este dataset por Athena con normalidad debería ajustar `projection.fecha.range` para que cubra también 2024, o quitar partition projection en favor de particiones registradas explícitamente.

## 2. Limpieza completada: `agenda_eventos` y `bluesky_menciones`

Mismo patrón que las tareas 073/074/075 (job de Glue de un solo uso, fuera del pipeline incremental, reutilizando la normalización de `glue_bronze_to_silver.py`): nuevos ficheros
`procesamiento/silver_gold/{agenda_eventos,bluesky_menciones}/glue_backfill_dedup.py` (Silver, `dropDuplicates` + `overwrite`) y `glue_backfill_dedup_gold.py` (Gold, misma agregación de producción sobre el histórico completo, `overwrite`), más sus `aws_glue_job`/`aws_s3_object` en `infra/terraform/glue.tf`.

Claves de deduplicación usadas (las mismas ya identificadas como clave natural en el propio código de `transform.py`/`aggregate.py` de cada dataset, no inventadas para esta tarea):
- `agenda_eventos`: `event_id` (ver docstring de `transform.py`: "clave natural imprescindible para poder deduplicar reingestas").
- `bluesky_menciones`: `post_hash` (SHA-256 truncado del texto, ver docstring de `transform.py`).

Antes de lanzar cada job, se vació a mano el prefijo de destino (`aws s3 rm --recursive`) — lección de la tarea 074: un `overwrite` de Spark sobre miles de objetos preexistentes puede fallar con `MultiObjectDeleteException` intermitente y abortar la escritura sin dejar nada nuevo.

### Resultados reales

| Dataset | Job | Duración | DPU-s | Resultado |
|---|---|---|---|---|
| `agenda_eventos` | silver-backfill-dedup | 231s | 463 | `SUCCEEDED` |
| `agenda_eventos` | gold-backfill-dedup | 131s | 262 | `SUCCEEDED` |
| `bluesky_menciones` | silver-backfill-dedup | 232s | 464 | `SUCCEEDED` |
| `bluesky_menciones` | gold-backfill-dedup | 61s | 123 | `SUCCEEDED` |

Verificación post-backfill con Athena (misma consulta que confirmó la duplicación original):

```sql
SELECT event_id, COUNT(*) AS n FROM agenda_eventos GROUP BY event_id ORDER BY n DESC LIMIT 3
-- n=1 en las 3 filas (antes: n=56)

SELECT post_hash, COUNT(*) AS n FROM bluesky_menciones GROUP BY post_hash ORDER BY n DESC LIMIT 3
-- n=1 en las 3 filas (antes: n=19)
```

Ambos datasets quedan sin duplicados en Silver, con Gold recalculado desde el Silver ya limpio.

## 3. Pendiente: `aforos_peatones_bicicletas`, `ruido`, `cams_calidad_aire`

**Duplicación confirmada (paso 1), pero el backfill NO se ha lanzado** — se agotó el presupuesto de esta sesión tras completar `agenda_eventos`/`bluesky_menciones` (prioridad explícita del enunciado). Sí se ha dejado todo el código y la infraestructura lista para que una tarea de seguimiento solo tenga que lanzar y verificar:

- `procesamiento/silver_gold/{aforos_peatones_bicicletas,ruido,cams_calidad_aire}/glue_backfill_dedup.py` + `glue_backfill_dedup_gold.py` — mismo patrón, ya escritos.
- Claves de deduplicación usadas:
  - `aforos_peatones_bicicletas`: `(station_id, mode, measured_at)` — `mode` distingue las dos redes de estaciones (peatones/bicicletas) que comparten el campo `count` (ver docstring de `transform.py`).
  - `ruido`: `(station_id, period, measured_date)` — misma clave que agrupa `aggregate.py` para el resumen diario. El backfill de Gold recalcula la media móvil de 7 días (`Window.rangeBetween`) sobre el histórico completo, no solo "hoy" como hace el pipeline incremental.
  - `cams_calidad_aire`: `(pollutant, latitude, longitude, valid_datetime, forecast_issued_at)` — identifica una previsión individual real (contaminante + punto de rejilla + instante previsto + corrida de modelo que la generó); `leadtime_hour` es redundante con `valid_datetime - forecast_issued_at`, no hace falta en la clave.
- Los 6 `aws_glue_job` correspondientes (Silver + Gold × 3 datasets) y sus `aws_s3_object` de script ya están **aplicados en AWS real** (ver sección siguiente) — una tarea de seguimiento solo necesita:
  1. Vaciar el prefijo de destino (`aws s3 rm --recursive`, Silver y luego Gold) antes de cada lanzamiento.
  2. `aws glue start-job-run --job-name madrono-tfm-dev-<dataset>-silver-backfill-dedup`, esperar, repetir con `-gold-backfill-dedup`.
  3. Verificar con la misma consulta Athena que confirmó la duplicación en el paso 1 de esta tarea (ahora debe dar `n=1`) — para `aforos_peatones_bicicletas`, recordar que Athena no sirve (ver nota de partition projection arriba); verificar con `pyarrow` sobre los ficheros reales, igual que se hizo aquí.

**Importante: los prefijos S3 de Silver/Gold de estos 3 datasets NO se han tocado en esta sesión** (a diferencia de `agenda_eventos`/`bluesky_menciones`, cuyos prefijos sí se vaciaron y reconstruyeron por completo) — siguen en su estado original (con la duplicación confirmada, pero con datos), listos para que la tarea de seguimiento los reconstruya sin haber perdido nada.

## Recursos AWS aplicados en esta sesión (región `eu-west-1`, cuenta `222234418587`)

`terraform apply` (acotado con `-target`, nunca sin acotar ni con `terraform destroy`) sobre:

- **20 recursos nuevos**: 4 por cada uno de los 5 datasets (`agenda_eventos`, `bluesky_menciones`, `aforos_peatones_bicicletas`, `ruido`, `cams_calidad_aire`) — `aws_s3_object` + `aws_glue_job` para el backfill de Silver, y lo mismo para Gold.
- **33 actualizaciones + 1 reemplazo**: `aws_s3_object.procesamiento_source` (el zip compartido de `procesamiento/` que empaquetan `--extra-py-files`) cambió de contenido al añadir los 10 ficheros `glue_backfill_dedup*.py` nuevos, forzando un nuevo hash/key en S3 — mismo escenario ya documentado en las tareas 072/075/076. Siguiendo esa lección, el `-target` se amplió para incluir **todos** los `aws_glue_job` que referencian ese artefacto (36 jobs: los 14 Bronze→Silver de producción, sus Silver→Gold con `--extra-py-files`, y los backfill de Silver ya existentes de tareas previas), no solo los 5 de esta tarea — así todos quedan apuntando de forma consistente al mismo zip nuevo en el mismo `apply`, sin dejar ningún job de producción con un `--extra-py-files` roto. Verificado con `terraform plan` (mismo `-target`) tras el apply: **"No changes"**.
- Ningún IAM, ningún trigger, ninguna tabla de Glue Catalog se ha tocado — confirmado en el plan (0 recursos de esos tipos en la lista de cambios).
- Ejecuciones de Glue lanzadas y esperadas hasta terminar: 4 (`agenda_eventos` silver+gold, `bluesky_menciones` silver+gold), todas `SUCCEEDED`, ~2.9 DPU-horas totales.
- Borrados S3 (Silver y Gold de `agenda_eventos`/`bluesky_menciones` únicamente, nunca Bronze, nunca `trafico`/`bicimad`/resto del grupo horario): antes de cada backfill, se vació el prefijo de destino correspondiente.

## Restricciones respetadas

- No se ha tocado `trafico`/`bicimad` ni el resto del grupo horario.
- No se ha tocado Bronze en ningún dataset.
- No se ha tocado `cartelera_cines_estrenos`, `aemet_prevision_avisos` ni `afluencia_lugares`.
- No se ha desactivado ningún trigger de este grupo (no se han tocado triggers en absoluto en esta sesión).
- `agenda_eventos` y `bluesky_menciones` se completaron por entero (Silver + Gold + verificado) antes de pasar al siguiente paso, siguiendo la prioridad explícita del enunciado.

## Relevante para tareas futuras

- Tarea de seguimiento pendiente: lanzar y verificar el backfill ya preparado de `aforos_peatones_bicicletas`, `ruido` y `cams_calidad_aire` (jobs de Glue ya aplicados en AWS, solo falta `start-job-run` + esperar + verificar, ver sección 3).
- La tabla de Glue Catalog de `aforos_peatones_bicicletas` tiene `partition projection` con un rango de fechas que excluye sus datos reales (2024) — Athena no es utilizable para este dataset sin corregir `projection.fecha.range` antes. Cualquier verificación futura sobre este dataset debe usar `pyarrow` directamente sobre S3, o corregir la tabla primero.
- Confirmado, una vez más (cuarta vez tras las tareas 072/075/076), que cualquier cambio a `procesamiento/` que se aplique con `terraform apply -target` debe ampliar el `-target` a todos los `aws_glue_job` que consumen `aws_s3_object.procesamiento_source`, no solo los del dataset que se esté tocando.
