# 052 — Verificación real Bronze→Silver→Gold de los 6 datasets

## Contexto

La tarea 051 arregló dos bugs de Glue (`saveAsTextFile`/`DirectOutputCommitter`
y `urllib3`/`DEFAULT_CIPHERS`) y dejó un job de sanidad de `trafico`
Bronze→Silver fallando por un tercer problema, ya diagnosticado pero no
arreglado: la política IAM de cada dataset no cubre
`_quality_reports/<dataset>/*` en el bucket Silver, donde
`_write_quality_report` (el arreglo boto3 de la 051) escribe. Esta tarea
completa la verificación real pendiente desde la 051: dos arreglos de
infraestructura adicionales (ambos huecos de permisos IAM, descubiertos
empíricamente en esta sesión) más una ejecución real de Bronze→Silver→Gold
para los 6 datasets del patrón.

**Cambios de infraestructura de esta tarea, aplicados contra la cuenta real
(`222234418587`, región `eu-west-1`, backend de estado
`madrono-tfm-terraform-state`)** — ambos con `terraform apply -target`
acotado exactamente a las 6 políticas IAM de Glue, sin tocar Kafka ni las
Lambdas de ingesta (mismo criterio que la 051 ante el drift preexistente no
relacionado):

## Arreglo 1: permiso `s3:PutObject` para `_quality_reports/<dataset>/*`

Diagnóstico ya documentado por la 051. Se añadió un statement
`WriteSilverQualityReports<Dataset>` (`s3:PutObject`,
`s3:AbortMultipartUpload`, `s3:ListMultipartUploadParts` sobre
`${bucket_silver}/_quality_reports/<dataset>/*`) a los 6 bloques de
`infra/terraform/glue.tf`, más el prefijo correspondiente en el
`ListLakehouseBucketsFor<Dataset>Prefixes` de cada uno. `terraform plan`
acotado a las 6 `aws_iam_policy.glue_<dataset>_data_access` dio exactamente
6 a cambiar, 0 a añadir/destruir — aplicado con éxito.

## Arreglo 2: permiso `s3:PutObject` para el marcador `<gold_prefix>_$folder$`

**Descubierto en esta tarea**, no documentado por la 051 (ese intento nunca
llegó tan lejos). Al lanzar `aparcamientos-silver-to-gold` tras el arreglo
1, falló con:

```
AccessDenied ... s3:PutObject ... "arn:aws:s3:::madrono-tfm-dev-gold-222234418587/aparcamientos_por_parking_hora_$folder$"
```

Causa confirmada en el log del driver de Glue (`/aws-glue/jobs/logs-v2`,
stream `<job-run-id>-driver`): cuando el `DataFrame` de Gold que se escribe
sale con **cero filas**, ninguna tarea de Spark llega a crear ningún objeto
de datos bajo el prefijo de salida (`needsTaskCommit=false` — no hay nada
que confirmar), así que `FileOutputCommitter.commitJob` cae en
`createSuccessMarkerOrEnsureOutputPathExists`, que llama a
`EmrFileSystem.mkdirs()` y crea explícitamente un objeto marcador de
directorio vacío `<prefijo>_$folder$` (sin barra antes de `_$folder$`) en
la raíz del prefijo. La política IAM `WriteGold<Dataset>...` solo cubre
`<prefijo>/*` (con barra), así que nunca cubre esta clave. Se añadió un
segundo recurso literal `<prefijo>_$folder$` al mismo statement en los 6
bloques de `glue.tf` (misma construcción del committer en los 6 jobs, no
solo el que falló). `terraform plan`/`apply` acotado a las mismas 6
políticas: 6 a cambiar, aplicado con éxito.

## Ejecución real: Bronze → Silver (6/6 con éxito)

