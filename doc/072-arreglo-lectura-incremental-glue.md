# 072 — Arreglo de la lectura incremental Bronze→Silver→Gold (coste de Glue descontrolado)

## Estado: PARCIAL, sin aplicar en AWS — commiteado a propósito así (ver enunciado, "un resultado a medias documentado es preferible a un intento perdido")

Esta sesión se quedó sin presupuesto antes de completar el alcance. Lo que
sigue documenta honestamente qué se arregló, qué falta, y por qué los 6
triggers horarios **siguen desactivados** (no se ha revertido la mitigación
de emergencia aplicada antes de esta tarea).

## Diagnóstico (confirmado, no solo heredado del enunciado)

Los 28 jobs (`glue_bronze_to_silver.py`/`glue_silver_to_gold.py` de los 14
datasets) leían siempre la raíz completa de su dataset de origen
(`spark.read...json(args["bronze_path"])` / `spark.read.parquet(args["silver_path"])`),
sin filtro de fecha/hora — cada ejecución reprocesaba todo el histórico
acumulado, coste creciente sin límite. Coste real acumulado hasta el
momento de crear esta tarea (`aws glue get-job-runs`):

| Job | Runs | DPU-horas |
|---|---|---|
| `bicimad-silver-to-gold` | 45 | 37.85 |
| `trafico-silver-to-gold` | 44 | 29.75 |
| `trafico-bronze-to-silver` | 50 | 20.04 |
| `bicimad-bronze-to-silver` | 48 | 10.79 |
| resto (p.ej. `aparcamientos-silver-to-gold`) | 48 | 1.61 (normal) |

## Diseño elegido: partición por reloj, no Job Bookmarks

AWS Glue Job Bookmarks es el mecanismo nativo para "procesar solo lo nuevo",
pero ya está deshabilitado a propósito en los 28 jobs
(`"--job-bookmark-option" = "job-bookmark-disable"`) y activarlo ahora habría
significado que la *primera* ejecución con bookmarks tuviese que recorrer
igualmente todo el histórico ya acumulado antes de poder ser incremental —
justo la ejecución cara que hay que evitar dada la urgencia real del coste.
Se ha optado por calcular la partición Hive (`fecha=/hora=`) a leer a partir
del reloj (instante en que corre el job, `datetime.now(MADRID_TZ)`), barato
desde la primera ejecución. Implementado en el módulo nuevo
`procesamiento/silver_gold/incremental.py` (Python puro + un único helper
con `boto3` inyectable, testeado en `procesamiento/tests/test_incremental.py`,
15 tests, todos en verde, sin `pyspark` instalado).

- **Grupo horario** (`trafico`, `transporte_publico_emt`, `bicimad`,
  `aparcamientos`, `calidad_aire`, `meteorologia`): lee la hora completa
  **anterior** a la ejecución (`previous_hour`) — el trigger dispara en el
  minuto 10 de cada hora, momento en que esa hora ya está completa.
- **Grupo diario** (`ruido`, `agenda_eventos`, `bluesky_menciones`,
  `afluencia_lugares`, `aforos_peatones_bicicletas`,
  `cartelera_cines_estrenos`, `aemet_prevision_avisos`, `cams_calidad_aire`):
  Bronze→Silver lee la partición de **hoy** (`today`) — esto es siempre
  correcto porque Bronze particiona por fecha/hora de *ingesta*
  (`ingesta/capturas/bronze.py`), nunca por el contenido.
- Cada job comprueba con `partition_has_objects` (lista S3, `MaxKeys=1`) si
  la partición objetivo tiene datos antes de leer; si no, `job.commit()` y
  sale sin más coste.

## Hecho en esta sesión

- `procesamiento/silver_gold/incremental.py` (nuevo) + sus tests.
- **Bronze→Silver de los 14 datasets**: los 14 scripts ya leen solo la
  partición Bronze correspondiente (hora anterior o día de hoy, según
  grupo), con guarda de partición vacía. Este es el que más DPU-horas
  concentraba (`trafico-bronze-to-silver` 20.04h, `bicimad-bronze-to-silver`
  10.79h) — **arreglado para los 14 datasets**.
- **Silver→Gold de los 6 datasets del grupo horario** (`trafico`,
  `transporte_publico_emt`, `bicimad`, `aparcamientos`, `calidad_aire`,
  `meteorologia`): ya leen solo la partición Silver de la hora anterior,
  reconstruyendo `fecha`/`hora` (columnas de partición que Spark deja de
  inferir al acotar la ruta) recalculándolas desde la misma columna de
  timestamp que usa el `write` correspondiente (`measured_at`/`ingested_at`,
  ver comentarios en cada script) — **arreglado**, incluye los dos jobs más
  caros de la tabla (`bicimad-silver-to-gold` 37.85h,
  `trafico-silver-to-gold` 29.75h).

