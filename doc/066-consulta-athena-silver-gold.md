# 066 — Capa de consulta SQL sobre Silver/Gold con Amazon Athena

## Objetivo

Silver/Gold (tareas 041-065) ya está en producción continua para los 14 datasets,
con 30 tablas registradas en el catálogo de Glue (`glue.tf`), pero sin ninguna forma
de consultarlas con SQL. Esta tarea añade Amazon Athena (motor de consulta
serverless, pago solo por bytes escaneados, sin clúster que mantener) y verifica con
consultas reales contra datos de producción que el resultado es correcto.

## Qué se ha aplicado en AWS (región `eu-west-1`, cuenta `222234418587`)

Fichero nuevo `infra/terraform/athena.tf` (9 recursos), aplicado con
`terraform apply` **acotado con `-target`** a exactamente estos 9 recursos (mismo
patrón documentado en `doc/065-aplicar-scheduling-silver-gold.md` para no arrastrar
la deriva no relacionada de Kafka/`procesamiento/` a este apply — confirmado con
`terraform plan -target=...`: "Plan: 9 to add, 0 to change, 0 to destroy", sin ningún
recurso ajeno):

| Recurso | Nombre real en AWS |
|---|---|
| `aws_athena_workgroup.silver_gold` | `madrono-tfm-dev-silver-gold` |
| `aws_s3_bucket.athena_results` | `madrono-tfm-dev-athena-results-222234418587` |
| `aws_s3_bucket_server_side_encryption_configuration.athena_results` | (sobre el bucket anterior, AES256) |
| `aws_s3_bucket_public_access_block.athena_results` | (sobre el bucket anterior, bloqueo total) |
| `aws_s3_bucket_lifecycle_configuration.athena_results` | expira objetos a los 7 días |
| `aws_s3_bucket_policy.athena_results` | deniega tráfico sin TLS |
| `aws_iam_role.athena_query` | `madrono-tfm-dev-athena-query-role` |
| `aws_iam_policy.athena_query` | `madrono-tfm-dev-athena-query` |
| `aws_iam_role_policy_attachment.athena_query` | adjunta la policy anterior al rol |

Confirmado con `aws athena get-work-group --work-group madrono-tfm-dev-silver-gold`
(región `eu-west-1` — el CLI de esta EC2 no tiene región por defecto configurada,
hace falta `--region eu-west-1`/`AWS_DEFAULT_REGION` explícito o falla con
`WorkGroup is not found` contra la región por defecto del SDK):

```json
{
  "ResultConfiguration": {
    "OutputLocation": "s3://madrono-tfm-dev-athena-results-222234418587/results/",
    "EncryptionConfiguration": { "EncryptionOption": "SSE_S3" }
  },
  "EnforceWorkGroupConfiguration": true,
  "PublishCloudWatchMetricsEnabled": true,
  "BytesScannedCutoffPerQuery": 1073741824
}
```

## Decisiones de diseño

- **Bucket de resultados: nuevo (`aws_s3_bucket.athena_results`), no un prefijo de
  `aws_s3_bucket.build_artifacts`.** Mismo motivo que ya documentó `main.tf` para
  "un bucket por capa" del lakehouse: política IAM de mínimo privilegio simple (el
  rol de consulta referencia el ARN del bucket completo, sin depender de acertar un
  `Condition` de prefijo dentro de un bucket que además contiene artefactos de
  CI/CD sin relación con resultados de consulta de datos de producción). Coste de
  un bucket vacío adicional: cero. Lifecycle de 7 días (los resultados son
  100% reproducibles, no hace falta conservarlos).