Lanzados con `aws glue start-job-run`, cada uno acotado a la última
partición horaria con datos en Bronze en el momento de lanzar (no toda la
partición recursiva del dataset). Resultado — todos `SUCCEEDED`, todos con
el informe de Great Expectations en 100% de expectativas superadas
(`_quality_reports/<dataset>/*.json`, descargado y verificado):

| dataset | `--bronze_path` (hora) | tiempo ejec. | filas Silver (GX `element_count`) | expectativas GX |
|---|---|---|---|---|
| trafico | fecha=2026-08-16/hora=17 | 176 s | 12534 | 11/11 ✅ |
| transporte_publico_emt | fecha=2026-08-16/hora=17 | 168 s | 6 | 5/5 ✅ |
| bicimad | fecha=2026-08-16/hora=17 | 180 s | 2043 | 10/10 ✅ |
| aparcamientos | fecha=2026-08-16/hora=17 | 192 s | 24 | 5/5 ✅ |
| calidad_aire | fecha=2026-08-16/hora=16 | 166 s | 369 | 7/7 ✅ |
| meteorologia | fecha=2026-08-16/hora=16 | 157 s | 261 | 7/7 ✅ |

Observaciones sobre el esquema/reparto de Silver, ninguna es un bug:

- **`trafico`/`bicimad`/`aparcamientos`**: las particiones físicas
  `fecha=/hora=` de Silver (derivadas de `measured_at`, no de
  `ingested_at`) no coinciden con la hora de Bronze usada como entrada —
  `bicimad` en particular reparte sus 2043 filas en **8 fechas distintas**,
  incluida `fecha=1970-01-01/hora=00`. Confirmado leyendo
  `ingesta/capturas/bicimad.py::normalize_record`: `measured_at` es el
  `last_reported` propio de cada estación en el feed GBFS (no el instante
  de captura), que puede estar desactualizado (estaciones fuera de
  servicio) o ser `0`/epoch para estaciones que nunca han reportado. Es el
  comportamiento esperado del feed, no un error de `transform.py`.
- **`transporte_publico_emt`**: solo 6 filas Silver de 3 batches Bronze de
  ~780 bytes cada uno — la captura de este dataset monitoriza un número
  reducido de paradas/líneas (no toda la red EMT), consistente con
  ficheros Bronze de ese tamaño.
- Todas las validaciones de Great Expectations (nulos, rangos de
  plausibilidad, columnas auxiliares `value_over_plausible_max` /
  `value_below_plausible_min` / `free_spaces_over_total_spaces` /
  `bikes_over_capacity` / `docks_over_capacity`) pasaron al 100% en los 6
  datasets — ninguna fila real de este lote violó la puerta de calidad.

## Ejecución real: Silver → Gold (5/6 con éxito, 1 con bug real de código)

| dataset | tiempo ejec. | resultado |
|---|---|---|
| trafico | 61 s | ✅ 2 ficheros parquet, `date=2026-08-16/` |
| transporte_publico_emt | 59 s | ✅ 1 fichero parquet, `date=2026-08-16/` |
| bicimad | 68 s | ✅ 6 ficheros parquet, uno por cada fecha de `measured_at` presente en Silver (`1970-01-01`, `2026-08-06/08/10/13/16`) |
| calidad_aire | 74 s | ✅ 1 fichero parquet, `date=2026-08-16/` |
| meteorologia | 63 s | ✅ 1 fichero parquet, `date=2026-08-16/` |
| **aparcamientos** | 58 s | ⚠️ **`SUCCEEDED` pero 0 filas escritas** — ver bug abajo |

### Bug real de código: `aparcamientos_silver_to_gold` no escribe ninguna fila

El job termina `SUCCEEDED` (sin excepción, una vez arreglado el permiso del
marcador de directorio) pero **no crea ningún fichero de datos** bajo
`gold/aparcamientos_por_parking_hora/` — solo queda el marcador
`aparcamientos_por_parking_hora_$folder$` (0 bytes), confirmando que el
`DataFrame` de Gold salió vacío. Confirmado en dos ejecuciones
independientes (misma `--silver_path` por defecto, sin overrides): las dos
veces 0 filas, así que no es un problema transitorio de consistencia de S3.

