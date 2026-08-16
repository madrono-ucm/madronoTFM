# 051 — Arreglar los dos bugs de Glue que bloquean Silver/Gold (sin verificación completa)

## Contexto: dos intentos previos sin commit

Esta tarea ya se había intentado dos veces. Las dos veces se ejecutó
`terraform apply` real y se lanzaron Glue jobs reales contra la cuenta de
AWS, pero **ningún intento terminó con un commit** — todo el trabajo real
quedó indocumentado en el repo. El diagnóstico acumulado (verificado
manualmente contra AWS fuera de sesión) apuntaba a dos bugs, en los 6
datasets del patrón (`trafico`, `transporte_publico_emt`, `bicimad`,
`aparcamientos`, `calidad_aire`, `meteorologia`) por igual:

1. `sc.parallelize([...], numSlices=1).saveAsTextFile(...)` para escribir el
   informe de Great Expectations dispara el protocolo de commit `mapred`
   (v1) de Hadoop, que busca
   `org.apache.hadoop.mapred.DirectOutputCommitter` — una clase de EMR/
   `hadoop-aws` ausente en el runtime de Spark de AWS Glue.
2. Tras arreglar (1), un segundo error, también en los 6 datasets:
   `ImportError: cannot import name 'DEFAULT_CIPHERS' from 'urllib3.util.ssl_'`.

Esta tarea repite el diagnóstico desde cero (sin fiarse del todo del
diagnóstico heredado, ya que no había ningún commit que lo respaldara),
arregla ambos bugs, y **confirma el arreglo con un job de Glue real**
(sanidad de `trafico`, no la matriz completa de 6×2 — eso es la tarea 052).

## Bug 1: `saveAsTextFile` → escritura directa a S3 vía `boto3`

**Causa confirmada**: el runtime de AWS Glue 4.0 no incluye
`hadoop-aws`/EMRFS con soporte para el "output committer" `mapred` v1
(`org.apache.hadoop.mapred.DirectOutputCommitter`) que
`RDD.saveAsTextFile` intenta usar por defecto para escribir un
`TextOutputFormat` a S3 — esa clase es específica de EMR y no está en el
classpath de Glue.

**Arreglo**: en los 6 `glue_bronze_to_silver.py`, se sustituyó

```python
sc.parallelize([json.dumps(quality_report, ensure_ascii=False)], numSlices=1).saveAsTextFile(
    report_key
)
```

por una función `_write_quality_report(report_uri, quality_report)` que
parsea el URI `s3://bucket/key` y usa `boto3.client("s3").put_object(...)`
directamente — un único JSON pequeño (el informe de calidad de una
ejecución) no necesita en absoluto la maquinaria distribuida de Spark, y
esto evita el problema del committer en vez de intentar reconfigurarlo
(que habría exigido tocar `spark.hadoop.mapred.output.committer.class`,
ya fijado a nivel de job por Glue —
`-Dspark.hadoop.mapred.output.committer.class=org.apache.hadoop.mapred.DirectOutputCommitter`,
visible en los logs del job real, ver más abajo). `import boto3` se añadió
a los 6 ficheros (ya estaba disponible en el runtime de Glue, no requiere
`--additional-python-modules`).

## Bug 2: `urllib3`/`DEFAULT_CIPHERS` → pin `urllib3<2` junto a Great Expectations

**Causa confirmada** (la hipótesis del segundo intento era correcta): el
runtime base de Glue 4.0 trae preinstalado un `boto3`/`botocore` cuyo
`botocore/httpsession.py` importa `DEFAULT_CIPHERS` de
`urllib3.util.ssl_` — símbolo eliminado en la serie 2.x de `urllib3`. El
job instala `great_expectations==0.18.19` en tiempo de ejecución vía
`--additional-python-modules` (un solo `pip install` resuelto por Glue), y
esa instalación arrastra `urllib3>=2` como dependencia transitiva (a
través de `requests`), pisando la versión 1.26.x que el
`boto3`/`botocore` ya instalado en el runtime necesita. Cualquier código
del job que use `boto3` después de esa instalación —incluida la propia
escritura del informe de calidad del arreglo del bug 1— rompe con
`ImportError: cannot import name 'DEFAULT_CIPHERS'`.