- **Rol IAM dedicado (`aws_iam_role.athena_query`), no reutilizar el rol de
  Terraform.** El rol que ejecuta `terraform apply` en esta EC2
  (`madrono-terraform-deployerEC2`) tiene permisos amplios para poder desplegar
  cualquier infraestructura del proyecto; el consumidor real de esta capa de
  consulta (un futuro dashboard BI/QuickSight, o un analista humano) no debería
  heredar esos permisos de despliegue. El rol nuevo solo tiene: lectura de
  Silver/Gold (S3), lectura del catálogo de Glue, `athena:*Query*` acotado al
  propio workgroup, y escritura acotada al bucket de resultados — mismo criterio
  de mínimo privilegio ya aplicado al rol de ingesta (`aws_iam_role.ingestion`)
  frente al rol de Terraform. Su política de confianza (`assume_role_policy`)
  confía por defecto en la cuenta AWS del proyecto (root) más una lista
  parametrizable de service principals (`var.athena_query_trusted_services`,
  vacía por defecto) — no existe todavía un consumidor concreto, así que se deja
  extensible sin tener que volver a tocar `athena.tf` cuando se elija uno (mismo
  patrón que `ingestion_trusted_services`/`ingestion_trusted_arns` en `main.tf`).
  **No se ha usado este rol para ejecutar las consultas de verificación de esta
  tarea** (no se ha hecho `sts:assume-role` sobre él): las 5+ consultas se han
  lanzado con las credenciales ya disponibles en esta EC2
  (`madrono-terraform-deployerEC2`, que al tener permisos amplios también puede
  usar Athena). El rol de mínimo privilegio queda desplegado y listo para un
  consumidor real futuro, pero no se ha verificado con una asunción de rol real
  en esta sesión.
- **`bytes_scanned_cutoff_per_query = 1 GiB`** (`var.athena_bytes_scanned_cutoff`):
  medido el volumen real antes de fijar el valor — Silver completo son 391 769 871
  bytes (~392 MB, 8494 objetos) y Gold 5 858 698 bytes (~5.8 MB, 589 objetos) a
  fecha de esta tarea (`aws s3 ls --recursive --summarize`). 1 GiB da margen de
  sobra para cualquier consulta legítima sobre un único dataset y corta en seco un
  `JOIN` sin condición o una consulta que escanee muchas más particiones de las
  esperadas.

## Hallazgo confirmado con una consulta real: el catálogo de Glue NO registra las particiones automáticamente

La tarea pedía explícitamente no dar esto por hecho y confirmarlo con una consulta
real. Se ha confirmado que **hace falta**: los 14 datasets escriben a Silver/Gold
con `DataFrame.write.mode("append").partitionBy(...).parquet(path)` (Spark plano,
ver p.ej. `procesamiento/silver_gold/trafico/glue_silver_to_gold.py`), no a través
de un sink del catálogo de Glue (`glueContext.write_dynamic_frame.from_catalog`
con `updateBehavior=UPDATE_IN_DATABASE`), así que escribir un fichero Parquet bajo
una partición nueva en S3 **no** añade esa partición al catálogo.

Secuencia real observada sobre `silver.trafico`:

1. `SELECT COUNT(*) FROM trafico` (contexto `madrono-tfm_dev_silver`) → **`0`**,
   `DataScannedInBytes = 0`, pese a que el bucket Silver tiene miles de objetos
   Parquet reales bajo ese prefijo.
2. `SHOW PARTITIONS trafico` → 0 filas.
3. `MSCK REPAIR TABLE trafico` → añade decenas de particiones
   (`fecha=.../hora=...`) reales encontradas en S3 pero ausentes del metastore.
4. Repetir `SELECT COUNT(*) FROM trafico` tras el repair → **`6186491`** filas
   reales.

Repetido y confirmado en 6 tablas en total (las que hacían falta para las 5+
consultas de verificación, no las 30): `silver.trafico`,
`gold.trafico_por_punto_hora`, `gold.calidad_aire_por_estacion_contaminante_hora`,
`silver.ruido`, `silver.cartelera_cines_estrenos` (0 particiones encontradas — Silver
vacío, ver tarea 063, `MSCK REPAIR` no da ningún error, simplemente no añade nada),
`silver.afluencia_lugares` (mismo caso, Silver vacío).