Silver de `aparcamientos` tiene 24 filas válidas (100% de expectativas GX
superadas, ver tabla arriba), repartidas en dos particiones reales
`fecha=2026-08-16/hora=14` y `fecha=2026-08-16/hora=15` — **no** hay
ninguna partición `fecha=__sin_medida__` en este lote, así que el filtro
`.where(F.col("fecha") != "__sin_medida__")` de
`procesamiento/silver_gold/aparcamientos/glue_silver_to_gold.py` no
debería eliminar ninguna fila. Aun así, `gold_df` (tras
`groupBy("parking_id", "fecha", "hora").agg(...)`) sale vacío. **No se ha
diagnosticado la causa exacta** — siguiendo la instrucción explícita de la
tarea de no depurar problemas reales de código más allá de un intento
razonable, se deja documentado aquí como bug real para una tarea de
seguimiento, con estos datos de partida:

- Es reproducible (dos ejecuciones, mismo resultado).
- Es el único de los 6 `glue_silver_to_gold.py` que aplica un `.where(...)`
  antes del `groupBy` — los otros 5 leen todo `silver_df` sin filtrar
  (comparar con `procesamiento/silver_gold/trafico/glue_silver_to_gold.py`
  y equivalentes). El filtro por `__sin_medida__` es el mejor candidato a
  revisar primero, aunque la partición no debería existir en este lote
  concreto.
- Bug relacionado, encontrado al intentar diagnosticar el anterior:
  sobrescribir `--silver_path` con un prefijo más específico
  (`.../aparcamientos/fecha=2026-08-16/`, un nivel más profundo que el
  prefijo raíz del dataset) rompe el job con
  `AnalysisException: Column 'fecha' does not exist` — al acotar la
  ruta de lectura hasta dentro de la partición `fecha=`, Spark dejar de
  descubrir `fecha` como columna de partición (solo queda `hora`), y el
  `.where(F.col("fecha") != ...)` referencia una columna que ya no existe.
  Esto también es candidato a la misma tarea de seguimiento: el patrón de
  "acotar `--silver_path`/`--bronze_path` a un prefijo más específico para
  una ejecución manual", documentado como uso previsto en el docstring de
  `glue_bronze_to_silver.py`, no funciona de forma simétrica en
  `aparcamientos_silver_to_gold.py` en cuanto se acota a nivel de fecha.

## Qué no se ha podido verificar en esta sesión

No hay ninguna herramienta de lectura de Parquet disponible en esta EC2
(sin `pyarrow`/`pandas`/`duckdb` instalados, y sin margen de disco para
instalarlos con garantías dado el límite de la máquina — ~1.3 GB libres al
empezar esta tarea). Se intentó `aws s3api select-object-content` (S3
Select, que no requiere ninguna librería local) para comparar a mano el
contenido de un grupo de agregación de Gold contra sus filas de Silver de
origen, pero la cuenta/bucket devolvió `MethodNotAllowed` para
`SelectObjectContent` sobre Parquet. Por eso la verificación de Gold de
esta tarea es **indirecta**: número/tamaño de ficheros parquet reales
escritos por partición, más el número de filas de Silver que alimentó cada
agregación (via los informes de Great Expectations, que sí se pudieron
descargar y parsear como JSON). No se ha comparado a mano el valor exacto
de ninguna fila de Gold contra sus filas de Silver de origen. Queda como
pendiente para una tarea futura con más margen de disco (o ejecutada fuera
de esta EC2) confirmar los valores agregados exactos.

## Costes/tiempos

