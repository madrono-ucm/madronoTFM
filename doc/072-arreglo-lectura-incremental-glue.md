# 072 — Arreglo de la lectura incremental Glue: `trafico` y `bicimad` (alcance reducido, URGENTE)

## Estado: COMPLETO para `trafico`/`bicimad` — aplicado en AWS, verificado con ejecución real, triggers reactivados

Esta es la **segunda** versión de esta tarea. Una primera versión con alcance
completo (14 datasets, 28 ficheros) agotó el presupuesto de una sesión previa
sin comitear nada (aunque sí dejó comiteado, en una sesión anterior a esa,
el código de `incremental.py` + la lectura incremental de Bronze→Silver para
los 14 datasets y de Silver→Gold horario para 6 de ellos — commit
`049d83b`, ya en el historial de esta rama). Esta tarea se reescribió con
**alcance reducido a los dos jobs en TIMEOUT activo** (`trafico`/`bicimad`)
para no repetir el mismo fallo; el resto queda para las tareas 073/074.

## Diagnóstico confirmado al empezar esta sesión

`aws glue get-job-runs` sobre los 4 jobs de `trafico`/`bicimad` mostró
`trafico-silver-to-gold` y `bicimad-silver-to-gold` terminando en `TIMEOUT`
(cortados a los 30 min configurados) en ejecuciones consecutivas, facturando
la hora completa de DPU en cada intento fallido sin llegar a actualizar
Gold. Acumulado histórico real en estos 4 jobs (`aws glue get-job-runs`,
sumando `DPUSeconds` de todas las ejecuciones):

| Job | Runs | DPU-horas acumuladas |
|---|---|---|
| `bicimad-silver-to-gold` | 47 | 37.90 |
| `trafico-silver-to-gold` | 46 | 30.79 |
| `trafico-bronze-to-silver` | 52 | 20.23 |
| `bicimad-bronze-to-silver` | 50 | 10.98 |
| **Total** | | **~99.9 DPU-horas ≈ 44 USD** (tarifa estándar Glue, eu-west-1) |

Causa raíz: `spark.read...json(args["bronze_path"])`/
`spark.read.parquet(args["silver_path"])` leían siempre la **raíz completa**
del dataset, sin filtro de fecha/hora — cada ejecución reprocesaba todo el
histórico acumulado desde el principio.

Los 6 triggers `SCHEDULED` horarios seguían desactivados (mitigación de
emergencia previa a esta tarea) — confirmado al empezar con `aws glue
get-trigger` sobre los 2 de `trafico`/`bicimad`: ambos `DEACTIVATED`, sus
`CONDITIONAL` de Silver→Gold hermanos seguían `ACTIVATED` (nunca se tocan,
solo disparan cuando su Bronze→Silver completa).

## Arreglo aplicado (código ya existente en el commit `049d83b`, verificado y desplegado en esta sesión)

Los 4 ficheros ya usaban `procesamiento/silver_gold/incremental.py`
(`previous_hour()`, `hourly_partition_uri()`, `partition_has_objects()`) para
acotar cada ejecución a la partición Hive (`fecha=/hora=`) de la hora
completa **anterior** a la ejecución, en vez de la raíz del dataset — código
ya escrito y testeado (15 tests en `procesamiento/tests/test_incremental.py`,
sin `pyspark` instalado) por la sesión anterior. Bronze→Silver recalcula
`fecha`/`hora` para escribir con el mismo esquema de partición que Bronze;
Silver→Gold recalcula las mismas columnas para agrupar antes de escribir
Gold. Nada de esta lógica se ha reescrito en esta sesión.

## Bug nuevo encontrado y arreglado en esta sesión (bloqueaba la verificación real)

Dos problemas reales, ambos necesarios para que el arreglo funcionase
end-to-end, no solo para que compilase:

### 1. `--extra-py-files` que faltaba en los jobs Silver→Gold