## NO hecho (pendiente de una sesión futura)

- **Silver→Gold de los 8 datasets del grupo diario sigue leyendo la raíz
  completa de Silver, sin narrowear.** Se investigó en profundidad el campo
  origen de cada partición `fecha` de Silver para diseñar el filtro correcto
  (varios de estos datasets tienen contenido con fecha *distinta* del día de
  ingesta: `ruido` publica con 1 día de retraso; `agenda_eventos` lista
  eventos hasta 100 días vista; `aemet_prevision` hasta 7 días vista;
  `cams_calidad_aire` hasta 4 días/96h vista — un filtro ingenuo de "solo
  hoy" perdería silenciosamente casi todos esos datos nuevos), pero no dio
  tiempo a implementar y testear el arreglo con la misma seguridad que el
  resto. Diseño ya decidido para retomar directamente (evita rehacer el
  análisis):
  - `bluesky_menciones`, `afluencia_lugares`, `aforos_peatones_bicicletas`,
    `cartelera_cines_estrenos`: narrowear a `fecha=hoy/` (su contenido sí
    coincide con el día de ingesta), reconstruyendo `fecha` desde la columna
    de timestamp original igual que el grupo horario.
  - `ruido`: leer ventana `date_range(processed_at, -7, -1)` (7 días
    terminando ayer, ya existe en `incremental.py`), sin reconstruir
    `fecha` (usa `measured_date`, columna de datos real, no partición) y
    **filtrar la salida a `date == ayer`** antes de escribir Gold (si no,
    se reintroduce duplicación de los 6 días ya escritos en ejecuciones
    anteriores).
  - `agenda_eventos`: narrowear Bronze a hoy (ya hecho); Silver→Gold leer
    `date_range(processed_at, 0, 100)`, reconstruyendo `fecha` desde
    `start_datetime` por cada partición leída (no un único literal, cada
    partición unida por separado con `unionByName`).
  - `aemet_prevision`/`aemet_avisos`/`cams_calidad_aire`: sus jobs de
    Silver→Gold **ya recalculan** `fecha`/`fecha_validez` desde una columna
    de datos real (`valid_date`, `effective_from`, `valid_datetime`) en vez
    de depender de la columna de partición — no necesitan reconstrucción,
    solo acotar qué particiones leer: `date_range(processed_at, 0, 7)`
    (prevision), `date_range(processed_at, -1, 3)` (avisos, conservador),
    `date_range(processed_at, 0, 4)` (cams).
  - Usar `existing_daily_partitions()` (ya en `incremental.py`) para
    filtrar a las particiones que realmente existen antes de leer/unir.
- **`terraform apply` no se ha ejecutado.** El código corregido (Bronze→Silver
  completo + Silver→Gold horario) no está desplegado en AWS todavía.
- **No se ha verificado con ninguna ejecución real** de `trafico`/`bicimad`.
- **Los 6 triggers `SCHEDULED` del grupo horario siguen desactivados**
  (mitigación de emergencia aplicada antes de esta tarea, fuera de su
  alcance) — correcto no reactivarlos sin verificación real, tal como pedía
  el enunciado explícitamente.
- Los 8 triggers del grupo diario siguen activos sin cambios (como pedía el
  enunciado), pero sus jobs Silver→Gold correspondientes **no** están
  arreglados todavía — seguirán acumulando coste (aunque, según la propia
  tabla de diagnóstico, a un ritmo "normal", no descontrolado, para estos 8
  datasets de menor volumen).

## Próximos pasos exactos para continuar

1. Implementar el Silver→Gold de los 8 datasets diarios según el diseño ya
   fijado arriba.
2. Añadir/actualizar tests de `procesamiento/tests/` para los nuevos casos
   (ventanas multi-día, filtrado de salida de `ruido`).
3. `terraform apply` **acotado con `-target`** a los 28 `aws_glue_job` (y
   solo esos — no tocar Kafka ni nada no relacionado, mismo patrón que las
   tareas 065/068).
4. Forzar una ejecución real de `trafico` y `bicimad` (Bronze→Silver y
   Silver→Gold) y confirmar con `aws glue get-job-runs` que la duración/
   DPU-segundos vuelve a ser del orden de una hora de datos, no del
   histórico completo.
5. Solo entonces, `aws glue start-trigger` sobre los 6 triggers horarios.
6. Actualizar este documento con el resultado real de la verificación.

## Restricciones respetadas

- No se ha ejecutado `terraform apply` (ni con ni sin `-target`): no había
  nada verificado que desplegar de forma responsable dentro del presupuesto
  restante.
- No se han reactivado los 6 triggers horarios.
- No se ha tocado el grupo diario (8 triggers) ni su infraestructura.
- No se ha ejecutado `terraform destroy` ni ninguna otra operación
  destructiva.
- No se ha escrito ni dejado nada programado (cron/systemd/bucle) en esta
  EC2.