**No corregido en esta tarea** (fuera del alcance descrito por el prompt, que pide
desplegar Athena y verificar con consultas, no rediseñar la escritura de
Silver/Gold): queda documentado como hallazgo real para una tarea de seguimiento.
Nombres reales de las bases de datos del catálogo (no coinciden literalmente con
"silver"/"gold" por el prefijo del proyecto):
`madrono-tfm_dev_silver` / `madrono-tfm_dev_gold`.

**Recomendación para la tarea de seguimiento** (dos alternativas, no aplicadas
aquí): (a) usar **Athena Partition Projection**
(`projection.enabled = "true"` + `projection.<key>.type = "date"`/`"injected"` en
los `parameters` de cada `aws_glue_catalog_table`) — encaja bien porque todas las
particiones son `fecha`/`hora` o `date` con rangos predecibles, y elimina la
necesidad de `MSCK REPAIR TABLE` por completo (Athena calcula las rutas S3
posibles en tiempo de consulta, sin consultar el metastore); o (b) añadir un paso
`MSCK REPAIR TABLE`/`glue:BatchCreatePartition` al final de cada job Silver→Gold
(o a un trigger encadenado en `glue_scheduling.tf`). La opción (a) es más barata
(sin coste de metadata) y no depende de que se ejecute nada extra tras cada job —
recomendada como primera opción a evaluar.

## Las 5 consultas de verificación ejecutadas (`aws athena start-query-execution` + `get-query-execution`/`get-query-results`, workgroup `madrono-tfm-dev-silver-gold`)

Todas las consultas se han lanzado con el workgroup real y sus resultados son de
producción (no simulados). `DataScannedInBytes` real de cada una:

### 1. Consulta simple sobre una tabla Silver

```sql
SELECT COUNT(*) AS row_count FROM trafico   -- contexto: madrono-tfm_dev_silver
```

- Resultado: **6 186 491** filas.
- `DataScannedInBytes`: **0** (Athena resuelve `COUNT(*)` sobre Parquet leyendo
  solo las estadísticas de los row groups, sin escanear las columnas — no es un
  error de medición).
- Requirió `MSCK REPAIR TABLE trafico` primero (ver hallazgo arriba); sin repair,
  la misma consulta devolvía `0` filas sin ningún error.

### 2. Agregación sobre una tabla Gold — intensidad media de tráfico por hora

```sql
SELECT hour, AVG(avg_intensity_vph) AS avg_intensity_vph, COUNT(*) AS n_points
FROM trafico_por_punto_hora                 -- contexto: madrono-tfm_dev_gold
WHERE date = '2026-08-20' GROUP BY hour ORDER BY hour
```

- Con `date = '2026-08-20'` (el día real de esta sesión, tal como pedía el
  enunciado): **0 filas**. `MSCK REPAIR TABLE trafico_por_punto_hora` solo
  encontró **una** partición real en S3: `date=2026-08-16` — Gold de `trafico`
  no se ha vuelto a agregar desde esa fecha en esta cuenta (coherente con el
  hallazgo de la tarea 065: los triggers `CONDITIONAL` de Silver→Gold no se
  observaron disparar automáticamente en su ventana de verificación). Se
  documenta el resultado real (0 filas), no el esperado.
- Repetida con `date = '2026-08-16'` (la única partición real disponible) para
  confirmar que la agregación en sí funciona: **24 filas** (una por hora),
  `DataScannedInBytes = 11 036`. Ejemplo, hora 14: `avg_intensity_vph =
  212.02130205840115` sobre 4178 puntos de medida.

### 3. `JOIN` entre dos tablas Gold por proximidad temporal — tráfico y calidad del aire de la misma hora

