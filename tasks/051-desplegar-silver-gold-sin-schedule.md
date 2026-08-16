---
id: 51
slug: desplegar-silver-gold-sin-schedule
title: Desplegar Glue Silver/Gold en AWS (sin schedule) y verificar con una carga
  puntual
status: failed
force: false
allow_infra_apply: true
branch: task/051-desplegar-silver-gold-sin-schedule
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: claude finalizó sin crear ningún commit
created_at: '2026-08-16T09:30:00+00:00'
updated_at: '2026-08-16T14:18:25.479195+00:00'
started_at: '2026-08-16T14:10:56.636764+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Las tareas 041 y 046-050 escribieron (sin aplicar) el código y el Terraform de
Glue para 6 datasets: `trafico` (piloto) y `transporte_publico_emt`,
`bicimad`, `aparcamientos`, `calidad_aire`, `meteorologia`.

**Un primer intento de esta tarea ya aplicó la infraestructura y lanzó las
cargas** (branch `task/051-desplegar-silver-gold-sin-schedule`, ya borrada) —
pero terminó sin crear ningún commit ni PR, así que el resultado quedó
completamente indocumentado en el repo pese a que sí tuvo efectos reales en
AWS. Verificado manualmente fuera de esta tarea (fuera de la sesión de
`claude`, con `aws glue get-jobs`/`get-databases`/`iam list-roles`):

- **`terraform apply` de `glue.tf` SÍ se ejecutó y sigue aplicado**: existen
  ya en `eu-west-1` los 12 jobs de Glue (2 por dataset × 6), las 2 bases del
  catálogo (`madrono-tfm_dev_silver`, `madrono-tfm_dev_gold`) y los 6 roles
  IAM. **No hace falta volver a aplicar nada nuevo** — un `terraform apply`
  de esta tarea será casi con toda seguridad un no-op o solo actualizará el
  hash del paquete de `procesamiento/` si cambias código (ver diagnóstico
  abajo). Confirma con `terraform plan` antes de nada, pero no esperes tener
  que crear infraestructura desde cero.
- **Las 6 ejecuciones de Bronze→Silver que se lanzaron fallaron, todas por
  la misma causa** (`aws glue get-job-run` sobre cada job, `ErrorMessage`):

  ```
  An error occurred while calling o879.saveAsTextFile.
  java.lang.RuntimeException: java.lang.ClassNotFoundException:
  Class org.apache.hadoop.mapred.DirectOutputCommitter not found
  ```

  **Diagnóstico (ya hecho, no hace falta repetirlo)**: los 6
  `glue_bronze_to_silver.py` (uno por dataset, mismo patrón copiado del
  piloto de tráfico) escriben el informe de Great Expectations con la API
  RDD antigua —
  `sc.parallelize([json.dumps(quality_report)], numSlices=1).saveAsTextFile(...)`—,
  que dispara el protocolo de commit `mapred` (v1) de Hadoop. Ese protocolo
  espera poder resolver `org.apache.hadoop.mapred.DirectOutputCommitter`,
  una clase específica de EMR/`hadoop-aws` que **no está en el classpath del
  runtime de Spark de AWS Glue** — por eso falla en los 6 datasets por igual,
  no es un problema de datos ni de permisos.
  Ninguna de las 6 ejecuciones de Silver→Gold llegó a lanzarse (Bronze→Silver
  falló antes).

Esta tarea ahora tiene doble objetivo: **arreglar esa causa raíz** (una vez,
en un sitio compartido si es razonable, o en los 6 ficheros si no lo es) y
**completar la verificación** que la primera tentativa no llegó a documentar.

**`force: false` deliberado**: quiero revisar el resultado de la primera
ejecución real de Glue/Great Expectations (coste, tiempo, calidad del dato)
antes de fusionar.

**Excepción de alcance** (`allow_infra_apply: true`): permiso para
`terraform apply` de los recursos de `infra/terraform/glue.tf` (si hiciera
falta tras el fix de código) y para lanzar manualmente los Glue jobs (`aws
glue start-job-run`).

## Objetivo

Arreglar el bug que bloqueó el primer intento (`saveAsTextFile` incompatible
con el runtime de Glue) y completar, para cada uno de los 6 datasets, **una
única carga manual** Bronze→Silver→Gold contra un lote real ya existente en
Bronze, verificando que el resultado en Silver/Gold es el esperado (esquema
correcto, puerta de calidad aplicada, agregación correcta).

## Alcance concreto

