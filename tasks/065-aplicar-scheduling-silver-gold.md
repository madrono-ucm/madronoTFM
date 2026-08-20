---
id: 65
slug: aplicar-scheduling-silver-gold
title: Aplicar el scheduling de Silver/Gold en producción y verificar un disparo real
status: in_progress
force: false
allow_infra_apply: true
branch: task/065-aplicar-scheduling-silver-gold
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-17T21:50:00+00:00'
updated_at: '2026-08-20T00:55:47.175426+00:00'
started_at: '2026-08-20T00:55:47.175399+00:00'
submitted_at: null
merged_at: null
---

## Contexto

**Esta tarea ya se intentó y agotó el presupuesto ($6, ~14.5M tokens, ~16
min) sin comitear nada.** La buena noticia, verificada manualmente fuera de
la sesión de `claude` (con `aws glue get-triggers`/`get-job-runs`, ya que el
runner del agente no conserva la salida completa de un intento que agota
presupuesto sin llegar a comitear):

- **`terraform apply` de los 28 `aws_glue_trigger` (14 `SCHEDULED` + 14
  `CONDITIONAL`) SÍ se ejecutó y ya están `ACTIVATED` en AWS real** — el
  objetivo principal de esta tarea ya está conseguido. **No hace falta
  volver a aplicar los triggers.**
- **Ya se ha observado un disparo automático real**: el trigger
  `SCHEDULED` del grupo "casi tiempo real" ya se activó solo al minuto 10
  de esta hora (`2026-08-20T00:10:xx`), confirmando que el mecanismo de
  cron funciona. Pero **dos de esos disparos fallaron**:
  `trafico-bronze-to-silver` y `calidad-aire-bronze-to-silver`:

  ```
  LAUNCH ERROR | Error downloading from S3 for bucket:
  madrono-tfm-dev-build-artifacts-222234418587, key:
  glue-libs/procesamiento-e6eed0971ba6bf1ee7898e319077387b.zip.
  The specified key does not exist.
  ```

  **Causa raíz (ya diagnosticada, no hace falta re-investigar)**: el
  paquete de librería compartido `procesamiento/` se sube a S3 con una key
  basada en el hash de su contenido
  (`data.archive_file.procesamiento_source` / `aws_s3_object.
  procesamiento_source`, ver `infra/terraform/glue.tf`). A lo largo de las
  tareas 051-064 se han hecho varios `terraform apply` **con `-target`
  acotado a datasets concretos** (para no arriesgar aplicar de más, buena
  práctica en sí misma) — pero eso ha dejado que distintos jobs de Glue
  queden apuntando, en AWS, a **hashes de este paquete compartido distintos
  entre sí** según cuándo se aplicó cada uno por última vez, en vez de
  converger todos al mismo. Confirmado con `terraform plan` (sin
  `-target`): el hash actualmente aplicado para este artefacto
  (`5855a63dafa6aa4649b5484981928348`) no coincide con el que generaría el
  código real de `main` ahora mismo (`16a22727668fe11274d5a8026afd36b1`), y
  ninguno de los dos coincide con el hash roto que busca `trafico`/
  `calidad_aire` (`e6eed0971ba6bf1ee7898e319077387b`) — server tres
  versiones distintas en juego, evidencia de varias `apply` parciales
  sucesivas sin una reconciliación completa.

## Objetivo

Reconciliar los 28 jobs de Glue (`aws_glue_job`) para que todos apunten al
mismo paquete `procesamiento/` actual, sin aplicar nada fuera de esa
reconciliación, y confirmar con disparos reales que el scheduling funciona
de extremo a extremo.

## Alcance concreto

1. `terraform plan` **sin `-target`**, solo para leer el diff completo (no
   apliques todavía) — vas a ver, además del artefacto compartido y los 28
   `aws_glue_job`, recursos **no relacionados y que NO debes aplicar**
   (p.ej. `aws_security_group.kafka` y el resto de `infra/terraform/
   kafka.tf`, código de la tarea 042 escrito pero deliberadamente sin
   aplicar todavía). **No hagas un `terraform apply` sin acotar.**
2. Aplica de forma acotada, con `-target` explícito para cada uno de los 28
   `aws_glue_job.*` (uno por cada `_bronze_to_silver`/`_silver_to_gold` de
   los 14 datasets) más `-target=aws_s3_object.procesamiento_source`
   — puedes generar la lista con
   `terraform state list | grep '^aws_glue_job\.'` y construir los flags
   `-target=` a partir de ahí. **No incluyas ningún recurso de
   `kafka.tf` ni ningún otro recurso no relacionado con Glue.**
3. Confirma con un segundo `terraform plan` (también sin `-target`, solo
   para leer) que ya no queda ningún `aws_glue_job` con diff pendiente —
   es normal y esperado que sigan apareciendo como pendientes los recursos
   de Kafka (no los toques).
4. Relanza (`aws glue start-trigger` o `aws glue start-job-run` directo)
   los dos jobs que fallaron (`trafico-bronze-to-silver`,
   `calidad-aire-bronze-to-silver`) y confirma que ahora completan sin el
   error de S3.
5. Para al menos 3 datasets representativos (uno del grupo "casi tiempo
   real", uno del grupo "diario", y `aemet_prevision_avisos` por su
   estructura de dos pares), fuerza el disparo con `aws glue start-trigger`
   sobre el trigger `SCHEDULED` correspondiente y confirma que el trigger
   `CONDITIONAL` dispara automáticamente el job Silver→Gold al terminar el
   anterior, sin que tú lo lances a mano, y que Gold contiene el resultado
   esperado.
6. Para el resto de datasets, confirma al menos que el trigger `SCHEDULED`
   está `ACTIVATED` (`aws glue get-trigger`) y, si tienes presupuesto,
   relanza su Bronze→Silver una vez para confirmar que ya no tiene el
   mismo problema de artefacto desincronizado que trafico/calidad_aire.
7. Documenta en `doc/065-aplicar-scheduling-silver-gold.md` el diagnóstico
   completo (el problema de artefactos desincronizados entre applies
   parciales) y el resultado de la verificación.

## Restricciones

- NO ejecutes `terraform apply` sin `-target` — el repo tiene código sin
  aplicar (Kafka, tarea 042) que no debe desplegarse como efecto colateral
  de esta tarea.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni la ingesta Bronze.
- Si algún trigger se comporta de forma inesperada (no encadena, dispara
  dos veces, etc.), documenta el problema exacto — no intentes depurarlo
  más allá de un intento razonable, sería una tarea de seguimiento.
- **Antes de terminar, confirma que dejas un commit real** con
  `doc/065-...md` — un resultado parcial documentado es mucho más útil que
  terminar sin commitear nada, que es exactamente lo que ya falló una vez
  en esta misma tarea.

## Criterios de aceptación

- Los 28 `aws_glue_job` apuntan al mismo paquete `procesamiento/` actual
  (sin diff pendiente en un `terraform plan` de solo lectura, salvo los
  recursos de Kafka, que no se tocan).
- `trafico-bronze-to-silver` y `calidad-aire-bronze-to-silver` completan
  sin el error de S3 original.
- Al menos 3 datasets representativos tienen una cadena
  SCHEDULED→CONDITIONAL verificada de extremo a extremo con un disparo
  real.
- `doc/065-aplicar-scheduling-silver-gold.md` documenta el diagnóstico y el
  resultado.
- Hay un commit real con estos cambios.