```sql
SELECT t.date, t.hour,
       COUNT(DISTINCT t.point_id) AS n_traffic_points,
       AVG(t.avg_intensity_vph)   AS avg_intensity_vph,
       COUNT(DISTINCT c.station_id) AS n_air_stations,
       AVG(c.avg_value)           AS avg_pollutant_value
FROM trafico_por_punto_hora t                              -- contexto: madrono-tfm_dev_gold
JOIN calidad_aire_por_estacion_contaminante_hora c
  ON t.date = c.date AND t.hour = c.hour
WHERE t.date = '2026-08-16'
GROUP BY t.date, t.hour ORDER BY t.hour
```

- Resultado real (2 filas, horas 14-15, único rango con datos de tráfico Gold
  disponible): hora 14 → 4178 puntos de tráfico (212.02 veh/h media), 23
  estaciones de calidad del aire (20.30 media del valor de contaminante); hora
  15 → 4178 puntos (212.21 veh/h), 23 estaciones (20.56).
- `DataScannedInBytes`: **60 578**.
- Confirma que Athena puede unir dos datasets Gold con un `JOIN` SQL normal
  (sin necesidad de ningún motor adicional) — el cruce espacial real es el
  grafo Neo4j (fuera de esta tarea).

### 4. Dataset del grupo "diario" — `ruido`

```sql
SELECT station_id, period, fecha, AVG(laeq_db) AS avg_laeq_db, COUNT(*) AS n_readings
FROM ruido                                  -- contexto: madrono-tfm_dev_silver
WHERE fecha = '2026-08-17'
GROUP BY station_id, period, fecha ORDER BY station_id, period LIMIT 10
```

- Resultado real (10 filas): p.ej. `RF-01`/`D`/`2026-08-17` → `avg_laeq_db =
  63.0` (1 lectura); `RF-01`/`E`/`2026-08-17` → `62.1`; `RF-01`/`N`/`2026-08-17`
  → `59.2`.
- `DataScannedInBytes`: **943**.

### 5. Dataset con Silver vacío — `cartelera_cines_estrenos`

```sql
SELECT COUNT(*) AS row_count FROM cartelera_cines_estrenos  -- contexto: madrono-tfm_dev_silver
```

- `MSCK REPAIR TABLE cartelera_cines_estrenos` → 0 filas devueltas (0
  particiones encontradas en S3, coherente con la tarea 063: este dataset sigue
  con Silver vacío), **sin ningún error**.
- `SELECT COUNT(*)` → **0** filas, `DataScannedInBytes = 0`, consulta
  `SUCCEEDED` sin excepción.
- Repetido también sobre `afluencia_lugares` (el otro dataset con Silver vacío,
  tarea 060/063): mismo resultado, `0` filas, sin error.
- Confirma que Athena maneja bien una tabla Hive-partitioned sin ninguna
  partición registrada/con datos: a diferencia del job de Glue Silver→Gold de
  este mismo dataset (`spark.read.parquet` sin esquema explícito, que **sí**
  falla con `AnalysisException` sobre un Silver vacío, ver tarea 063), Athena
  simplemente devuelve un resultado vacío.

## Coste total real de esta verificación

Suma de `DataScannedInBytes` de las 5 consultas con datos (excluyendo las
`MSCK REPAIR TABLE`, operaciones de metadata sin coste de escaneo, y las
repeticiones con `date`/`fecha` sin resultados): `0 + 11036 + 60578 + 943 + 0 =
72 557` bytes (~0.07 MB). A $5/TB escaneado (precio de Athena en `eu-west-1`), el
coste de estas 5 consultas es, en la práctica, cero (muy por debajo del redondeo a
10 MB mínimo por consulta que aplica Athena en la facturación real).

## Restricciones respetadas

- `terraform apply` se ha ejecutado **acotado con `-target`** a los 9 recursos de
  `athena.tf` únicamente — confirmado con `terraform plan -target=...` antes de
  aplicar: "Plan: 9 to add, 0 to change, 0 to destroy", sin ningún recurso de
  `lambda.tf`/`glue.tf`/`kafka.tf` de por medio.