`trafico/glue_silver_to_gold.py` y `bicimad/glue_silver_to_gold.py` hacen
`from procesamiento.silver_gold.incremental import (...)`, pero sus
`aws_glue_job` en `glue.tf` no llevaban el argumento `--extra-py-files`
(a diferencia de los jobs Bronze→Silver, que sí lo llevan desde la tarea
041) — sin él, ese import habría fallado con `ModuleNotFoundError` al
ejecutar de verdad en Glue (el paquete `procesamiento` no está en el path
por defecto). Añadido a ambos jobs en `infra/terraform/glue.tf`, apuntando
al mismo artefacto compartido (`aws_s3_object.procesamiento_source`) que ya
usan los 14 jobs Bronze→Silver.

**Mismo bug late presente, sin aplicar todavía, en los otros 4 datasets
horarios** (`transporte_publico_emt`, `aparcamientos`, `calidad_aire`,
`meteorologia`) cuyo Silver→Gold ya se arregló en código en la sesión previa
pero nunca se desplegó — confirmado que sus jobs siguen `SUCCEEDED` en AWS
ahora mismo porque siguen ejecutando el código VIEJO (sin ese import). Las
tareas 073/074 deben añadir el mismo `--extra-py-files` a esos 4 jobs
cuando les toque desplegarlos, o fallarán con `ModuleNotFoundError` en su
primera ejecución real.

### 2. Timezone de sesión de Spark: `hora` calculada en UTC, no en Madrid

Encontrado solo al forzar una ejecución real (no era detectable con los
tests unitarios, que no ejecutan Spark). `measured_at` en los datos reales
lleva offset explícito (`"2026-08-22T17:00:04+02:00"`), pero
`date_format(to_timestamp("measured_at"), "HH")` calcula la hora en el
**timezone de sesión de Spark**, que en el runtime de Glue usado aquí
resultó ser UTC por defecto (no Europe/Madrid) — una fila medida a las
17:00 hora de Madrid se escribía en la partición `hora=15`.

Esto rompía la cadena end-to-end en silencio: `previous_hour()` (Python,
`Europe/Madrid`, igual que la partición real de Bronze) calculaba
correctamente `hora=17` tanto para decidir qué leer de Bronze como para
decidir qué leer de Silver, pero Bronze→Silver escribía en `hora=15`
(desplazado 2h) — así que Silver→Gold, al buscar `hora=17`, nunca encontraba
la partición que el job hermano acababa de escribir, hacía `job.commit()` y
salía sin escribir nada en Gold. **El primer intento de verificación real de
esta sesión reprodujo exactamente esto**: Bronze→Silver `SUCCEEDED` en 172s
(coste proporcional, correcto), pero Silver→Gold `SUCCEEDED` en solo 30s sin
crear ninguna partición nueva en Gold (no-op silencioso, no un error).

Arreglado añadiendo `spark.conf.set("spark.sql.session.timeZone",
"Europe/Madrid")` justo tras crear la `SparkSession`, en los 4 ficheros
(`{trafico,bicimad}/glue_{bronze_to_silver,silver_to_gold}.py`) — alinea el
cálculo de `fecha`/`hora` en Spark con el mismo timezone que ya usa
`previous_hour()` en Python.

**Mismo riesgo, no verificado, en los otros 12 datasets**: cualquier job
Bronze→Silver/Silver→Gold que recalcule `fecha`/`hora` desde una columna de
datos con `date_format(to_timestamp(...), ...)` sin fijar antes
`spark.sql.session.timeZone` puede sufrir el mismo desfase silencioso. Las
tareas 073/074 deberían añadir la misma línea a sus propios jobs y
verificarlo con una ejecución real antes de darlo por bueno — no basta con
que los tests unitarios (que no ejecutan Spark) pasen en verde.

## Desplegado en AWS (aplicado con `terraform apply -target`, región `eu-west-1`, cuenta `222234418587`)

