---
id: 51
slug: desplegar-silver-gold-sin-schedule
title: Arreglar los dos bugs de Glue que bloquean Silver/Gold (sin verificación completa)
status: in_progress
force: false
allow_infra_apply: true
branch: task/051-desplegar-silver-gold-sin-schedule
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-16T09:30:00+00:00'
updated_at: '2026-08-16T14:41:39.808857+00:00'
started_at: '2026-08-16T14:41:39.808827+00:00'
submitted_at: null
merged_at: null
---

## Contexto

**Esta tarea ya se ha intentado dos veces y las dos veces terminó sin crear
ningún commit**, pese a que en ambas se ejecutó `terraform apply` real y se
lanzaron Glue jobs reales contra la cuenta de AWS — el trabajo real quedó
completamente indocumentado en el repo las dos veces, y el segundo intento
demuestra que el primero sí llegó a arreglar algo (el error cambió), pero ese
arreglo se perdió al no comitearse nunca.

**Diagnóstico acumulado de los dos intentos anteriores** (verificado
manualmente contra AWS con `aws glue get-job-run`, fuera de la sesión de
`claude`, ya que el runner del agente no conserva la salida completa de un
intento que termina "ok" sin commits):

1. **Primer intento**: los 6 `glue_bronze_to_silver.py` (uno por dataset)
   escriben el informe de Great Expectations con la API RDD antigua —
   `sc.parallelize([json.dumps(quality_report)], numSlices=1).saveAsTextFile(...)`—,
   que dispara el protocolo de commit `mapred` (v1) de Hadoop y busca
   `org.apache.hadoop.mapred.DirectOutputCommitter`, una clase de EMR/
   `hadoop-aws` que no existe en el runtime de Spark de AWS Glue. Falla en
   los 6 datasets por igual.
2. **Segundo intento**: ese error ya no aparece (se arregló, aunque el fix no
   se comiteó), pero surge uno nuevo, también igual en los 6 datasets:

   ```
   ImportError: cannot import name 'DEFAULT_CIPHERS' from 'urllib3.util.ssl_'
   (/home/spark/.local/lib/python3.10/site-packages/urllib3/util/ssl_.py)
   ```

   **Hipótesis de causa** (a confirmar, no verificada por ejecución real):
   `DEFAULT_CIPHERS` se eliminó de `urllib3` en la serie 2.x. El job instala
   `great_expectations==0.18.19` en tiempo de ejecución vía
   `--additional-python-modules` (parámetro nativo de Glue, valor de la
   variable `great_expectations_pip_spec` en
   `infra/terraform/variables.tf`), y ese `pip install` probablemente arrastra
   una versión de `urllib3` >= 2.0 como dependencia transitiva, que rompe la
   importación de `boto3`/`botocore` (que en el runtime base de Glue esperan
   una versión de `urllib3` anterior a la 2.0, la que sí trae
   `DEFAULT_CIPHERS`). Como esta EC2 no tiene `pyspark`/Glue instalado, no se
   ha podido reproducir localmente — confírmalo en el propio job.

## Objetivo

Arreglar ambos bugs y confirmarlo con **un único job de sanidad** (no la
matriz completa de 6 datasets × 2 etapas) — la verificación completa de los 6
datasets es la tarea 052, deliberadamente separada de esta para mantener el
alcance pequeño y evitar un tercer intento sin commit.

## Alcance concreto

1. En los 6 `procesamiento/silver_gold/<dataset>/glue_bronze_to_silver.py`
   (`trafico`, `transporte_publico_emt`, `bicimad`, `aparcamientos`,
   `calidad_aire`, `meteorologia`), sustituye
   `sc.parallelize(...).saveAsTextFile(...)` para escribir el informe de
   Great Expectations por una escritura directa a S3 vía `boto3`
   (`s3_client.put_object(...)`) — un único fichero JSON pequeño no necesita
   la maquinaria distribuida de Spark, y esto evita el problema del
   committer en vez de intentar reconfigurarlo.
2. En `infra/terraform/variables.tf`, ajusta el valor por defecto de
   `great_expectations_pip_spec` para fijar una versión de `urllib3`
   compatible junto a Great Expectations (p.ej.
   `"great_expectations==0.18.19,urllib3<2"` o el pin concreto que
   determines correcto) — investiga primero cuál es la versión de `urllib3`
   que realmente necesita el `boto3`/`botocore` del runtime de Glue antes de
   fijar un número al azar. Es una única variable usada por los 12 jobs
   (`grep -n additional-python-modules infra/terraform/glue.tf`), así que el
   arreglo es centralizado.
3. `terraform plan` (el único cambio esperado: el hash del paquete de
   `procesamiento/` por el punto 1, y `default_arguments` de los 12 jobs de
   Glue por el punto 2 — nada más, ni recursos nuevos ni ningún
   trigger/schedule) y `terraform apply`.
4. Lanza **un único** `aws glue start-job-run` de sanidad —
   `madrono-tfm-dev-trafico-bronze-to-silver` contra el lote más reciente ya
   presente en `s3://madrono-tfm-dev-bronze-222234418587/trafico/...` — y
   espera a que termine. No hace falta lanzar los otros 11 jobs ni la etapa
   Silver→Gold: solo confirmar que este arreglo hace que el job avance más
   allá de los dos errores conocidos.
5. Documenta en `doc/051-desplegar-silver-gold-sin-schedule.md` el
   diagnóstico completo (los dos bugs, cómo se arreglaron) y el resultado del
   job de sanidad — si completó con éxito, genial; si falló con un tercer
   error nuevo, documenta ese error exacto igualmente y no intentes
   depurarlo más allá de un intento razonable (queda para la tarea 052).

## Restricciones

- **NO lances la matriz completa de verificación** (los 6 datasets × Bronze→
  Silver→Gold) — eso es explícitamente la tarea 052. Esta tarea es solo el
  arreglo + un job de sanidad.
- NO crees ningún trigger/schedule para estos jobs de Glue.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni ningún recurso de la fase de
  ingesta.
- **Antes de terminar, confirma que dejas un commit real** (código +
  `infra/terraform/variables.tf` + `doc/051-...md`) aunque el job de sanidad
  siga fallando tras el arreglo — un resultado parcial documentado es mucho
  más útil para la cola de tareas que terminar sin commitear nada, que es
  exactamente lo que falló las dos veces anteriores. Si por cualquier motivo
  decides que no puedes completar ni siquiera esto, comitea de todos modos un
  `doc/051-...md` explicando en qué punto te quedaste y por qué, antes de
  terminar la sesión.

## Criterios de aceptación

- Los dos bugs (`saveAsTextFile`/`DirectOutputCommitter` y
  `urllib3`/`DEFAULT_CIPHERS`) están corregidos y aplicados en AWS real.
- Hay al menos un job de Glue (`trafico-bronze-to-silver`) ejecutado tras el
  arreglo, con su resultado documentado (éxito o el error exacto si aún
  falla).
- `doc/051-desplegar-silver-gold-sin-schedule.md` documenta el diagnóstico
  completo y el resultado.
- Hay un commit real con estos cambios.