- No se ha ejecutado `terraform destroy`.
- No se han tocado `infra/terraform/lambda.tf` ni `infra/terraform/glue.tf` — el
  único fichero nuevo es `athena.tf`; los únicos ficheros existentes modificados
  son `variables.tf` (2 variables nuevas) y `outputs.tf` (3 outputs nuevos), ambos
  fuera de la lista de ficheros prohibidos.
- No se ha tocado la deriva del zip de `procesamiento/` documentada en la tarea
  065.
- Los `MSCK REPAIR TABLE` ejecutados durante la verificación son operaciones de
  metadata del catálogo de Glue (registran particiones ya existentes en S3, no
  crean ni modifican ningún dato) — necesarios para poder confirmar con una
  consulta real si el catálogo descubre particiones automáticamente, tal como
  pedía explícitamente el enunciado ("confírmalo con una consulta real, no lo des
  por hecho"). Solo se han repair-eado las 6 tablas necesarias para las 5+
  consultas de esta tarea, no las 30 tablas del catálogo.
- `backend.hcl` (copia local de `backend.hcl.example`) y los artefactos de
  `terraform init`/`plan` (`.terraform/`, `.terraform.lock.hcl`, `athena.tfplan`)
  se eliminan al terminar la sesión — no se commitea nada de esto.

## Relevante para tareas futuras

- **El catálogo de Glue no descubre particiones nuevas automáticamente para
  ninguno de los 14 datasets** (todos escriben con `DataFrame.write...parquet`
  plano, no con un sink de catálogo) — confirmado con una consulta real en esta
  tarea, no asumido. Cualquier tabla no repareada devuelve `0` filas sin ningún
  error (no falla, simplemente no encuentra datos), lo cual es fácil de
  malinterpretar como "el dataset está vacío" cuando en realidad el problema es
  que faltan particiones en el metastore. Antes de fiarte de que una consulta
  Athena sobre Silver/Gold devuelve `0` filas porque el dataset está realmente
  vacío, comprueba primero `SHOW PARTITIONS <tabla>` o ejecuta
  `MSCK REPAIR TABLE <tabla>`.
- Recomendación concreta para la tarea de seguimiento que resuelva esto: Athena
  Partition Projection (declarar `projection.enabled`/`projection.<key>.type` en
  los `parameters` de cada `aws_glue_catalog_table` de `glue.tf`) es probablemente
  mejor que automatizar `MSCK REPAIR TABLE` tras cada job, porque no depende de
  que se ejecute ningún paso adicional ni tiene coste de metadata — Athena
  calcula las rutas S3 válidas en tiempo de consulta a partir del rango de
  fechas declarado.
- Gold de `trafico` solo tiene una partición real (`date=2026-08-16`) a fecha de
  esta sesión (2026-08-20) — consistente con el hallazgo ya documentado en la
  tarea 065 (el trigger `CONDITIONAL` de Silver→Gold no se observó disparar
  automáticamente en su ventana de verificación). Si una tarea futura relanza
  Silver→Gold de `trafico` a mano o confirma que el scheduling ya funciona,
  debería volver a aparecer una partición Gold más reciente y las consultas de
  esta tarea que hoy devuelven 0 filas para `date = CURRENT_DATE` empezarían a
  devolver datos.
- El CLI de AWS en esta EC2 no tiene región por defecto configurada
  (`aws configure get region` no devuelve nada, `AWS_DEFAULT_REGION` vacío) —
  cualquier llamada a un servicio no genérico (Athena, Glue) necesita
  `--region eu-west-1`/`AWS_DEFAULT_REGION=eu-west-1` explícito, o falla de forma
  confusa (`WorkGroup is not found` en vez de un error de región). Las llamadas a
  S3 sí funcionan sin región explícita porque el SDK resuelve el bucket
  automáticamente.