El artefacto `--extra-py-files` (`aws_s3_object.procesamiento_source`) es
**un único zip compartido por los 14 jobs Bronze→Silver** (todo
`procesamiento/` sin `tests/`, con el contenido indexado por hash en la
`key` de S3). Aplicar solo los 4 recursos de `trafico`/`bicimad` con
`-target` habría forzado igualmente el reemplazo de ese zip compartido
(cambia de contenido en cuanto se añade `incremental.py`), **borrando la key
antigua que los otros 12 jobs Bronze→Silver siguen referenciando en su
configuración ya desplegada** — habría roto su `--extra-py-files` en su
siguiente ejecución real sin tocar ni su código ni sus triggers. Para
evitarlo, el `-target` se amplió a los **14 `aws_glue_job` Bronze→Silver +
los 2 Silver→Gold de `trafico`/`bicimad`** (16 recursos), de forma que los
14 quedan apuntando de forma consistente al mismo zip nuevo en el mismo
`apply`. Esto significa que, como efecto colateral inevitable (no buscado,
pero necesario para no romper nada), **se ha desplegado a producción el
arreglo de lectura incremental de Bronze→Silver ya comiteado para los 14
datasets** (no solo los 2 de esta tarea) — sus triggers y su Silver→Gold
siguen sin tocarse, tal como pedía el enunciado.

Verificado con `terraform plan` antes y después de cada uno de los dos
`apply` de esta sesión (el código cambió dos veces: una vez para
`--extra-py-files`, otra para el timezone) que el plan afectaba
**exclusivamente** a: los 14 `aws_glue_job.*_bronze_to_silver`, los 2
`aws_glue_job.{trafico,bicimad}_silver_to_gold`, sus `aws_s3_object` de
script/librería compartida — ningún IAM, ningún trigger, ninguna tabla de
Glue Catalog, nada de Kafka. Confirmado con `terraform plan` final: sin
cambios pendientes en estos 16 recursos.

## Verificación con ejecución real

Tras el segundo `apply` (con el fix de timezone ya desplegado):

| Job | Antes (histórico, con el bug) | Después (esta sesión, verificado) |
|---|---|---|
| `trafico-bronze-to-silver` | ~880s / ~1760 DPU-s por ejecución, creciendo | **179s / 359 DPU-s** |
| `bicimad-bronze-to-silver` | ~475s / ~950 DPU-s por ejecución, creciendo | **178s / 356 DPU-s** |
| `trafico-silver-to-gold` | `TIMEOUT` a los 1801s / 3603 DPU-s | **52s / 104 DPU-s, `SUCCEEDED`** |
| `bicimad-silver-to-gold` | `TIMEOUT` (mismo patrón) | **50s / 100 DPU-s, `SUCCEEDED`** |

Confirmado además que Gold recibió datos reales de hoy tras el segundo
intento (`aws s3 ls`): `trafico_por_punto_hora/date=2026-08-22/` (4 ficheros
parquet) y `bicimad_por_estacion_hora/date=2026-08-22/` (1 fichero) — vacío
antes del fix de timezone, con datos después.

Nota de calidad de datos, no bloqueante: el primer intento (antes del fix de
timezone) sí dejó escrita una partición `Silver/fecha=2026-08-22/hora=15/`
para ambos datasets con datos reales pero en la hora "equivocada" (desplazados
2h por el mismo bug). No se ha borrado — son datos válidos, solo con la
partición de hora desplazada, sin impacto en ejecuciones futuras (que ya
calculan la hora correctamente); limpieza opcional para una tarea futura si
se considera necesario.

## Triggers reactivados

```
aws glue start-trigger --name madrono-tfm-dev-trafico-scheduled-bronze-to-silver
aws glue start-trigger --name madrono-tfm-dev-bicimad-scheduled-bronze-to-silver
```

Confirmado con `aws glue get-trigger`: ambos `ACTIVATED`. Sus `CONDITIONAL`
de Silver→Gold ya estaban `ACTIVATED` desde antes (nunca se tocan) y ahora sí
dispararán jobs que completan y escriben Gold de verdad.