Ninguna ejecución fue sorprendentemente larga o costosa: Bronze→Silver
entre 157 s y 192 s (todas con `great_expectations` instalándose vía
`--additional-python-modules` en cada arranque, que explica la mayor parte
de ese tiempo frente a los 55-75 s de Silver→Gold, que no instala nada
adicional). Todos los jobs corrieron con la configuración de workers por
defecto de `infra/terraform/variables.tf` (`glue_worker_type`/
`glue_number_of_workers`), sin necesidad de ajustarla.

## Restricciones respetadas

- No se ha creado ningún trigger/schedule para estos jobs de Glue.
- No se ha ejecutado `terraform destroy`.
- No se ha tocado `infra/terraform/lambda.tf` ni ningún recurso de la fase
  de ingesta — los dos `terraform apply` de esta tarea se acotaron con
  `-target` exactamente a las 6 `aws_iam_policy.glue_<dataset>_data_access`
  (mismo criterio que la 051 ante el drift preexistente de Kafka/Lambdas,
  ajeno a esta tarea y no investigado aquí).
- El bug real de `aparcamientos_silver_to_gold` (0 filas) se ha
  documentado, no depurado ni arreglado, siguiendo la instrucción explícita
  de la tarea.
- `backend.hcl` se creó localmente (copia de `backend.hcl.example`) solo
  para poder ejecutar `terraform init`/`plan`/`apply`; no se commitea (ya
  cubierto por `.gitignore`) y se borra al terminar, junto con
  `.terraform/`, `.terraform.lock.hcl` y los ficheros de plan guardados.

## Relevante para tareas futuras

- **Bug de seguimiento prioritario**: `aparcamientos_silver_to_gold.py`
  produce un `DataFrame` de Gold vacío con datos Silver reales y válidos
  (24 filas, 100% GX). Punto de partida para depurarlo: comparar su
  `.where(F.col("fecha") != "__sin_medida__")` contra los otros 5 jobs
  (que no filtran nada antes del `groupBy`), y revisar por qué acotar
  `--silver_path` a un nivel de partición más profundo rompe el
  descubrimiento de la columna `fecha`. Hasta que se arregle, `aparcamientos`
  es el único de los 6 datasets sin ninguna fila real en Gold verificada.
- Los 6 jobs Silver→Gold comparten la misma construcción de committer
  (EMR Optimized Parquet Committer sobre `EmrFileSystem`/S3 nativo), que
  crea un marcador `<prefijo>_$folder$` en la raíz del prefijo de salida
  cada vez que el `DataFrame` a escribir sale vacío. Cualquier dataset
  futuro del patrón que pueda producir agregaciones vacías en alguna
  ejecución (huecos de datos, filtros estrictos) debe incluir este segundo
  recurso en su política IAM desde el principio — el arreglo 2 de esta
  tarea ya lo cubre para los 6 datasets actuales, pero un séptimo dataset
  nuevo necesitaría el mismo patrón de dos recursos (`<prefijo>/*` +
  `<prefijo>_$folder$`) en su statement `WriteGold<Dataset>...`.
- Esta EC2 no tiene ninguna herramienta de lectura de Parquet ni acceso a
  S3 Select sobre Parquet — cualquier tarea futura que necesite comparar
  contenido fila a fila de Silver/Gold reales debe planear ejecutarse desde
  un entorno con `pyarrow`/`duckdb` disponibles (o un Glue Studio Notebook
  real, como ya recomendaban las tareas 046-050 para el smoke-test de
  `ge_suite.py`), no desde esta máquina de desarrollo.
- Con los dos arreglos de infraestructura de esta tarea aplicados, los 6
  datasets ya tienen su Bronze→Silver funcionando de extremo a extremo sin
  ningún bug conocido pendiente; Silver→Gold funciona para 5/6 (todos salvo
  `aparcamientos`). Antes de programar esto en producción (siguiente paso
  natural, fuera de alcance de esta tarea por `force: false` explícito),
  falta como mínimo arreglar el bug de `aparcamientos` de arriba.
