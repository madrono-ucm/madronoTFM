---
kind: fil
title: "Gold de ruido (11 días) y aemet_avisos (8 días) estancado pese a jobs SUCCEEDED a diario — silver_to_gold escribe 0 filas en silencio"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-29"
---

> **Contexto**: encontrado en `VIC_09` (evaluación técnica de
> `procesamiento/`, [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md)),
> comprobando la frescura real de los 16 datasets en producción continua
> contra Athena. Es la misma familia de bug que ya rompió `aparcamientos`
> (tareas 072/075) y `cartelera_cines_estrenos` (tarea 090): el job de Glue
> reporta `SUCCEEDED` cada día pero escribe **cero filas nuevas**, sin que
> nada lo señale como error.

## Qué está roto (verificado en vivo)

### `ruido_por_estacion_periodo_fecha` (Gold) — estancado en `2026-08-19`, 11 días

- **Bronze**: fresco, partición `fecha=2026-08-28/` con datos reales
  (verificado tamaño de fichero no-cero).
- **Silver**: avanza hasta `fecha=2026-08-26/` (con un hueco real en
  `fecha=2026-08-21/`-`22/`, sin investigar en este ticket — puede ser una
  fuente que no publica fin de semana, o un bug de bronze→silver aparte).
- **Gold**: `aws s3 ls .../ruido_por_estacion_periodo_fecha/` → última
  partición real `date=2026-08-19/`. **Ninguna partición nueva desde
  entonces**, pese a que `madrono-tfm-dev-ruido-silver-to-gold` tiene
  ejecuciones `SUCCEEDED` diarias (`aws glue get-job-runs`, incluida la de
  hoy 2026-08-29T19:50).

**Hipótesis de causa raíz** (revisar, no asumir sin comprobar):
`procesamiento/silver_gold/ruido/glue_silver_to_gold.py` lee una ventana de
`ROLLING_WINDOW_DAYS` (7) días de Silver para calcular la media móvil, pero
**filtra la escritura a una sola fila: `gold_df.filter(F.col("date") ==
today(processed_at))`** antes de hacer `write.mode("append")`. Si por
cualquier motivo la fila de "hoy" no aparece en el `groupBy` (p. ej. un
desfase entre `measured_date` de la fuente y `today()` calculado por el
job), el DataFrame a escribir queda vacío, Spark no escribe ninguna
partición, y `job.commit()` se ejecuta igual → `SUCCEEDED` con 0 filas
nuevas, indefinidamente, sin ninguna alerta.

### `aemet_avisos_por_zona_fecha_nivel` (Gold) — estancado en `processed_at` del `2026-08-22`, 8 días

- **Bronze**: fresco y con **datos reales, no vacíos** — verificado
  descargando `aemet_avisos/fecha=2026-08-29/hora=23/...json`: 8 avisos CAP
  reales (nivel "verde", avisos de temperatura, `effective_from
  2026-08-31`). No es un día "sin avisos que reportar".
- **Gold**: `max(processed_at)` = `2026-08-22T08:19:44`. El job
  `madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold` sí tiene
  ejecuciones `SUCCEEDED` recientes (28/8, 29/8) — pero esas ejecuciones
  refrescan **solo la salida de `prevision`** (`aemet_prevision_por_municipio_leadtime`
  tiene `processed_at` del 29/8, fresco); la salida de **`avisos`** no se
  actualiza desde el 22/8 pese a que el mismo job "SUCCEEDED" y pese a que
  Bronze tiene avisos reales cada día desde entonces.

**Hipótesis de causa raíz**: `procesamiento/silver_gold/aemet_prevision_avisos/glue_silver_to_gold.py`
lee la salida de avisos con
`silver_avisos_partition_path = daily_partition_uri(args["silver_avisos_path"], today(processed_at))`
+ `if partition_has_objects(...)`. Si la partición de Silver para
`fecha=<today>` de avisos no coincide con lo que el job espera (posible
desalineación entre la fecha de partición de Silver-avisos y `today()`, a
confirmar mirando cómo se particiona `silver_avisos` en
`glue_bronze_to_silver.py` de este mismo dataset), el `if` nunca es cierto
y la rama de avisos simplemente no escribe nada — silenciosamente, sin
tocar el resultado de `prevision` que sí sigue funcionando.

## Por qué importa

Estos dos datasets son 2 de los 16 "productores en producción continua"
que describe la memoria (`VIC_02`). Sin datos frescos, cualquier
consumidor (el asistente, `modelado/` si algún día usa ruido/avisos como
feature) trabajaría sobre datos de hace más de una semana sin ningún aviso
de que están obsoletos.

## Qué investigar / hacer (sin aplicar nada aquí)

1. Confirmar en detalle, leyendo `glue_bronze_to_silver.py` de cada
   dataset, cómo se calcula/particiona la fecha de Silver, y contrastarla
   con `today(processed_at)` tal como lo usa `glue_silver_to_gold.py` — el
   objetivo es encontrar el desfase exacto (posible timezone, posible
   `effective_from` vs fecha de captura, posible cambio de esquema de
   partición no reflejado en el job de Gold).
2. Una vez identificado, proponer el fix (puede ser tan simple como el que
   ya se aplicó a `cartelera_cines_estrenos`/`agenda_eventos`/
   `bluesky_menciones` en la tarea 090 — recuperar la columna de partición
   tras acotar la lectura, o ajustar qué fecha se usa para filtrar la
   salida) — **como ticket `FIL_*` aparte con el diff propuesto**, no
   aplicado directamente aquí.
3. Tras el fix, forzar (o esperar) una ejecución real y confirmar en
   Athena que ambos Gold avanzan más allá de sus fechas actuales.
4. Investigar también el hueco de Silver de `ruido` en
   `fecha=2026-08-21`/`22` (aparte, puede no ser el mismo bug).

## Restricciones

- No se ha tocado ningún código de `procesamiento/` en este ticket — es
  solo el hallazgo, verificado contra AWS real (Bronze/Silver/Gold en S3 +
  Athena + `aws glue get-job-runs`).
- Cualquier fix debe verificarse contra datos reales (no basta con que el
  job "SUCCEEDED" — ya sabemos que eso no es suficiente señal para este
  bug).

## Criterios de aceptación

- Causa raíz confirmada (no solo la hipótesis de arriba) para ambos casos.
- `ruido_por_estacion_periodo_fecha` y `aemet_avisos_por_zona_fecha_nivel`
  con datos posteriores a sus fechas actuales de estancamiento, verificado
  en Athena real tras el fix.
- Documentado en un `doc/FIL-11-...md` o similar.