## Restricciones respetadas

- `terraform apply` se ejecutó siempre acotado con `-target` (16 recursos,
  ver justificación arriba de por qué 16 y no 4) — nunca sin `-target`,
  nunca `terraform destroy`.
- No se han tocado los otros 4 triggers horarios ni los 8 diarios — solo los
  2 `SCHEDULED` de `trafico`/`bicimad` se han reactivado.
- No se ha forzado ninguna ejecución manual de los otros 12 datasets — el
  único efecto sobre ellos es que su `--extra-py-files` ya desplegado apunta
  al zip nuevo (mismo comportamiento que antes, solo con `incremental.py`
  disponible de más, que no usan); sus triggers siguen exactamente en el
  estado en que estaban al empezar la sesión.
- No se ha escrito ni dejado nada programado (cron/systemd/bucle) en esta
  EC2 — la verificación fue un `start-job-run` puntual por job, con
  `get-job-run` en bucle de sondeo hasta que cada uno terminó, sin dejar
  nada corriendo en background al terminar la sesión.
- `backend.hcl` (copia local de `backend.hcl.example`) y los artefactos de
  `terraform init`/`plan` (`.terraform/`, `.terraform.lock.hcl`, ficheros
  `.tfplan`) se eliminan al terminar la sesión — no se commitea nada de
  esto.

## Relevante para tareas futuras (073/074)

- **Diseño de partición por reloj ya validado end-to-end con datos reales**
  (no solo en teoría): `previous_hour()`/`hourly_partition_uri()`/
  `partition_has_objects()` de `incremental.py` funcionan correctamente
  contra Glue/S3 reales, una vez fijado el timezone de sesión de Spark.
- **Añadir siempre `spark.conf.set("spark.sql.session.timeZone",
  "Europe/Madrid")`** justo tras crear la `SparkSession`, en cualquier job
  que recalcule `fecha`/`hora` con `date_format(to_timestamp(...), ...)` —
  sin esto, el job puede terminar `SUCCEEDED` sin ningún error visible y aun
  así no escribir nunca la partición correcta (no-op silencioso). No es
  detectable con los tests unitarios existentes (no ejecutan Spark); solo se
  detectó forzando una ejecución real en esta sesión.
- **Añadir `--extra-py-files` a cualquier job Silver→Gold que importe algo
  de `procesamiento/`** (ya lo necesitan, según el código ya comiteado en
  `049d83b`, los 4 datasets horarios restantes: `transporte_publico_emt`,
  `aparcamientos`, `calidad_aire`, `meteorologia`) — de lo contrario fallará
  con `ModuleNotFoundError` en su primera ejecución real tras el despliegue.
- **El artefacto `procesamiento_source` es compartido por los 14 jobs
  Bronze→Silver.** Cualquier `terraform apply -target` que toque este
  artefacto (lo hará en cuanto se modifique cualquier fichero de
  `procesamiento/`, incluido añadir código nuevo) debe incluir en el
  `-target` **todos** los `aws_glue_job` que lo consumen (los 14
  Bronze→Silver, más cualquier Silver→Gold al que se le añada
  `--extra-py-files`), no solo los del dataset que se esté arreglando —
  de lo contrario el `apply` borra la key S3 antigua y rompe en silencio
  los jobs no incluidos en el `-target` en su siguiente ejecución real.
- Sigue pendiente (fuera de esta tarea, ver tareas 073/074): Silver→Gold de
  los 8 datasets diarios (sin narrowear todavía) y Silver→Gold de los otros
  4 datasets horarios (código ya escrito en `049d83b`, sin desplegar, con
  los dos mismos riesgos de arriba pendientes de aplicar antes de
  desplegar).
- Los dos bugs de Silver vacío ya conocidos desde la tarea 063
  (`cartelera_cines_estrenos_silver_to_gold`, `afluencia_lugares_silver_to_gold`
  sin `--extra-py-files`) siguen sin resolver, sin relación con esta tarea.
