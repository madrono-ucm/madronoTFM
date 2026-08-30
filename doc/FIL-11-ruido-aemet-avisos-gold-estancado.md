# FIL-11 — `ruido` y `aemet_avisos` Gold congelados: `silver_to_gold` filtraba a "hoy"

Hallazgo de `VIC_09` (evaluación técnica de `procesamiento/`). Dos jobs
Silver→Gold daban `SUCCEEDED` a diario **escribiendo 0 filas**, sin ninguna
señal de error — misma familia que `aparcamientos` (072/075) y
`cartelera_cines_estrenos` (090).

## Causa raíz (confirmada, no hipótesis)

### `ruido_por_estacion_periodo_fecha` — congelado 11 días en `2026-08-19`

`procesamiento/silver_gold/ruido/glue_silver_to_gold.py` leía la ventana de
`ROLLING_WINDOW_DAYS` (7) para la media móvil, pero luego **filtraba la
salida a `F.col("date") == today(processed_at)`** y hacía
`write.mode("append")` de solo esa fila. La Red Fija del SIVCA publica sus
medidas con **varios días de retraso** (la partición de Silver más reciente
era `fecha=2026-08-26`, con `today` = `2026-08-30`), así que
`date == today()` **nunca coincidía** → DataFrame vacío → Spark no escribía
ninguna partición → `job.commit()` → `SUCCEEDED` con 0 filas nuevas.

### `aemet_avisos_por_zona_fecha_nivel` — congelado en `2026-08-19`

La rama de avisos de
`procesamiento/silver_gold/aemet_prevision_avisos/glue_silver_to_gold.py`
leía **solo** `Silver/aemet_avisos/fecha=hoy`. Pero `glue_bronze_to_silver.py`
particiona Silver-avisos por el **día de `effective_from`**, que para un
aviso emitido hoy suele ser un día **futuro** → `fecha=hoy` casi nunca tenía
objetos → `partition_has_objects(...)` falso → toda la rama se saltaba en
silencio. Además el `write.mode("append")` había acumulado **hasta 4× la
misma `(zone, fecha, level)`** en Gold (Silver-avisos `fecha=2026-08-19`
tenía part-files re-escritos el 20, 21 y 22).

Matiz: `aemet_avisos` también lleva estancado porque **AEMET solo ha emitido
avisos "verde" desde el 19/8** — filtrados a propósito
(`transform.py`: `VALID_LEVELS = {"amarillo", "naranja", "rojo"}`). Eso es
correcto; el fix cubre el momento en que vuelva a haber un aviso real y
limpia los duplicados existentes.

## Fix

Ambos jobs pasan de `append` + filtro-a-hoy a **`mode("overwrite")` con
`spark.sql.sources.partitionOverwriteMode=dynamic`**: se reescriben
exactamente las particiones presentes en el DataFrame (la ventana de 7 días
de `ruido`; todas las `fecha=` recalculadas de `aemet_avisos`), sin tocar el
resto del histórico. Idempotente, sin duplicados, y **auto-curativo**: cuando
los datos con retraso llegan a Silver, la ejecución siguiente los recoge.
`aemet_avisos` pasa además a leer la **raíz completa** de Silver-avisos
(volumen minúsculo, ~7 KB/día) en vez de una sola partición.

Esto alinea los jobs con `aggregate.py` (la fuente de verdad testada), que
**nunca** filtró por "hoy". Sin cambios en `aggregate.py`/`transform.py`;
59 tests de `procesamiento/` (ruido + aemet) en verde. PRs **#180** (código)
y **#181** (IAM).

### IAM (`s3:DeleteObject`)

La sobrescritura dinámica borra los ficheros de la partición antes de
reescribirla → necesita `s3:DeleteObject` en el prefijo Gold. Se añadió a
`WriteGoldRuidoPorEstacionPeriodoFecha` y
`WriteGoldAemetAvisosPorZonaFechaNivel` (mismo permiso que `FIL_01` tuvo que
añadir al statement de `prevision`). Sin él,
`madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold` falló con
`"One or more objects could not be deleted"` en la primera ejecución tras
desplegar #180.

## Verificación (en vivo, Athena real)

| Tabla | Antes | Después |
|---|---|---|
| `ruido_por_estacion_periodo_fecha` | `max(date) = 2026-08-19` | `max(date) = 2026-08-26` (añadidas 23–26; 20–22 es un hueco real de Silver, ver abajo). `n == uniq` (124), sin duplicados |
| `aemet_avisos_por_zona_fecha_nivel` | `fecha=2026-08-18`: 20 filas / 5 únicas; `fecha=2026-08-19`: 8 / 2 | **de-duplicado**: 5/5 y 2/2. `n == uniq` en todas las fechas |
| `aemet_prevision_por_municipio_leadtime` (control) | fresco | sigue fresco (`processed_at` de hoy) — la rama de previsión del job compartido no se rompió |

## Despliegue

Scripts subidos a sus keys estables (`glue-scripts/{ruido,aemet_prevision_avisos}_silver_to_gold.py`,
key estable desde tarea 107) vía `aws s3 cp`; estado de Terraform
reconciliado con `terraform apply -target` de esos 2 objetos + las 2
policies IAM. Jobs re-lanzados a mano → `SUCCEEDED`.

## Pendiente (fuera de FIL_11)

- **Hueco de Silver de `ruido` en `fecha=2026-08-20`/`21`/`22`** — el ticket
  lo señaló como aparte. Puede ser la fuente sin publicar esos días (la
  propia media móvil ya lo contempla: reduce `laeq_rolling_7d_days` en vez
  de desplazar la ventana) o un fallo de `bronze_to_silver` en esa ventana.
  Sin investigar aquí.
