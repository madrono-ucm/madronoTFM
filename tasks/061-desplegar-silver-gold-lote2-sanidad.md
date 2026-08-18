---
id: 61
slug: desplegar-silver-gold-lote2-sanidad
title: "Desplegar Glue Silver/Gold para el segundo lote (8 datasets) y verificar con un job de sanidad"
status: pending
force: false
allow_infra_apply: true
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-17T21:50:00+00:00"
updated_at: "2026-08-18T21:50:00+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

**Esta tarea ya se ha intentado y terminó sin crear ningún commit**, pese a
que `terraform apply` y los jobs de sanidad sí se ejecutaron contra AWS
real — mismo patrón que le pasó dos veces a la tarea 051. La buena noticia,
verificada manualmente fuera de la sesión de `claude` (con `aws glue
get-job-runs`, ya que el runner del agente no conserva la salida completa de
un intento que termina "ok" sin commits):

- **`terraform apply` de `glue.tf` SÍ se ejecutó y sigue aplicado**: los 8
  jobs de Bronze→Silver (y previsiblemente los 8 de Silver→Gold) existen ya
  en `eu-west-1`. **No hace falta volver a aplicar infraestructura nueva.**
- **6 de los 8 datasets completaron su job de sanidad (Bronze→Silver) CON
  ÉXITO**: `ruido`, `aforos_peatones_bicicletas`, `agenda_eventos`,
  `bluesky_menciones`, `aemet_prevision_avisos`, `cams_calidad_aire`. No
  hace falta repetir su verificación en esta tarea.
- **2 datasets fallan, ambos por el mismo motivo, ya diagnosticado**:
  `cartelera_cines_estrenos` y `afluencia_lugares`:

  ```
  s3:PutObject on resource ".../madrono-tfm-dev-silver-.../
  cartelera_cines_estrenos_$folder$" ... AccessDenied
  ```
  (mismo error para `afluencia_lugares_$folder$`)

  **Causa raíz (ya identificada, no hace falta re-investigar)**: la tarea
  051 ya había descubierto y arreglado este mismo tipo de hueco de permisos
  para el nivel **Gold** de todos los datasets (el marcador `_$folder$` que
  escribe el committer de Spark cuando el DataFrame sale vacío en esa
  ejecución) — se ve reflejado en el comentario "hueco de permisos
  detectado por el job de sanidad de la tarea 051" que ya aparece en
  `infra/terraform/glue.tf` para estos datasets. Pero para
  `cartelera_cines_estrenos` y `afluencia_lugares`, el mismo problema
  también ocurre al nivel **Silver** (su Silver sale vacío en esta
  ejecución concreta, algo que no le pasó a los otros 6), y la política IAM
  correspondiente (`data.aws_iam_policy_document.
  glue_cartelera_cines_estrenos_data_access`, statement
  `ReadWriteSilverCarteleraCinesEstrenos`; y el equivalente para
  `afluencia_lugares`) **solo tiene el recurso
  `.../silver/<dataset>/*`, sin el marcador `.../silver/<dataset>_$folder$`**
  — a diferencia del statement de Gold del mismo fichero, que ya tiene
  ambos.

## Objetivo

Arreglar el hueco de permisos IAM en esos dos datasets (añadir el recurso
`_$folder$` que falta al nivel Silver, igual que ya existe al nivel Gold) y
confirmar con un reintento del job de sanidad que los 8 datasets completan.

## Alcance concreto

1. En `infra/terraform/glue.tf`, en
   `data.aws_iam_policy_document.glue_cartelera_cines_estrenos_data_access`
   (statement `ReadWriteSilverCarteleraCinesEstrenos`) y en
   `data.aws_iam_policy_document.glue_afluencia_lugares_data_access`
   (statement equivalente), añade a `resources` la entrada
   `"${aws_s3_bucket.lakehouse["silver"].arn}/<dataset>_$folder$"` (mismo
   patrón que ya usa el statement de Gold de esos mismos ficheros).
2. Revisa si algún otro de los 8 datasets de esta tarea tiene el mismo hueco
   al nivel Silver (aunque no haya fallado esta vez, podría fallar en una
   futura ejecución cuyo Silver también salga vacío) — si lo encuentras,
   arréglalo igual, no hace falta esperar a que falle primero.
3. `terraform plan` (el único cambio esperado: estas políticas IAM, nada
   más — la infraestructura ya está aplicada, ver Contexto) y
   `terraform apply`.
4. Relanza `aws glue start-job-run` del job Bronze→Silver de
   `cartelera_cines_estrenos` y `afluencia_lugares`, espera a que terminen,
   y confirma que ya no fallan por este motivo.
5. Documenta en `doc/061-desplegar-silver-gold-lote2-sanidad.md` el
   resultado del job de sanidad de los 8 datasets (los 6 que ya completaron
   con éxito, más el resultado del reintento de los otros 2).

## Restricciones

- NO lances la matriz completa de verificación (Bronze→Silver→Gold × 8
  datasets, con comprobación de contenido) — eso es la tarea 062.
- NO crees ningún trigger/schedule de Glue — eso es la tarea 064.
- NO ejecutes `terraform destroy`.
- NO toques `infra/terraform/lambda.tf` ni el primer lote de 6 datasets ya
  desplegado.
- **Antes de terminar, confirma que dejas un commit real** (código +
  `doc/061-...md`) — un resultado parcial documentado es mucho más útil que
  terminar sin commitear nada, que es exactamente lo que ya falló una vez
  en esta misma tarea.

## Criterios de aceptación

- El hueco de permisos IAM (`_$folder$` a nivel Silver) está corregido para
  `cartelera_cines_estrenos` y `afluencia_lugares`, y para cualquier otro
  dataset de este lote que compartiera el mismo hueco.
- Los 8 datasets completan su job de sanidad Bronze→Silver sin error.
- `doc/061-desplegar-silver-gold-lote2-sanidad.md` documenta el resultado.
- Hay un commit real con estos cambios.