1. Arregla la causa raíz en los 6 `glue_bronze_to_silver.py`
   (`procesamiento/silver_gold/<dataset>/glue_bronze_to_silver.py`): sustituye
   `sc.parallelize(...).saveAsTextFile(...)` para escribir el informe de
   Great Expectations por una escritura directa a S3 que no dependa del
   protocolo de commit de Hadoop — es un único fichero JSON pequeño, no hace
   falta la maquinaria distribuida de Spark para escribirlo. La forma más
   simple y robusta es escribirlo con `boto3` (`s3_client.put_object(...)`)
   directamente desde el driver, igual que ya hace el resto del proyecto
   (`ingesta/capturas/bronze.py`) para escribir JSON en S3 — evita por
   completo el problema del committer en vez de intentar reconfigurarlo. Si
   decides otra solución (p.ej. usar la API de `DataFrame.write` en vez de
   RDD), justifica por qué es preferible.
   Si el resto del job (la escritura real de Silver, vía `DataFrame.write`)
   usa una ruta de escritura distinta a `saveAsTextFile`, no debería verse
   afectado por este bug — confírmalo, no des por hecho que el resto del job
   también está roto.
2. Actualiza/añade un test si la lógica cambiada es testeable sin una sesión
   Spark real (igual que el resto de `procesamiento/tests`); si el cambio
   vive enteramente dentro del entry point de Glue (que ya está fuera del
   alcance de los tests unitarios de este proyecto, ver `procesamiento/
   README.md`), no hace falta forzar un test nuevo — dilo explícitamente.
3. `terraform plan` sobre `infra/terraform/glue.tf`: dado que la
   infraestructura ya está aplicada (ver Contexto), el único cambio esperado
   es el hash del paquete de `procesamiento/` (`data.archive_file.
   procesamiento_source`) al haber cambiado el código — no debe aparecer
   ningún recurso nuevo, ni ningún trigger/schedule de Glue (`aws_glue_trigger`
   tipo `SCHEDULED`, `aws_scheduler_schedule`). Si el plan muestra algo
   inesperado, párate a entender por qué antes de aplicar.
4. `terraform apply`.
5. Para cada uno de los 6 datasets, lanza manualmente (`aws glue
   start-job-run`) el job Bronze→Silver contra el lote más reciente ya
   presente en el bucket Bronze real (`s3://madrono-tfm-dev-bronze-
   222234418587/<dataset>/...`), espera a que termine
   (`aws glue get-job-run`), y confirma en S3 que:
   - Silver contiene los registros esperados (número razonable, esquema
     correcto, ningún campo que debería haberse filtrado por la puerta de
     calidad).
   - El informe de Great Expectations se escribió correctamente.
6. Lanza el job Silver→Gold correspondiente contra lo que acabas de escribir
   en Silver, y confirma que Gold tiene la agregación esperada (compara a
   mano al menos un grupo `(id, fecha, hora)` contra los registros Silver de
   origen).
7. Documenta en `doc/051-desplegar-silver-gold-sin-schedule.md`: la causa
   raíz encontrada por el intento anterior de esta tarea y cómo la
   arreglaste, y por dataset, el resultado real de esta verificación — si
   completó sin error, cuánto tardó, cuántos registros entraron/salieron de
   cada etapa, y cualquier discrepancia entre lo esperado (según el
   código/tests de la tarea correspondiente) y lo real. Incluye valores
   reales, no solo "funcionó".
8. Si, tras el arreglo, algún job sigue fallando por un problema real de
   código distinto (no de credenciales/permisos), documenta el error exacto
   — no intentes depurarlo ni arreglarlo aquí, sería una tarea de seguimiento
   (mismo criterio que la tarea 033 con Lambda).
9. **Antes de terminar, confirma que dejas un commit real** (código +
   `doc/051-...md`) aunque algún dataset siga fallando tras el arreglo — un
   resultado parcial documentado es mucho más útil para la cola de tareas que
   terminar sin commitear nada, que es exactamente lo que falló la vez
   anterior.

## Restricciones

- NO crees ningún trigger/schedule para estos jobs de Glue — la ejecución de
  esta tarea es manual y puntual, a propósito.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni ningún recurso de la fase de
  ingesta — esta tarea es solo sobre `glue.tf`.
- Si el coste/tiempo de alguna ejecución de Glue resulta sorprendentemente
  alto, documéntalo explícitamente (es información relevante para decidir si
  programar esto en producción más adelante).

## Criterios de aceptación

- El bug de `saveAsTextFile`/`DirectOutputCommitter` está corregido en los 6
  `glue_bronze_to_silver.py`.
- Los recursos de `infra/terraform/glue.tf` para los 6 datasets siguen
  aplicados en AWS real (con el código corregido), sin ningún
  trigger/schedule.
- Cada uno de los 6 datasets tiene al menos una ejecución real y verificada
  de Bronze→Silver→Gold tras el arreglo, documentada con los resultados
  reales obtenidos (o, si alguno sigue fallando por otra causa, el error
  exacto documentado).
- `doc/051-desplegar-silver-gold-sin-schedule.md` documenta la causa raíz, el
  arreglo, y el resultado detallado dataset por dataset.
- Hay un commit real con estos cambios — el intento anterior falló
  precisamente en esto.