**Arreglo**: en `infra/terraform/variables.tf`, el valor por defecto de
`great_expectations_pip_spec` pasó de

```
"great_expectations==0.18.19"
```

a

```
"great_expectations==0.18.19,urllib3<2"
```

`--additional-python-modules` acepta una lista separada por comas resuelta
en una única invocación de `pip install`, así que el resolutor de
dependencias instala ambos paquetes de forma consistente en un solo paso,
en vez de que `great_expectations` se instale primero y sobrescriba
`urllib3` después. Es una única variable, usada por los 6 jobs
Bronze→Silver (los únicos que instalan Great Expectations vía
`--additional-python-modules`; los 6 Silver→Gold no la usan — confirmado
con `grep -n additional-python-modules infra/terraform/glue.tf`, 6
coincidencias, no 12), así que el arreglo es centralizado.

## `terraform apply`: aplicado, con `-target` para evitar arrastrar drift no relacionado

Al ejecutar `terraform plan` sin acotar, el plan incluía **12 recursos a
crear, 21 a cambiar, 7 a destruir** — muy por encima de lo esperado (según
el enunciado, "nada más, ni recursos nuevos ni ningún trigger/schedule").
La causa: el estado remoto real tiene drift respecto a los `.tf` del
repo, ajeno a esta tarea:

- Toda la infraestructura de Kafka (`aws_instance.kafka`,
  `aws_iam_role.kafka`, `aws_security_group.kafka`, etc., de la tarea 042,
  que su propio doc documenta explícitamente como "solo código, sin
  `terraform apply`") aparecía como **a crear**.
- Los 14 `aws_lambda_function.producer[...]` y
  `aws_iam_policy.scheduler_invoke_lambda` aparecían **a actualizar en
  local** (drift preexistente, no investigado en esta tarea — no es su
  alcance).

Aplicar ese plan sin acotar habría desplegado un EC2 de Kafka real y
tocado las Lambdas de ingesta — ambos explícitamente fuera de alcance
("NO toques... ningún recurso de la fase de ingesta", "NO crees ningún
trigger/schedule"). Se optó por **`terraform apply` con `-target`**,
acotado exactamente a los 13 recursos que sí correspondían a los dos
arreglos:

```
aws_glue_job.{trafico,transporte_publico_emt,bicimad,aparcamientos,calidad_aire,meteorologia}_bronze_to_silver
aws_s3_object.glue_script_{bronze_to_silver (trafico),transporte_publico_emt_bronze_to_silver,bicimad_bronze_to_silver,aparcamientos_bronze_to_silver,calidad_aire_bronze_to_silver,meteorologia_bronze_to_silver}
aws_s3_object.procesamiento_source
```

El plan acotado resultante fue exactamente el esperado: **7 a añadir
(reemplazo por hash de los 6 scripts Bronze→Silver + el zip compartido de
`procesamiento/`), 6 a cambiar (los 6 `aws_glue_job` Bronze→Silver,
únicamente `default_arguments["--additional-python-modules"]` y las rutas
`--extra-py-files`/`script_location` con el nuevo hash), 7 a destruir**
(las versiones anteriores de esos mismos 7 objetos S3, reemplazadas por
cambio de key/hash). **Aplicado con éxito** contra la cuenta real
(`222234418587`, región `eu-west-1`, bucket de estado
`madrono-tfm-terraform-state`). No se tocó ningún otro recurso: ni Kafka,
ni las Lambdas de ingesta, ni ningún trigger/schedule.

Recursos AWS reales modificados por este `apply`:

- `aws_glue_job.trafico_bronze_to_silver`,
  `aws_glue_job.transporte_publico_emt_bronze_to_silver`,
  `aws_glue_job.bicimad_bronze_to_silver`,
  `aws_glue_job.aparcamientos_bronze_to_silver`,
  `aws_glue_job.calidad_aire_bronze_to_silver`,
  `aws_glue_job.meteorologia_bronze_to_silver` — nombres reales
  `madrono-tfm-dev-<dataset>-bronze-to-silver`, `--additional-python-modules`
  actualizado a `great_expectations==0.18.19,urllib3<2`.
- `aws_s3_object.glue_script_*` (6 objetos, bucket
  `madrono-tfm-dev-build-artifacts-222234418587`, prefijo `glue-scripts/`) —
  reemplazados con el código corregido, nuevo hash en la key.
- `aws_s3_object.procesamiento_source` (mismo bucket, prefijo `glue-libs/`,
  key `procesamiento-e6eed0971ba6bf1ee7898e319077387b.zip`) — el paquete
  compartido de `procesamiento/`, reempaquetado con el código corregido.

## Job de sanidad: `madrono-tfm-dev-trafico-bronze-to-silver`

Lanzado con `aws glue start-job-run`, sobreescribiendo `--bronze_path` a un
único lote reciente (no la partición recursiva completa de `trafico/`, para
mantener la ejecución rápida y acotada):

```
--bronze_path s3://madrono-tfm-dev-bronze-222234418587/trafico/fecha=2026-08-16/hora=16/
```

`JobRunId`: `jr_c33e9fcfa7ac5bd05a558d8f65d1ac44f90042b9382afb63fa85a45917df9a76`.
Resultado: **`FAILED`**, tras 161 s de ejecución (`ExecutionTime`), con un
**tercer error, nuevo y distinto de los dos anteriores**:

```
ClientError: An error occurred (AccessDenied) when calling the PutObject
operation: User: arn:aws:sts::222234418587:assumed-role/madrono-tfm-dev-trafico-glue-role/GlueJobRunnerSession
is not authorized to perform: s3:PutObject on resource:
"arn:aws:s3:::madrono-tfm-dev-silver-222234418587/_quality_reports/trafico/trafico_20260816T164818.json"
because no identity-based policy allows the s3:PutObject action
```

**Los dos bugs objetivo de esta tarea están confirmados arreglados**: el
job llegó mucho más lejos que en los dos intentos previos —leyó Bronze,
ejecutó `bronze_to_silver` (transformación + puerta de calidad), corrió la
validación de Great Expectations— y solo falló al intentar escribir el
informe de calidad, en la nueva llamada `boto3.put_object` (bug 1
arreglado: ya no hay ningún rastro de `DirectOutputCommitter` en los logs;
bug 2 arreglado: `boto3`/`botocore` se importó y usó sin ningún
`ImportError` de `urllib3`).

**Causa del tercer error (diagnóstico, no arreglado en esta tarea)**: la
política IAM `glue_trafico_data_access`
(`infra/terraform/glue.tf`, statement `ReadWriteSilverTrafico`) solo
concede `s3:PutObject`/`s3:GetObject` sobre
`${bucket_silver}/trafico/*` — el prefijo real donde `_write_quality_report`
escribe (`--quality_report_path` =
`s3://madrono-tfm-dev-silver-222234418587/_quality_reports/trafico/`) nunca
estuvo cubierto por ningún statement de la política. Es un hueco de diseño
preexistente (la escritura del informe con `saveAsTextFile` habría tenido
el mismo problema de permisos si hubiera llegado a ejecutarse — nunca llegó
tan lejos en los dos intentos previos), no algo introducido por el arreglo
de esta tarea. El mismo hueco existe, por construcción idéntica de la
política, en los otros 5 datasets (`ReadWriteSilver<Dataset>` en cada
bloque de `glue.tf` solo cubre `silver/<dataset>/*`, no
`silver/_quality_reports/<dataset>/*`).

Siguiendo la instrucción explícita de la tarea ("no intentes depurarlo más
allá de un intento razonable — queda para la tarea 052"), **no se ha
tocado la política IAM** en esta tarea. Queda documentado aquí como punto
de partida para la 052: añadir un statement `s3:PutObject` (+
`s3:AbortMultipartUpload`/`s3:ListMultipartUploadParts`, mismo patrón que
`ReadWriteSilver<Dataset>`) sobre
`${bucket_silver}/_quality_reports/<dataset>/*` en los 6 roles Glue del
patrón, antes de poder completar ni siquiera la verificación de `trafico`
solo, y mucho menos la matriz completa de 6 datasets.

## Alcance respetado

- Solo se tocaron los 6 `glue_bronze_to_silver.py` (bug 1) y
  `infra/terraform/variables.tf` (bug 2) — ningún otro fichero de
  `procesamiento/silver_gold/`.
- No se creó ningún trigger/schedule.
- No se ejecutó `terraform destroy`.
- No se tocó `infra/terraform/lambda.tf` ni ningún recurso de la fase de
  ingesta (el drift detectado en las Lambdas y en Kafka se dejó
  intencionadamente fuera del `apply`, vía `-target`, precisamente para no
  tocarlo).
- No se lanzó la matriz completa de 6 datasets × Bronze→Silver→Gold —
  solo el job de sanidad de `trafico` Bronze→Silver, como pedía el
  enunciado.
- `backend.hcl` se creó localmente (copia de `backend.hcl.example`) solo
  para poder ejecutar `terraform init`/`plan`/`apply` en esta sesión; no se
  commitea (ya cubierto por `.gitignore`) y se borró al terminar, junto con
  `.terraform/`, `.terraform.lock.hcl` y los ficheros de plan guardados
  (`tfplan051`, `tfplan051scoped`).

## Relevante para tareas futuras

- **Tarea 052 (verificación completa) necesita primero un tercer arreglo**:
  añadir permisos `s3:PutObject` sobre `_quality_reports/<dataset>/*` en
  los 6 roles IAM de Glue de `infra/terraform/glue.tf` (ver diagnóstico
  arriba). Sin esto, ningún job Bronze→Silver del patrón puede completar
  con éxito — todos escriben el informe de calidad al mismo prefijo
  `_quality_reports/<dataset>/` con el mismo hueco de permisos.
- Al planificar el `apply` de la 052 (o cualquier tarea futura que toque
  `infra/terraform/glue.tf`), **ejecutar primero un `terraform plan` sin
  acotar y revisar el recuento de recursos antes de aplicar**: el estado
  remoto real tiene drift no relacionado con Glue (Kafka de la tarea 042
  nunca aplicado, y las 14 Lambdas de ingesta con cambios en local no
  investigados) que un `apply` sin `-target` aplicaría de golpe. Este
  drift ya existía antes de esta tarea — no se ha investigado su causa ni
  se ha intentado resolverlo aquí (fuera de alcance), pero cualquier tarea
  futura que haga `terraform apply` en este proyecto debería tenerlo en
  cuenta y decidir explícitamente si acotar con `-target` o resolver el
  drift primero.
- El patrón de "escribir directamente a S3 vía `boto3` en vez de
  `sc.parallelize(...).saveAsTextFile(...)`" para ficheros pequeños y
  únicos (no datasets particionados) es el criterio a replicar en
  cualquier future job de Glue de este proyecto que necesite escribir un
  artefacto de tamaño acotado (un informe, un manifiesto, etc.) — el
  commit protocol distribuido de Spark solo tiene sentido para escrituras
  particionadas grandes (como el propio `silver_partitioned.write.parquet`
  de estos mismos jobs, que sí sigue usando la vía normal de Spark y no se
  ha tocado).
