# 093 — Recaptura del `terraform plan` de drift: 15 cambios documentados → 55 reales

**Tarea deliberadamente de solo lectura** (`allow_infra_apply: false`), continuación de
`doc/088` un día después. El QA de esta tarea sospechaba que el número que
`NEXT_STEPS.md` (Prioridad 1, punto 2) cita como pendiente de revisión humana
(`5 to add, 15 to change, 0 to destroy`, de `doc/088`, 25/8) ya no coincide con el plan
real, y que la causa probable es el despliegue manual a S3 (fuera de Terraform) que la
tarea 090 hizo a propósito sobre 4 scripts de Glue + el zip compartido
`procesamiento_source`. Esta tarea recaptura el plan real de hoy (26/8) y confirma esa
hipótesis contra el `terraform plan` real, no solo por inspección de código.

## Resultado: el plan subió de `5/15/0` a `10/55/5`

```
Plan: 10 to add, 55 to change, 5 to destroy.
```

Confirmado primero que la tarea 092 (fix de `fileset` para excluir `__pycache__`/`.pyc`/
`.pyo` del paquete de `ingesta/`) ya está fusionada en `main` (`git log`, commit
`77dbd94`) y que este worktree no tiene ningún `__pycache__` local que pudiera romper el
`plan` por el motivo ya corregido — confirmado con `find ../../ingesta -iname
"__pycache__" -o -iname "*.pyc"` sin resultados antes de generar el plan.

**Nota de entorno para tareas futuras**: esta EC2 tiene muy poco disco libre (`df -h /` ⇒
`197M` de `6.7G` antes de esta tarea) y el primer `terraform init` falló con `Error while
installing hashicorp/aws v5.100.0: ... no space left on device` (el provider de AWS
ocupa varios cientos de MB). Se resolvió sin borrar nada del propio repositorio /
directorios de otras sesiones: `export TF_PLUGIN_CACHE_DIR=/tmp/tf-plugin-cache` antes de
`terraform init` — `/tmp` es un `tmpfs` separado con casi 2 GB libres en esta instancia,
así que los binarios del provider se instalan ahí en vez de en el disco raíz, y
`.terraform/providers/` en el propio worktree queda como symlinks (unos pocos KB). Ninguna
tarea anterior (`doc/088`, `doc/092`) documentó este bloqueo — puede que sus sesiones
tuvieran más disco libre en el momento en que se ejecutaron, o que el provider ya
estuviera cacheado; para cualquier sesión futura que vea el mismo error, esta es la vía
que no requiere `sudo` (no disponible en esta EC2, `sudo` está bloqueado por
`no new privileges`) ni borrar datos de otros procesos/worktrees.

## Confirmación de la hipótesis: el zip compartido `procesamiento_source` no coincide con el estado

El `terraform plan` real muestra, en el primer job Glue que aparece
(`aws_glue_job.aemet_prevision_avisos_bronze_to_silver`):

```
~ "--extra-py-files" = "s3://.../glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip"
                     -> "s3://.../glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
```

Es decir: el estado de Terraform sigue apuntando a la clave `...-41c225d6...zip`, pero el
contenido real de `procesamiento/` en `main` hoy hashea a `...-6b73c9ac...zip` — una clave
distinta a la que el propio `aws_s3_object.procesamiento_source` tiene en el `arn`/`key`
de las mismas líneas del plan real:

```
~ etag = "41c225d658b2c0460396d681d7ef0062" -> "6b73c9ac8ba8143845e9f8429ed0b4ce"
~ key  = "glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip"
      -> "glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip" # forces replacement
```

Esto es exactamente el drift deliberado que `doc/090` dejó documentado y que
`NEXT_STEPS.md` (Prioridad 2) señala como pendiente de absorber en la Prioridad 1: la
tarea 090 sobrescribió el contenido de 4 objetos S3 de script Glue *en el sitio* (misma
clave, sin pasar por `terraform apply`, precisamente para no arrastrar el reemplazo del
zip compartido sobre datasets no tocados). Un `terraform apply` normal, en su momento, sí
habría generado una clave nueva (hash del contenido) para el zip compartido y para esos 4
scripts — como nunca se aplicó, el estado sigue con las claves antiguas, y hoy el plan
vuelve a proponer exactamente ese cambio de clave.

**Confirmado, no solo asumido**: son exactamente los mismos 4 datasets que `doc/090`
nombra como corregidos fuera de Terraform los que aparecen con `must be replaced` en el
plan de hoy:

```
$ grep -n "must be replaced" (plan real, ver abajo)
aws_s3_object.glue_script_aforos_peatones_bicicletas_silver_to_gold must be replaced
aws_s3_object.glue_script_agenda_eventos_silver_to_gold must be replaced
aws_s3_object.glue_script_bluesky_menciones_silver_to_gold must be replaced
aws_s3_object.glue_script_cartelera_cines_estrenos_silver_to_gold must be replaced
aws_s3_object.procesamiento_source must be replaced
```

Y como **~40 de los ~48 jobs Glue del proyecto** referencian ese mismo zip compartido vía
`--extra-py-files` (`doc/090`, sección "Despliegue de los 4 scripts corregidos"), el
reemplazo de `procesamiento_source` arrastra un `~ "--extra-py-files"` en cascada sobre
todos ellos — no solo sobre los 4 datasets corregidos. Ese arrastre, verificado contra el
plan real, es la causa concreta y ya identificada de por qué el número subió de 15 a 55
cambios, confirmando la hipótesis del ticket con datos del `terraform plan`, no solo por
inspección del código de la tarea 090.

## Categorización completa del plan real (`10 to add, 55 to change, 5 to destroy`)

| Categoría | Recursos | Cuenta | Motivo | Coincide con `doc/088` |
|---|---|---|---|---|
| A. Redespliegue de código Lambda a `main` | `aws_lambda_function.producer[*]` (14) | 14 (`to change`) | Mismo drift ya descrito en `doc/088` categoría A: el código de `ingesta/` en `main` no coincide con el desplegado | Sí, mismos 14, mismo motivo |
| A'. Colateral de A | `aws_iam_policy.scheduler_invoke_lambda` | 1 (`to change`) | Se relee por depender de los ARN de las 14 funciones que cambian; resuelve al mismo JSON tras aplicar | Sí, mismo colateral ya señalado en `doc/088` |
| B. Infraestructura de Kafka, nunca aplicada (tarea 042) | `aws_security_group.kafka`, `aws_iam_role.kafka`, `aws_iam_instance_profile.kafka`, `aws_iam_role_policy_attachment.kafka_ssm`, `aws_instance.kafka` | 5 (`to add`) | Sin cambios desde `doc/088` — sigue deliberadamente sin aplicar | Sí, idéntico |
| C. **Nuevo desde `doc/088`**: zip compartido de Glue desactualizado en el estado | `aws_s3_object.procesamiento_source` + 4 `aws_s3_object.glue_script_*_silver_to_gold` (`aforos_peatones_bicicletas`, `agenda_eventos`, `bluesky_menciones`, `cartelera_cines_estrenos`) | 5 (`to add`) + 5 (`to destroy`, reemplazo) | Drift deliberado de la tarea 090 (despliegue manual a S3 fuera de Terraform) — ver sección anterior | No existía en `doc/088` (25/8, antes de la tarea 090) |
| D. **Nuevo desde `doc/088`**: arrastre del zip compartido sobre el resto de jobs Glue | `aws_glue_job.*` (38 de los ~48 jobs del proyecto: los 3 pasos del pipeline — `bronze_to_silver`/`silver_backfill_dedup`/`silver_to_gold` — de cada dataset que los tiene) | 38 (`to change`) | Mismo `--extra-py-files` apuntando a la clave antigua del zip compartido (categoría C) | No existía en `doc/088` |
| E. **Nuevo desde `doc/088`**: fix de partition projection de `aforos_peatones_bicicletas` (`doc/087`, escrito en `glue.tf` pero nunca aplicado) | `aws_glue_catalog_table.aforos_peatones_bicicletas_gold`, `..._silver` | 2 (`to change`) | `projection.date.range`/`projection.fecha.range` en el código ya ampliado a `"2024-01-01,NOW+1DAY"` (`doc/087`), el catálogo real en AWS sigue con el rango estrecho original | `doc/088` no lo mencionaba explícitamente en su categorización, aunque el propio `NEXT_STEPS.md` (Prioridad 2) ya decía "fix ya escrito ... sin aplicar" — confirma que este cambio también sigue pendiente |
| F. Cualquier otra cosa | — | 0 | Revisado el plan completo (`grep -n "^  # "`): 55+10+5 = 70 líneas de recurso, exactamente 14+1+5+5+5+38+2 = 70 | — |

Cero cambios sobre `aws_s3_bucket*` (Bronze/Silver/Gold intactos), cero cambios sobre
`afluencia_lugares`/Google Maps más allá del mismo redespliegue de código que recibe
cualquier otro productor (categoría A), cero reemplazos fuera de los 5 ya esperados de la
categoría C.

## Por qué el total subió de "15 to change" a "55 to change" (y de "0/5 to destroy" a "5/10")

- `doc/088` (25/8): categorías A + A' = 15 to change; B = 5 to add; 0 to destroy.
- `doc/093` (26/8, esta tarea): (A + A') sin cambios = 15; + D (38, arrastre del zip
  compartido) + E (2, partition projection) = 55 to change; B (5) + C-adds (5) = 10 to
  add; C-destroys (5, reemplazos) = 5 to destroy.

Es decir, **todo el incremento (15 → 55, 5 → 10, 0 → 5) se explica por trabajo real
fusionado en `main` entre el 25/8 y el 26/8** (tareas 090 y su drift deliberado ya
documentado, más el fix de partition projection de la tarea 087 que seguía sin aplicar) —
no hay ningún cambio inesperado o sin explicación en el plan de hoy.

## Verificación de que no es el bug de `doc/092` (`__pycache__`)

Antes de generar el plan se confirmó que no había ningún `__pycache__`/`.pyc`/`.pyo` en
`ingesta/` en este worktree (no se ha ejecutado ningún test de `ingesta/` en esta sesión).
El `terraform init`/`plan` completó sin el error de `doc/092` — consistente con que ese
fix ya está en `main` y con que esta sesión no generó bytecode local.

## Qué NO se hizo (respeta las restricciones del alcance)

- No se ha ejecutado `terraform apply` en ningún momento.
- No se ha tocado ningún script de Glue ni código de `procesamiento/`/`ingesta/` — el
  drift descrito en la categoría D es el mismo ya documentado en `doc/090`, no un hallazgo
  nuevo que arreglar aquí.
- No se ha tocado ningún fichero `.tf`.
- `backend.hcl`/`terraform.tfvars`/`.terraform/`/`*.tfplan`/`/tmp/tf-plugin-cache` usados
  durante esta tarea son todos gitignored o están fuera del repositorio (`/tmp`); no
  quedan en el commit (`git status --porcelain` verificado limpio al terminar).

## Siguiente paso (para la tarea de "apply", punto 3 de la Prioridad 1 — no esta)

1. Revisar con un humano el plan completo de esta tarea (categorías A-E de arriba), no el
   de `doc/088` (desactualizado).
2. Si se confirma, `terraform apply` — igual que preveía `doc/088`, más la actualización
   del zip compartido de Glue y de los 4 scripts a sus claves reales (categorías C/D, sin
   cambio de comportamiento esperado: el contenido ya está desplegado y verificado en
   vivo por la tarea 090, solo cambia qué clave S3 referencia el estado) y el rango de
   partition projection de `aforos_peatones_bicicletas` (categoría E, `doc/087`).
3. Volver a verificar en vivo tras aplicar, mismo patrón que `doc/083`/`doc/088`.
4. Documentar el resultado en `doc/`.

## Salida completa y literal de `terraform plan` (sin acotar, sin aplicar)

Generada con:

```
$ export TF_PLUGIN_CACHE_DIR=/tmp/tf-plugin-cache   # ver nota de disco arriba
$ terraform init -backend-config=backend.hcl -input=false
$ terraform plan -input=false -no-color -out=/tmp/plan093.tfplan
```

usando el rol de instancia real `madrono-terraform-deployerEC2` de esta EC2 (mismas
credenciales que cualquier tarea anterior que haya tocado `infra/terraform/`), contra el
backend S3 remoto real (`madrono-tfm-terraform-state`) y el estado real de la cuenta
`222234418587` (`eu-west-1`). `terraform.tfvars` incluyó explícitamente
`lambda_dependencies_layer_arn = "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1"`
(mismo ARN verificado de nuevo con `aws lambda list-layer-versions`, sigue siendo la única
versión, `:1`) — sin él, el plan mostraría el mismo falso positivo ya documentado en
`doc/088` (Hallazgo 3, quitar la Layer de las 14 funciones).

```text

Warning: Deprecated Parameter

The parameter "dynamodb_table" is deprecated. Use parameter "use_lockfile"
instead.
data.archive_file.layer_build_source: Reading...
data.archive_file.layer_build_source: Read complete after 0s [id=91cff7c2e142516b467eed53571b9533a0dccf81]
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_assume_role: Reading...
aws_cloudwatch_log_group.glue_cartelera_cines_estrenos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-cartelera-cines-estrenos]
aws_cloudwatch_log_group.glue_calidad_aire: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-calidad-aire]
data.aws_caller_identity.current: Reading...
aws_cloudwatch_log_group.glue_aemet_prevision_avisos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-aemet-prevision-avisos]
data.aws_iam_policy_document.glue_afluencia_lugares_assume_role: Reading...
aws_cloudwatch_log_group.glue_aparcamientos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-aparcamientos]
data.aws_vpc.default: Reading...
data.aws_iam_policy_document.glue_afluencia_lugares_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_assume_role: Read complete after 0s [id=2681768870]
aws_cloudwatch_log_group.glue_cams_calidad_aire: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-cams-calidad-aire]
aws_cloudwatch_log_group.glue_aforos_peatones_bicicletas: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-aforos-peatones-bicicletas]
data.archive_file.ingesta_source: Reading...
data.aws_caller_identity.current: Read complete after 0s [id=222234418587]
aws_cloudwatch_log_group.glue_meteorologia: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-meteorologia]
data.aws_iam_policy_document.lambda_layer_codebuild_assume_role: Reading...
aws_cloudwatch_log_group.producer["afluencia_lugares"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-afluencia_lugares]
aws_cloudwatch_log_group.glue_bicimad: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-bicimad]
aws_cloudwatch_log_group.producer["cartelera_cines_estrenos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-cartelera_cines_estrenos]
data.aws_iam_policy_document.lambda_layer_codebuild_assume_role: Read complete after 0s [id=1229436035]
data.aws_iam_policy_document.glue_transporte_publico_emt_assume_role: Reading...
aws_cloudwatch_log_group.producer["cams_calidad_aire"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-cams_calidad_aire]
data.aws_iam_policy_document.glue_transporte_publico_emt_assume_role: Read complete after 0s [id=2681768870]
aws_cloudwatch_log_group.producer["bluesky_menciones"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-bluesky_menciones]
aws_cloudwatch_log_group.producer["bicimad"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-bicimad]
aws_cloudwatch_log_group.producer["meteorologia"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-meteorologia]
data.archive_file.procesamiento_source: Reading...
aws_cloudwatch_log_group.producer["transporte_publico_emt"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-transporte_publico_emt]
aws_cloudwatch_log_group.producer["calidad_aire"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-calidad_aire]
aws_cloudwatch_log_group.producer["trafico"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-trafico]
aws_cloudwatch_log_group.producer["aemet_prevision_avisos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-aemet_prevision_avisos]
aws_cloudwatch_log_group.producer["aforos_peatones_bicicletas"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-aforos_peatones_bicicletas]
aws_cloudwatch_log_group.producer["ruido"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-ruido]
aws_cloudwatch_log_group.producer["aparcamientos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-aparcamientos]
aws_cloudwatch_log_group.producer["agenda_eventos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-agenda_eventos]
aws_cloudwatch_log_group.glue_bluesky_menciones: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-bluesky-menciones]
aws_cloudwatch_log_group.glue_transporte_publico_emt: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-transporte-publico-emt]
data.aws_iam_policy_document.glue_bluesky_menciones_assume_role: Reading...
data.aws_iam_policy_document.glue_bluesky_menciones_assume_role: Read complete after 0s [id=2681768870]
aws_cloudwatch_log_group.glue_shared["logs-v2"]: Refreshing state... [id=/aws-glue/jobs/logs-v2]
aws_cloudwatch_log_group.glue_shared["output"]: Refreshing state... [id=/aws-glue/jobs/output]
aws_cloudwatch_log_group.glue_shared["error"]: Refreshing state... [id=/aws-glue/jobs/error]
data.aws_iam_policy_document.glue_aparcamientos_assume_role: Reading...
data.aws_iam_policy_document.glue_aparcamientos_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_ruido_assume_role: Reading...
data.aws_iam_policy_document.glue_ruido_assume_role: Read complete after 0s [id=2681768870]
aws_cloudwatch_log_group.glue_afluencia_lugares: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-afluencia-lugares]
data.aws_iam_policy_document.kafka_assume_role: Reading...
data.aws_iam_policy_document.glue_calidad_aire_assume_role: Reading...
data.aws_iam_policy_document.kafka_assume_role: Read complete after 0s [id=2851119427]
data.aws_iam_policy_document.glue_calidad_aire_assume_role: Read complete after 0s [id=2681768870]
data.aws_ssm_parameter.al2023_ami: Reading...
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_assume_role: Reading...
data.aws_vpc.default: Read complete after 1s [id=vpc-0cd0f252bd38d9edf]
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_agenda_eventos_assume_role: Reading...
aws_cloudwatch_log_group.glue_trafico: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-trafico]
data.aws_iam_policy_document.glue_agenda_eventos_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_trafico_assume_role: Reading...
aws_glue_catalog_database.gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold]
data.aws_iam_policy_document.glue_trafico_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_bicimad_assume_role: Reading...
data.aws_iam_policy_document.glue_bicimad_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_meteorologia_assume_role: Reading...
aws_cloudwatch_log_group.glue_ruido: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-ruido]
aws_cloudwatch_log_group.glue_agenda_eventos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-agenda-eventos]
aws_glue_catalog_database.silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver]
data.aws_iam_policy_document.glue_meteorologia_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_aemet_prevision_avisos_assume_role: Reading...
data.aws_iam_policy_document.ingestion_assume_role: Reading...
data.aws_iam_policy_document.glue_aemet_prevision_avisos_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.ingestion_assume_role: Read complete after 0s [id=2690255455]
aws_ssm_parameter.secrets["EMT_PASS_KEY"]: Refreshing state... [id=/madrono-tfm/dev/secrets/emt-pass-key]
aws_ssm_parameter.secrets["GOOGLE_MAPS_API_KEY"]: Refreshing state... [id=/madrono-tfm/dev/secrets/google-maps-api-key]
aws_ssm_parameter.secrets["AEMET_API_KEY"]: Refreshing state... [id=/madrono-tfm/dev/secrets/aemet-api-key]
data.aws_ssm_parameter.al2023_ami: Read complete after 0s [id=/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64]
aws_ssm_parameter.secrets["CAMS_ADS_API_KEY"]: Refreshing state... [id=/madrono-tfm/dev/secrets/cams-ads-api-key]
aws_ssm_parameter.secrets["EMT_CLIENT_ID"]: Refreshing state... [id=/madrono-tfm/dev/secrets/emt-client-id]
data.aws_iam_policy_document.scheduler_assume_role: Reading...
data.aws_iam_policy_document.scheduler_assume_role: Read complete after 0s [id=52247394]
data.aws_iam_policy_document.glue_cams_calidad_aire_assume_role: Reading...
data.aws_iam_policy_document.glue_cams_calidad_aire_assume_role: Read complete after 0s [id=2681768870]
aws_iam_role.glue_afluencia_lugares: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-glue-role]
aws_iam_role.glue_cartelera_cines_estrenos: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-glue-role]
aws_s3_bucket.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_s3_bucket.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
data.aws_iam_policy_document.athena_query_assume_role: Reading...
aws_iam_role.glue_transporte_publico_emt: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-glue-role]
data.aws_iam_policy_document.athena_query_assume_role: Read complete after 0s [id=337710939]
aws_iam_role.glue_bluesky_menciones: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-glue-role]
aws_iam_role.lambda_layer_codebuild: Refreshing state... [id=madrono-tfm-dev-lambda-layer-codebuild-role]
aws_iam_role.glue_aparcamientos: Refreshing state... [id=madrono-tfm-dev-aparcamientos-glue-role]
aws_iam_role.glue_ruido: Refreshing state... [id=madrono-tfm-dev-ruido-glue-role]
data.aws_iam_policy_document.ingestion_lambda_logs: Reading...
data.aws_iam_policy_document.ingestion_lambda_logs: Read complete after 0s [id=64690464]
aws_iam_role.glue_calidad_aire: Refreshing state... [id=madrono-tfm-dev-calidad-aire-glue-role]
data.aws_subnets.default: Reading...
aws_iam_role.glue_aforos_peatones_bicicletas: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-glue-role]
aws_iam_role.glue_agenda_eventos: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-glue-role]
aws_iam_role.glue_trafico: Refreshing state... [id=madrono-tfm-dev-trafico-glue-role]
aws_iam_role.glue_bicimad: Refreshing state... [id=madrono-tfm-dev-bicimad-glue-role]
data.aws_subnets.default: Read complete after 0s [id=eu-west-1]
aws_iam_role.glue_meteorologia: Refreshing state... [id=madrono-tfm-dev-meteorologia-glue-role]
aws_iam_role.glue_aemet_prevision_avisos: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-glue-role]
aws_iam_role.ingestion: Refreshing state... [id=madrono-tfm-dev-ingestion-role]
aws_iam_role.scheduler: Refreshing state... [id=madrono-tfm-dev-scheduler-role]
aws_iam_role.glue_cams_calidad_aire: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-glue-role]
aws_s3_bucket.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_s3_bucket.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
data.archive_file.ingesta_source: Read complete after 2s [id=e0c510ef29da67d41546fce773d2669b5dbdaf32]
aws_s3_bucket.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_iam_role.athena_query: Refreshing state... [id=madrono-tfm-dev-athena-query-role]
aws_iam_role_policy_attachment.glue_afluencia_lugares_service_role: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-glue-role-20260817225242316200000006]
aws_iam_role_policy_attachment.glue_cartelera_cines_estrenos_service_role: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-glue-role-2026081722524271480000000b]
aws_iam_role_policy_attachment.glue_transporte_publico_emt_service_role: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-glue-role-20260816075639707000000005]
aws_iam_policy.ingestion_lambda_logs: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-ingestion-lambda-logs]
aws_s3_object.glue_script_transporte_publico_emt_bronze_to_silver: Refreshing state... [id=glue-scripts/transporte_publico_emt_bronze_to_silver-227b9894b2fc66730ce2cbb6a7a9f6a3.py]
aws_s3_object.glue_script_cartelera_cines_estrenos_bronze_to_silver: Refreshing state... [id=glue-scripts/cartelera_cines_estrenos_bronze_to_silver-2b7b796b05eb81035f181fa7ae643321.py]
aws_s3_object.glue_script_ruido_backfill_dedup: Refreshing state... [id=glue-scripts/ruido_backfill_dedup-fce8661c6ea351323d8dbec6a79e1377.py]
aws_s3_object.glue_script_bicimad_backfill_dedup: Refreshing state... [id=glue-scripts/bicimad_backfill_dedup-ed6e6af42559477339b933051cafe77b.py]
aws_s3_object.glue_script_transporte_publico_emt_backfill_dedup_gold: Refreshing state... [id=glue-scripts/transporte_publico_emt_backfill_dedup_gold-fe90bd1230ec95accd5efc6836a9c7f5.py]
aws_s3_object.glue_script_bicimad_backfill_dedup_gold: Refreshing state... [id=glue-scripts/bicimad_backfill_dedup_gold-3cc7762735e125d2ba40c9a759900087.py]
aws_s3_object.glue_script_ruido_bronze_to_silver: Refreshing state... [id=glue-scripts/ruido_bronze_to_silver-4578e5651d5577da838113244d5be142.py]
aws_s3_object.glue_script_aparcamientos_silver_to_gold: Refreshing state... [id=glue-scripts/aparcamientos_silver_to_gold-ce49527d7c8d3dd98bcb65d2ca1b38ad.py]
aws_s3_bucket_server_side_encryption_configuration.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_s3_object.glue_script_cams_calidad_aire_backfill_dedup: Refreshing state... [id=glue-scripts/cams_calidad_aire_backfill_dedup-f740ec883030bc43077f1cf7c79cffd7.py]
aws_s3_bucket_public_access_block.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_s3_object.glue_script_ruido_silver_to_gold: Refreshing state... [id=glue-scripts/ruido_silver_to_gold-df06da27741ea0c03b88aab3ac7e0a51.py]
aws_s3_object.glue_script_transporte_publico_emt_backfill_dedup: Refreshing state... [id=glue-scripts/transporte_publico_emt_backfill_dedup-23abd9cec70fa40fd164acace5643b81.py]
aws_s3_object.glue_script_cartelera_cines_estrenos_silver_to_gold: Refreshing state... [id=glue-scripts/cartelera_cines_estrenos_silver_to_gold-90a5785103ca4aa3ef331d91a67d2851.py]
aws_s3_object.glue_script_bluesky_menciones_bronze_to_silver: Refreshing state... [id=glue-scripts/bluesky_menciones_bronze_to_silver-3911e443483f4b8bccf853ec600d43b6.py]
aws_s3_object.glue_script_silver_to_gold: Refreshing state... [id=glue-scripts/trafico_silver_to_gold-60a5f338a6cc68a8c760176719c0db97.py]
data.aws_iam_policy_document.lambda_layer_codebuild: Reading...
aws_s3_object.glue_script_cams_calidad_aire_silver_to_gold: Refreshing state... [id=glue-scripts/cams_calidad_aire_silver_to_gold-b314b6a6fc7c546a4c090fe2e01f052d.py]
aws_s3_object.glue_script_ruido_backfill_dedup_gold: Refreshing state... [id=glue-scripts/ruido_backfill_dedup_gold-f687c85eeca0b75468cfe68bb01c48c3.py]
data.aws_iam_policy_document.lambda_layer_codebuild: Read complete after 1s [id=2269842593]
aws_s3_object.glue_script_agenda_eventos_backfill_dedup: Refreshing state... [id=glue-scripts/agenda_eventos_backfill_dedup-406949108f74a212bfa3dd0a5f67acca.py]
aws_s3_object.glue_script_aparcamientos_backfill_dedup_gold: Refreshing state... [id=glue-scripts/aparcamientos_backfill_dedup_gold-b03433c6e4e72c7e33e557790f1809b2.py]
aws_s3_object.glue_script_bluesky_menciones_silver_to_gold: Refreshing state... [id=glue-scripts/bluesky_menciones_silver_to_gold-eebc2e82aa50cb399f022af861372782.py]
aws_s3_object.glue_script_calidad_aire_backfill_dedup_gold: Refreshing state... [id=glue-scripts/calidad_aire_backfill_dedup_gold-b1b779d81465784f5abab97e0cbdab0c.py]
aws_s3_object.glue_script_cams_calidad_aire_backfill_dedup_gold: Refreshing state... [id=glue-scripts/cams_calidad_aire_backfill_dedup_gold-1a9154bc6c0c71a12b1e6c42eea25f30.py]
aws_s3_object.glue_script_agenda_eventos_backfill_dedup_gold: Refreshing state... [id=glue-scripts/agenda_eventos_backfill_dedup_gold-b4c8693ee116e2f50aee1b96fd7018c6.py]
aws_s3_object.glue_script_bicimad_bronze_to_silver: Refreshing state... [id=glue-scripts/bicimad_bronze_to_silver-44a29129cff7226b539da9071dd8f8b7.py]
aws_s3_object.glue_script_agenda_eventos_silver_to_gold: Refreshing state... [id=glue-scripts/agenda_eventos_silver_to_gold-73b5e533d9966653fcd6f2597254ba59.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_backfill_dedup: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_backfill_dedup-8dc97077e9a7b0d793edb42e68c8a090.py]
aws_lambda_layer_version.ingesta_dependencies: Refreshing state... [id=arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1]
aws_s3_object.layer_build_source: Refreshing state... [id=source/ingesta-requirements-dda68d48ce6639f0dc4b67370d63ca56.zip]
aws_s3_object.glue_script_transporte_publico_emt_silver_to_gold: Refreshing state... [id=glue-scripts/transporte_publico_emt_silver_to_gold-31a48a9152356f0fb479193b278e8d0c.py]
aws_s3_object.glue_script_meteorologia_bronze_to_silver: Refreshing state... [id=glue-scripts/meteorologia_bronze_to_silver-9f8c92a3c75695ffe310682ba8d437b0.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_bronze_to_silver: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_bronze_to_silver-d037fa3c1d50aa6cdf1a4355e4af910b.py]
data.aws_iam_policy_document.build_artifacts_bucket_policy: Reading...
aws_s3_object.glue_script_aparcamientos_bronze_to_silver: Refreshing state... [id=glue-scripts/aparcamientos_bronze_to_silver-90e5ef17131a899ea2f70fcff0bb1962.py]
data.aws_iam_policy_document.build_artifacts_bucket_policy: Read complete after 0s [id=1312249984]
aws_s3_object.glue_script_bluesky_menciones_backfill_dedup: Refreshing state... [id=glue-scripts/bluesky_menciones_backfill_dedup-2efdec7fc5aa3a4ed77dbee6c1a5e2d4.py]
aws_s3_object.glue_script_cams_calidad_aire_bronze_to_silver: Refreshing state... [id=glue-scripts/cams_calidad_aire_bronze_to_silver-c0577843a652fafb4ba8dc477363c545.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_backfill_dedup_gold: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_backfill_dedup_gold-dedd44063c766e8475986650df404498.py]
aws_s3_object.glue_script_meteorologia_silver_to_gold: Refreshing state... [id=glue-scripts/meteorologia_silver_to_gold-169c14fd98eac491489861d9e5192564.py]
aws_s3_object.glue_script_meteorologia_backfill_dedup: Refreshing state... [id=glue-scripts/meteorologia_backfill_dedup-d0fd57ddf99e04744edfcba8d690721c.py]
aws_s3_object.glue_script_agenda_eventos_bronze_to_silver: Refreshing state... [id=glue-scripts/agenda_eventos_bronze_to_silver-e24cfdad3be04dfe065231b9643719c0.py]
aws_s3_object.glue_script_calidad_aire_silver_to_gold: Refreshing state... [id=glue-scripts/calidad_aire_silver_to_gold-2aa3d2a268bb6c9d89020347d439f194.py]
aws_s3_object.glue_script_bronze_to_silver: Refreshing state... [id=glue-scripts/trafico_bronze_to_silver-168f6d4b74abbb184207e7548dc13bdb.py]
aws_s3_object.glue_script_bluesky_menciones_backfill_dedup_gold: Refreshing state... [id=glue-scripts/bluesky_menciones_backfill_dedup_gold-eaac70080a579db34ec3c54244f4e426.py]
aws_s3_bucket_lifecycle_configuration.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_s3_object.glue_script_aparcamientos_backfill_dedup: Refreshing state... [id=glue-scripts/aparcamientos_backfill_dedup-d2f4134d5b53957b15e82d4bed24c7eb.py]
aws_s3_object.glue_script_afluencia_lugares_silver_to_gold: Refreshing state... [id=glue-scripts/afluencia_lugares_silver_to_gold-62c7375ae0141dbeab3bcc17a4936081.py]
aws_s3_object.glue_script_aemet_prevision_avisos_bronze_to_silver: Refreshing state... [id=glue-scripts/aemet_prevision_avisos_bronze_to_silver-5874411ad6f28f158f685ce90841add5.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_silver_to_gold: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_silver_to_gold-1ed5acbc05f8bc8dc8c53eae4e789893.py]
aws_s3_object.glue_script_meteorologia_backfill_dedup_gold: Refreshing state... [id=glue-scripts/meteorologia_backfill_dedup_gold-f919944ff6593ee881f3d4d2a4c57ecf.py]
aws_s3_object.glue_script_calidad_aire_backfill_dedup: Refreshing state... [id=glue-scripts/calidad_aire_backfill_dedup-34fd8107fa813f83f6e1b5b6ad747653.py]
aws_s3_object.glue_script_afluencia_lugares_bronze_to_silver: Refreshing state... [id=glue-scripts/afluencia_lugares_bronze_to_silver-e019ce6127891d24af49cb253082177b.py]
aws_s3_object.glue_script_calidad_aire_bronze_to_silver: Refreshing state... [id=glue-scripts/calidad_aire_bronze_to_silver-da2056544438c70f538d76fa59f438a4.py]
aws_s3_object.glue_script_bicimad_silver_to_gold: Refreshing state... [id=glue-scripts/bicimad_silver_to_gold-c843909cc91d34dcfdcf321695e074a2.py]
aws_s3_object.glue_script_aemet_prevision_avisos_silver_to_gold: Refreshing state... [id=glue-scripts/aemet_prevision_avisos_silver_to_gold-735e6a4f6938be2c1d4d15ce74735529.py]
aws_iam_role_policy_attachment.glue_bluesky_menciones_service_role: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-glue-role-20260817225241998700000001]
aws_iam_role_policy_attachment.glue_aparcamientos_service_role: Refreshing state... [id=madrono-tfm-dev-aparcamientos-glue-role-20260816075639434100000004]
aws_s3_bucket_public_access_block.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
aws_s3_bucket_lifecycle_configuration.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
data.aws_iam_policy_document.athena_results_bucket_policy: Reading...
aws_athena_workgroup.silver_gold: Refreshing state... [id=madrono-tfm-dev-silver-gold]
data.aws_iam_policy_document.athena_results_bucket_policy: Read complete after 0s [id=3728792540]
aws_s3_bucket_server_side_encryption_configuration.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
aws_iam_role_policy_attachment.glue_ruido_service_role: Refreshing state... [id=madrono-tfm-dev-ruido-glue-role-20260817225242315200000005]
aws_iam_role_policy_attachment.glue_calidad_aire_service_role: Refreshing state... [id=madrono-tfm-dev-calidad-aire-glue-role-20260816075639813800000006]
aws_iam_role_policy_attachment.glue_aforos_peatones_bicicletas_service_role: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-glue-role-20260817225242176000000003]
aws_iam_role_policy_attachment.glue_agenda_eventos_service_role: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-glue-role-20260817225242339700000007]
aws_iam_role_policy_attachment.glue_trafico_service_role: Refreshing state... [id=madrono-tfm-dev-trafico-glue-role-20260816075639044000000003]
aws_iam_role_policy_attachment.glue_bicimad_service_role: Refreshing state... [id=madrono-tfm-dev-bicimad-glue-role-20260816075639036000000002]
aws_iam_role_policy_attachment.glue_aemet_prevision_avisos_service_role: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-glue-role-20260817225242271000000004]
aws_iam_role_policy_attachment.glue_meteorologia_service_role: Refreshing state... [id=madrono-tfm-dev-meteorologia-glue-role-20260816075639015600000001]
aws_iam_role_policy_attachment.glue_cams_calidad_aire_service_role: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-glue-role-20260817225242109200000002]
aws_iam_role_policy_attachment.ingestion_lambda_logs: Refreshing state... [id=madrono-tfm-dev-ingestion-role-20260814212955875100000001]
aws_glue_catalog_table.calidad_aire_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:calidad_aire_por_estacion_contaminante_hora]
data.aws_iam_policy_document.glue_meteorologia_data_access: Reading...
data.aws_iam_policy_document.glue_agenda_eventos_data_access: Reading...
aws_glue_catalog_table.meteorologia_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:meteorologia_por_estacion_magnitud_hora]
data.aws_iam_policy_document.glue_agenda_eventos_data_access: Read complete after 0s [id=2233283693]
data.aws_iam_policy_document.glue_meteorologia_data_access: Read complete after 0s [id=1660976330]
data.aws_iam_policy_document.glue_transporte_publico_emt_data_access: Reading...
data.aws_iam_policy_document.glue_bluesky_menciones_data_access: Reading...
data.aws_iam_policy_document.ingestion_bronze_write: Reading...
aws_glue_catalog_table.agenda_eventos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:agenda_eventos]
aws_glue_catalog_table.ruido_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:ruido_por_estacion_periodo_fecha]
data.aws_iam_policy_document.glue_transporte_publico_emt_data_access: Read complete after 0s [id=1469263382]
data.aws_iam_policy_document.ingestion_bronze_write: Read complete after 0s [id=175239690]
data.aws_iam_policy_document.glue_bluesky_menciones_data_access: Read complete after 0s [id=3016547089]
aws_s3_bucket_versioning.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_public_access_block.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
data.aws_iam_policy_document.glue_aparcamientos_data_access: Reading...
data.aws_iam_policy_document.glue_aparcamientos_data_access: Read complete after 0s [id=3918684311]
aws_glue_job.transporte_publico_emt_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-gold-backfill-dedup]
aws_glue_job.bicimad_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bicimad-gold-backfill-dedup]
data.aws_iam_policy_document.glue_bicimad_data_access: Reading...
data.aws_iam_policy_document.glue_afluencia_lugares_data_access: Reading...
data.aws_iam_policy_document.glue_afluencia_lugares_data_access: Read complete after 0s [id=2439414232]
data.aws_iam_policy_document.glue_bicimad_data_access: Read complete after 0s [id=2467033104]
data.aws_iam_policy_document.glue_ruido_data_access: Reading...
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_data_access: Reading...
data.aws_iam_policy_document.glue_ruido_data_access: Read complete after 0s [id=3942754620]
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_data_access: Read complete after 0s [id=2497092921]
data.aws_iam_policy_document.glue_trafico_data_access: Reading...
aws_glue_catalog_table.aparcamientos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aparcamientos_por_parking_hora]
data.aws_iam_policy_document.glue_trafico_data_access: Read complete after 0s [id=3067492418]
aws_glue_catalog_table.aemet_prevision_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aemet_prevision_por_municipio_leadtime]
aws_glue_catalog_table.aparcamientos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aparcamientos]
aws_glue_catalog_table.cams_calidad_aire_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:cams_calidad_aire_por_contaminante_fecha_validez]
aws_glue_catalog_table.agenda_eventos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:agenda_eventos_por_categoria_distrito_fecha]
aws_glue_catalog_table.bluesky_menciones_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:bluesky_menciones_por_termino_modo_hora]
aws_glue_catalog_table.bicimad_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:bicimad]
data.aws_iam_policy_document.glue_calidad_aire_data_access: Reading...
data.aws_iam_policy_document.glue_calidad_aire_data_access: Read complete after 0s [id=3442098839]
aws_glue_catalog_table.calidad_aire_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:calidad_aire]
aws_glue_catalog_table.meteorologia_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:meteorologia]
aws_glue_catalog_table.aemet_prevision_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aemet_prevision]
data.aws_iam_policy_document.glue_cams_calidad_aire_data_access: Reading...
aws_glue_catalog_table.aemet_avisos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aemet_avisos_por_zona_fecha_nivel]
data.aws_iam_policy_document.glue_cams_calidad_aire_data_access: Read complete after 0s [id=3873881262]
aws_glue_catalog_table.aforos_peatones_bicicletas_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aforos_peatones_bicicletas]
aws_glue_catalog_table.cartelera_cines_estrenos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:cartelera_cines_estrenos]
aws_glue_catalog_table.ruido_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:ruido]
aws_glue_catalog_table.bluesky_menciones_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:bluesky_menciones]
aws_glue_catalog_table.trafico_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:trafico]
aws_glue_catalog_table.aforos_peatones_bicicletas_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aforos_peatones_bicicletas_por_estacion_modo_hora]
aws_glue_catalog_table.trafico_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:trafico_por_punto_hora]
data.aws_iam_policy_document.glue_aemet_prevision_avisos_data_access: Reading...
aws_glue_catalog_table.afluencia_lugares_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:afluencia_lugares]
data.aws_iam_policy_document.glue_aemet_prevision_avisos_data_access: Read complete after 0s [id=192142698]
aws_glue_catalog_table.bicimad_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:bicimad_por_estacion_hora]
aws_glue_catalog_table.afluencia_lugares_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:afluencia_lugares_por_lugar_fecha_hora]
aws_glue_catalog_table.transporte_publico_emt_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:transporte_publico_emt_por_parada_hora]
aws_glue_catalog_table.aemet_avisos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aemet_avisos]
aws_glue_catalog_table.cartelera_cines_estrenos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:cartelera_cines_estrenos_por_pelicula_cine_fecha]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
data.aws_iam_policy_document.bucket_policy["bronze"]: Reading...
data.aws_iam_policy_document.bucket_policy["gold"]: Reading...
data.aws_iam_policy_document.bucket_policy["gold"]: Read complete after 0s [id=1014628649]
data.aws_iam_policy_document.bucket_policy["bronze"]: Read complete after 0s [id=42177744]
data.aws_iam_policy_document.bucket_policy["silver"]: Reading...
aws_s3_bucket_versioning.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_data_access: Reading...
aws_s3_bucket_versioning.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
data.aws_iam_policy_document.bucket_policy["silver"]: Read complete after 0s [id=168412883]
aws_s3_bucket_public_access_block.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_data_access: Read complete after 0s [id=3258002293]
aws_iam_role_policy.lambda_layer_codebuild: Refreshing state... [id=madrono-tfm-dev-lambda-layer-codebuild-role:madrono-tfm-dev-lambda-layer-codebuild-policy]
aws_s3_bucket_public_access_block.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_glue_catalog_table.cams_calidad_aire_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:cams_calidad_aire]
aws_glue_catalog_table.transporte_publico_emt_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:transporte_publico_emt]
aws_glue_job.ruido_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-ruido-gold-backfill-dedup]
aws_glue_job.cams_calidad_aire_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-gold-backfill-dedup]
aws_glue_job.aparcamientos_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aparcamientos-gold-backfill-dedup]
aws_glue_job.calidad_aire_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-calidad-aire-gold-backfill-dedup]
aws_glue_job.agenda_eventos_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-gold-backfill-dedup]
aws_s3_bucket_policy.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_glue_job.aforos_peatones_bicicletas_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-gold-backfill-dedup]
aws_glue_job.bluesky_menciones_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-gold-backfill-dedup]
aws_glue_job.meteorologia_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-meteorologia-gold-backfill-dedup]
aws_s3_bucket_policy.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
aws_iam_policy.glue_agenda_eventos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-agenda-eventos-data-access]
data.aws_iam_policy_document.athena_query: Reading...
data.aws_iam_policy_document.athena_query: Read complete after 0s [id=1764529612]
aws_iam_policy.glue_meteorologia_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-meteorologia-data-access]
aws_lambda_function.producer["aemet_prevision_avisos"]: Refreshing state... [id=madrono-tfm-dev-aemet_prevision_avisos]
aws_lambda_function.producer["transporte_publico_emt"]: Refreshing state... [id=madrono-tfm-dev-transporte_publico_emt]
aws_lambda_function.producer["agenda_eventos"]: Refreshing state... [id=madrono-tfm-dev-agenda_eventos]
aws_lambda_function.producer["aparcamientos"]: Refreshing state... [id=madrono-tfm-dev-aparcamientos]
aws_lambda_function.producer["trafico"]: Refreshing state... [id=madrono-tfm-dev-trafico]
aws_lambda_function.producer["calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-calidad_aire]
aws_lambda_function.producer["cartelera_cines_estrenos"]: Refreshing state... [id=madrono-tfm-dev-cartelera_cines_estrenos]
aws_lambda_function.producer["afluencia_lugares"]: Refreshing state... [id=madrono-tfm-dev-afluencia_lugares]
aws_lambda_function.producer["bluesky_menciones"]: Refreshing state... [id=madrono-tfm-dev-bluesky_menciones]
aws_lambda_function.producer["aforos_peatones_bicicletas"]: Refreshing state... [id=madrono-tfm-dev-aforos_peatones_bicicletas]
aws_lambda_function.producer["meteorologia"]: Refreshing state... [id=madrono-tfm-dev-meteorologia]
aws_lambda_function.producer["bicimad"]: Refreshing state... [id=madrono-tfm-dev-bicimad]
aws_lambda_function.producer["ruido"]: Refreshing state... [id=madrono-tfm-dev-ruido]
aws_lambda_function.producer["cams_calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-cams_calidad_aire]
aws_iam_policy.glue_transporte_publico_emt_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-transporte-publico-emt-data-access]
aws_iam_policy.ingestion_bronze_write: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-ingestion-bronze-write]
aws_iam_policy.glue_aparcamientos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-aparcamientos-data-access]
aws_iam_policy.glue_bluesky_menciones_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-bluesky-menciones-data-access]
aws_iam_policy.glue_afluencia_lugares_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-afluencia-lugares-data-access]
data.archive_file.procesamiento_source: Read complete after 9s [id=89f51956199895716a4f57fee9bf88770ca59c7f]
aws_iam_policy.glue_bicimad_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-bicimad-data-access]
aws_iam_policy.glue_ruido_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-ruido-data-access]
aws_iam_policy.glue_trafico_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-trafico-data-access]
aws_iam_policy.glue_aforos_peatones_bicicletas_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-aforos-peatones-bicicletas-data-access]
aws_iam_policy.glue_calidad_aire_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-calidad-aire-data-access]
aws_iam_policy.glue_cams_calidad_aire_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-cams-calidad-aire-data-access]
aws_iam_policy.glue_aemet_prevision_avisos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-aemet-prevision-avisos-data-access]
aws_s3_bucket_policy.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_policy.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_s3_bucket_policy.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_codebuild_project.lambda_dependencies_layer: Refreshing state... [id=arn:aws:codebuild:eu-west-1:222234418587:project/madrono-tfm-dev-lambda-dependencies-layer]
aws_iam_policy.glue_cartelera_cines_estrenos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-cartelera-cines-estrenos-data-access]
aws_iam_policy.athena_query: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-athena-query]
aws_iam_role_policy_attachment.glue_agenda_eventos_data_access: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-glue-role-2026081722524290960000000f]
aws_s3_bucket_lifecycle_configuration.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_iam_role_policy_attachment.glue_meteorologia_data_access: Refreshing state... [id=madrono-tfm-dev-meteorologia-glue-role-2026081607564030390000000c]
aws_s3_bucket_lifecycle_configuration.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_lifecycle_configuration.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_iam_role_policy_attachment.ingestion_bronze_write: Refreshing state... [id=madrono-tfm-dev-ingestion-role-20260813160151981500000001]
aws_iam_role_policy_attachment.glue_transporte_publico_emt_data_access: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-glue-role-2026081607564024520000000b]
aws_iam_role_policy_attachment.glue_bluesky_menciones_data_access: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-glue-role-2026081722524272500000000d]
aws_iam_role_policy_attachment.glue_aparcamientos_data_access: Refreshing state... [id=madrono-tfm-dev-aparcamientos-glue-role-20260816075639899700000008]
aws_iam_role_policy_attachment.glue_afluencia_lugares_data_access: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-glue-role-2026081722524275410000000e]
aws_iam_role_policy_attachment.glue_bicimad_data_access: Refreshing state... [id=madrono-tfm-dev-bicimad-glue-role-20260816075639983400000009]
aws_iam_role_policy_attachment.glue_ruido_data_access: Refreshing state... [id=madrono-tfm-dev-ruido-glue-role-20260817225242694700000008]
aws_scheduler_schedule.producer["cartelera_cines_estrenos"]: Refreshing state... [id=default/madrono-tfm-dev-cartelera_cines_estrenos]
aws_scheduler_schedule.producer["trafico"]: Refreshing state... [id=default/madrono-tfm-dev-trafico]
aws_scheduler_schedule.producer["aemet_avisos_1100"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_1100]
aws_scheduler_schedule.producer["aemet_avisos_1800"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_1800]
aws_scheduler_schedule.producer["aemet_avisos_2350"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_2350]
aws_scheduler_schedule.producer["afluencia_lugares"]: Refreshing state... [id=default/madrono-tfm-dev-afluencia_lugares]
aws_scheduler_schedule.producer["aforos_peatones_bicicletas"]: Refreshing state... [id=default/madrono-tfm-dev-aforos_peatones_bicicletas]
aws_scheduler_schedule.producer["agenda_eventos"]: Refreshing state... [id=default/madrono-tfm-dev-agenda_eventos]
aws_scheduler_schedule.producer["cams_0715_utc"]: Refreshing state... [id=default/madrono-tfm-dev-cams_0715_utc]
aws_scheduler_schedule.producer["cartelera_cines_estrenos_sesiones"]: Refreshing state... [id=default/madrono-tfm-dev-cartelera_cines_estrenos_sesiones]
aws_scheduler_schedule.producer["aparcamientos"]: Refreshing state... [id=default/madrono-tfm-dev-aparcamientos]
aws_scheduler_schedule.producer["calidad_aire"]: Refreshing state... [id=default/madrono-tfm-dev-calidad_aire]
aws_scheduler_schedule.producer["emt_llegadas"]: Refreshing state... [id=default/madrono-tfm-dev-emt_llegadas]
aws_scheduler_schedule.producer["meteorologia"]: Refreshing state... [id=default/madrono-tfm-dev-meteorologia]
aws_scheduler_schedule.producer["ruido"]: Refreshing state... [id=default/madrono-tfm-dev-ruido]
aws_scheduler_schedule.producer["aemet_prevision_0700"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_prevision_0700]
aws_scheduler_schedule.producer["aemet_prevision_1400"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_prevision_1400]
aws_scheduler_schedule.producer["bluesky_menciones"]: Refreshing state... [id=default/madrono-tfm-dev-bluesky_menciones]
aws_scheduler_schedule.producer["cams_0900_utc"]: Refreshing state... [id=default/madrono-tfm-dev-cams_0900_utc]
aws_scheduler_schedule.producer["aemet_avisos_0800"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_0800]
aws_scheduler_schedule.producer["bicimad"]: Refreshing state... [id=default/madrono-tfm-dev-bicimad]
aws_iam_role_policy_attachment.glue_calidad_aire_data_access: Refreshing state... [id=madrono-tfm-dev-calidad-aire-glue-role-20260816075639853300000007]
aws_iam_role_policy_attachment.glue_trafico_data_access: Refreshing state... [id=madrono-tfm-dev-trafico-glue-role-2026081607564002340000000a]
aws_iam_role_policy_attachment.glue_cams_calidad_aire_data_access: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-glue-role-2026081722524272170000000c]
aws_iam_role_policy_attachment.glue_aforos_peatones_bicicletas_data_access: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-glue-role-20260817225242712100000009]
aws_iam_role_policy_attachment.glue_aemet_prevision_avisos_data_access: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-glue-role-20260817225242985500000010]
aws_iam_role_policy_attachment.athena_query: Refreshing state... [id=madrono-tfm-dev-athena-query-role-20260820014319117700000001]
aws_iam_role_policy_attachment.glue_cartelera_cines_estrenos_data_access: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-glue-role-2026081722524271210000000a]
aws_iam_policy.scheduler_invoke_lambda: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-scheduler-invoke-lambda]
aws_s3_object.procesamiento_source: Refreshing state... [id=glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip]
aws_iam_role_policy_attachment.scheduler_invoke_lambda: Refreshing state... [id=madrono-tfm-dev-scheduler-role-20260814213123137400000002]
aws_glue_job.meteorologia_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-meteorologia-bronze-to-silver]
aws_glue_job.bicimad_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bicimad-silver-backfill-dedup]
aws_glue_job.trafico_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-trafico-bronze-to-silver]
aws_glue_job.bicimad_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-bicimad-silver-to-gold]
aws_glue_job.aforos_peatones_bicicletas_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-bronze-to-silver]
aws_glue_job.agenda_eventos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-bronze-to-silver]
aws_glue_job.agenda_eventos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-silver-to-gold]
aws_glue_job.aparcamientos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-aparcamientos-bronze-to-silver]
aws_glue_job.cams_calidad_aire_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-bronze-to-silver]
aws_glue_job.meteorologia_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-meteorologia-silver-to-gold]
aws_glue_job.transporte_publico_emt_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-silver-backfill-dedup]
aws_glue_job.cams_calidad_aire_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-silver-to-gold]
aws_glue_job.cartelera_cines_estrenos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-silver-to-gold]
aws_glue_job.aemet_prevision_avisos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-bronze-to-silver]
aws_glue_job.cartelera_cines_estrenos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-bronze-to-silver]
aws_glue_job.afluencia_lugares_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-bronze-to-silver]
aws_glue_job.ruido_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-ruido-bronze-to-silver]
aws_glue_job.calidad_aire_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-calidad-aire-bronze-to-silver]
aws_glue_job.ruido_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-ruido-silver-to-gold]
aws_glue_job.agenda_eventos_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-silver-backfill-dedup]
aws_glue_job.aemet_prevision_avisos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold]
aws_glue_job.calidad_aire_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-calidad-aire-silver-backfill-dedup]
aws_glue_job.aparcamientos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-aparcamientos-silver-to-gold]
aws_glue_job.meteorologia_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-meteorologia-silver-backfill-dedup]
aws_glue_job.transporte_publico_emt_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-bronze-to-silver]
aws_glue_job.ruido_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-ruido-silver-backfill-dedup]
aws_glue_job.cams_calidad_aire_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-silver-backfill-dedup]
aws_glue_job.bicimad_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-bicimad-bronze-to-silver]
aws_glue_job.aparcamientos_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aparcamientos-silver-backfill-dedup]
aws_glue_job.bluesky_menciones_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-silver-to-gold]
aws_glue_job.transporte_publico_emt_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-silver-to-gold]
aws_glue_job.aforos_peatones_bicicletas_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-silver-backfill-dedup]
aws_glue_job.aforos_peatones_bicicletas_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-silver-to-gold]
aws_glue_job.afluencia_lugares_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-silver-to-gold]
aws_glue_job.bluesky_menciones_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-bronze-to-silver]
aws_glue_job.calidad_aire_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-calidad-aire-silver-to-gold]
aws_glue_job.trafico_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-trafico-silver-to-gold]
aws_glue_job.bluesky_menciones_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-silver-backfill-dedup]
aws_glue_trigger.scheduled_bronze_to_silver_daily["cartelera_cines_estrenos"]: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["cams_calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["bluesky_menciones"]: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["afluencia_lugares"]: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["aparcamientos"]: Refreshing state... [id=madrono-tfm-dev-aparcamientos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["aforos_peatones_bicicletas"]: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["aemet_prevision_avisos"]: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["ruido"]: Refreshing state... [id=madrono-tfm-dev-ruido-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["bicimad"]: Refreshing state... [id=madrono-tfm-dev-bicimad-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["agenda_eventos"]: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-calidad-aire-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["meteorologia"]: Refreshing state... [id=madrono-tfm-dev-meteorologia-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["trafico"]: Refreshing state... [id=madrono-tfm-dev-trafico-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["transporte_publico_emt"]: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-scheduled-bronze-to-silver]
aws_glue_trigger.conditional_silver_to_gold_hourly["aparcamientos"]: Refreshing state... [id=madrono-tfm-dev-aparcamientos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-calidad-aire-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["transporte_publico_emt"]: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["trafico"]: Refreshing state... [id=madrono-tfm-dev-trafico-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["bicimad"]: Refreshing state... [id=madrono-tfm-dev-bicimad-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["meteorologia"]: Refreshing state... [id=madrono-tfm-dev-meteorologia-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["bluesky_menciones"]: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["agenda_eventos"]: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["cartelera_cines_estrenos"]: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["afluencia_lugares"]: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["aemet_prevision_avisos"]: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["aforos_peatones_bicicletas"]: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["cams_calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["ruido"]: Refreshing state... [id=madrono-tfm-dev-ruido-conditional-silver-to-gold]

Terraform used the selected providers to generate the following execution
plan. Resource actions are indicated with the following symbols:
  + create
  ~ update in-place
-/+ destroy and then create replacement
 <= read (data resources)

Terraform will perform the following actions:

  # data.aws_iam_policy_document.scheduler_invoke_lambda will be read during apply
  # (depends on a resource or a module with changes pending)
 <= data "aws_iam_policy_document" "scheduler_invoke_lambda" {
      + id            = (known after apply)
      + json          = (known after apply)
      + minified_json = (known after apply)

      + statement {
          + actions   = [
              + "lambda:InvokeFunction",
            ]
          + effect    = "Allow"
          + resources = [
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aemet_prevision_avisos",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-afluencia_lugares",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aforos_peatones_bicicletas",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-agenda_eventos",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aparcamientos",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-bicimad",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-bluesky_menciones",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-calidad_aire",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-cams_calidad_aire",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-cartelera_cines_estrenos",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-meteorologia",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-ruido",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-trafico",
              + "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-transporte_publico_emt",
            ]
          + sid       = "InvokeProducerLambdas"
        }
    }

  # aws_glue_catalog_table.aforos_peatones_bicicletas_gold will be updated in-place
  ~ resource "aws_glue_catalog_table" "aforos_peatones_bicicletas_gold" {
        id                 = "222234418587:madrono-tfm_dev_gold:aforos_peatones_bicicletas_por_estacion_modo_hora"
        name               = "aforos_peatones_bicicletas_por_estacion_modo_hora"
      ~ parameters         = {
          ~ "projection.date.range"         = "2026-08-01,NOW+1DAY" -> "2024-01-01,NOW+1DAY"
            # (8 unchanged elements hidden)
        }
        # (9 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_catalog_table.aforos_peatones_bicicletas_silver will be updated in-place
  ~ resource "aws_glue_catalog_table" "aforos_peatones_bicicletas_silver" {
        id                 = "222234418587:madrono-tfm_dev_silver:aforos_peatones_bicicletas"
        name               = "aforos_peatones_bicicletas"
      ~ parameters         = {
          ~ "projection.fecha.range"         = "2026-08-01,NOW+1DAY" -> "2024-01-01,NOW+1DAY"
            # (11 unchanged elements hidden)
        }
        # (9 unchanged attributes hidden)

        # (3 unchanged blocks hidden)
    }

  # aws_glue_job.aemet_prevision_avisos_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "aemet_prevision_avisos_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (11 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-aemet-prevision-avisos-bronze-to-silver"
        name                      = "madrono-tfm-dev-aemet-prevision-avisos-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.aemet_prevision_avisos_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "aemet_prevision_avisos_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold"
        name                      = "madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.afluencia_lugares_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "afluencia_lugares_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-afluencia-lugares-bronze-to-silver"
        name                      = "madrono-tfm-dev-afluencia-lugares-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.afluencia_lugares_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "afluencia_lugares_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-afluencia-lugares-silver-to-gold"
        name                      = "madrono-tfm-dev-afluencia-lugares-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.aforos_peatones_bicicletas_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "aforos_peatones_bicicletas_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-aforos-peatones-bicicletas-bronze-to-silver"
        name                      = "madrono-tfm-dev-aforos-peatones-bicicletas-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.aforos_peatones_bicicletas_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "aforos_peatones_bicicletas_silver_backfill_dedup" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-aforos-peatones-bicicletas-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-aforos-peatones-bicicletas-silver-backfill-dedup"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.aforos_peatones_bicicletas_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "aforos_peatones_bicicletas_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-aforos-peatones-bicicletas-silver-to-gold"
        name                      = "madrono-tfm-dev-aforos-peatones-bicicletas-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_silver_to_gold-1ed5acbc05f8bc8dc8c53eae4e789893.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_silver_to_gold-98ae6a2fa1ca9fc05b6451aaffbd690b.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.agenda_eventos_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "agenda_eventos_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-agenda-eventos-bronze-to-silver"
        name                      = "madrono-tfm-dev-agenda-eventos-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.agenda_eventos_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "agenda_eventos_silver_backfill_dedup" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-agenda-eventos-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-agenda-eventos-silver-backfill-dedup"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.agenda_eventos_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "agenda_eventos_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-agenda-eventos-silver-to-gold"
        name                      = "madrono-tfm-dev-agenda-eventos-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_silver_to_gold-73b5e533d9966653fcd6f2597254ba59.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_silver_to_gold-7ed6c1455ead3aef19f9e40b96c23a51.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.aparcamientos_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "aparcamientos_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-aparcamientos-bronze-to-silver"
        name                      = "madrono-tfm-dev-aparcamientos-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.aparcamientos_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "aparcamientos_silver_backfill_dedup" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-aparcamientos-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-aparcamientos-silver-backfill-dedup"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.aparcamientos_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "aparcamientos_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-aparcamientos-silver-to-gold"
        name                      = "madrono-tfm-dev-aparcamientos-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.bicimad_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "bicimad_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-bicimad-bronze-to-silver"
        name                      = "madrono-tfm-dev-bicimad-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.bicimad_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "bicimad_silver_backfill_dedup" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-bicimad-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-bicimad-silver-backfill-dedup"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.bicimad_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "bicimad_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-bicimad-silver-to-gold"
        name                      = "madrono-tfm-dev-bicimad-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.bluesky_menciones_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "bluesky_menciones_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-bluesky-menciones-bronze-to-silver"
        name                      = "madrono-tfm-dev-bluesky-menciones-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.bluesky_menciones_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "bluesky_menciones_silver_backfill_dedup" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-bluesky-menciones-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-bluesky-menciones-silver-backfill-dedup"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.bluesky_menciones_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "bluesky_menciones_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-bluesky-menciones-silver-to-gold"
        name                      = "madrono-tfm-dev-bluesky-menciones-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_silver_to_gold-eebc2e82aa50cb399f022af861372782.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_silver_to_gold-261976e04868c0265f79a78dacffb6ed.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.calidad_aire_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "calidad_aire_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-calidad-aire-bronze-to-silver"
        name                      = "madrono-tfm-dev-calidad-aire-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.calidad_aire_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "calidad_aire_silver_backfill_dedup" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-calidad-aire-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-calidad-aire-silver-backfill-dedup"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.calidad_aire_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "calidad_aire_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-calidad-aire-silver-to-gold"
        name                      = "madrono-tfm-dev-calidad-aire-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.cams_calidad_aire_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "cams_calidad_aire_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-cams-calidad-aire-bronze-to-silver"
        name                      = "madrono-tfm-dev-cams-calidad-aire-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.cams_calidad_aire_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "cams_calidad_aire_silver_backfill_dedup" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-cams-calidad-aire-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-cams-calidad-aire-silver-backfill-dedup"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.cams_calidad_aire_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "cams_calidad_aire_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-cams-calidad-aire-silver-to-gold"
        name                      = "madrono-tfm-dev-cams-calidad-aire-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.cartelera_cines_estrenos_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "cartelera_cines_estrenos_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-cartelera-cines-estrenos-bronze-to-silver"
        name                      = "madrono-tfm-dev-cartelera-cines-estrenos-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.cartelera_cines_estrenos_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "cartelera_cines_estrenos_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-cartelera-cines-estrenos-silver-to-gold"
        name                      = "madrono-tfm-dev-cartelera-cines-estrenos-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

      ~ command {
            name            = "glueetl"
          ~ script_location = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cartelera_cines_estrenos_silver_to_gold-90a5785103ca4aa3ef331d91a67d2851.py" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cartelera_cines_estrenos_silver_to_gold-8d4592f5bf658249febbacc5cca7df26.py"
            # (2 unchanged attributes hidden)
        }

        # (1 unchanged block hidden)
    }

  # aws_glue_job.meteorologia_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "meteorologia_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-meteorologia-bronze-to-silver"
        name                      = "madrono-tfm-dev-meteorologia-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.meteorologia_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "meteorologia_silver_backfill_dedup" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-meteorologia-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-meteorologia-silver-backfill-dedup"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.meteorologia_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "meteorologia_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-meteorologia-silver-to-gold"
        name                      = "madrono-tfm-dev-meteorologia-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.ruido_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "ruido_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-ruido-bronze-to-silver"
        name                      = "madrono-tfm-dev-ruido-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.ruido_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "ruido_silver_backfill_dedup" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-ruido-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-ruido-silver-backfill-dedup"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.ruido_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "ruido_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-ruido-silver-to-gold"
        name                      = "madrono-tfm-dev-ruido-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.trafico_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "trafico_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-trafico-bronze-to-silver"
        name                      = "madrono-tfm-dev-trafico-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.trafico_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "trafico_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-trafico-silver-to-gold"
        name                      = "madrono-tfm-dev-trafico-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.transporte_publico_emt_bronze_to_silver will be updated in-place
  ~ resource "aws_glue_job" "transporte_publico_emt_bronze_to_silver" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-transporte-publico-emt-bronze-to-silver"
        name                      = "madrono-tfm-dev-transporte-publico-emt-bronze-to-silver"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.transporte_publico_emt_silver_backfill_dedup will be updated in-place
  ~ resource "aws_glue_job" "transporte_publico_emt_silver_backfill_dedup" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (9 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-transporte-publico-emt-silver-backfill-dedup"
        name                      = "madrono-tfm-dev-transporte-publico-emt-silver-backfill-dedup"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_glue_job.transporte_publico_emt_silver_to_gold will be updated in-place
  ~ resource "aws_glue_job" "transporte_publico_emt_silver_to_gold" {
      ~ default_arguments         = {
          ~ "--extra-py-files"                   = "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "s3://madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip"
            # (7 unchanged elements hidden)
        }
        id                        = "madrono-tfm-dev-transporte-publico-emt-silver-to-gold"
        name                      = "madrono-tfm-dev-transporte-publico-emt-silver-to-gold"
        tags                      = {}
        # (16 unchanged attributes hidden)

        # (2 unchanged blocks hidden)
    }

  # aws_iam_instance_profile.kafka will be created
  + resource "aws_iam_instance_profile" "kafka" {
      + arn         = (known after apply)
      + create_date = (known after apply)
      + id          = (known after apply)
      + name        = "madrono-tfm-dev-kafka-profile"
      + name_prefix = (known after apply)
      + path        = "/"
      + role        = "madrono-tfm-dev-kafka-role"
      + tags_all    = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + unique_id   = (known after apply)
    }

  # aws_iam_policy.scheduler_invoke_lambda will be updated in-place
  ~ resource "aws_iam_policy" "scheduler_invoke_lambda" {
        id               = "arn:aws:iam::222234418587:policy/madrono-tfm-dev-scheduler-invoke-lambda"
        name             = "madrono-tfm-dev-scheduler-invoke-lambda"
      ~ policy           = jsonencode(
            {
              - Statement = [
                  - {
                      - Action   = "lambda:InvokeFunction"
                      - Effect   = "Allow"
                      - Resource = [
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-transporte_publico_emt",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-trafico",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-ruido",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-meteorologia",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-cartelera_cines_estrenos",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-cams_calidad_aire",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-calidad_aire",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-bluesky_menciones",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-bicimad",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aparcamientos",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-agenda_eventos",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aforos_peatones_bicicletas",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-afluencia_lugares",
                          - "arn:aws:lambda:eu-west-1:222234418587:function:madrono-tfm-dev-aemet_prevision_avisos",
                        ]
                      - Sid      = "InvokeProducerLambdas"
                    },
                ]
              - Version   = "2012-10-17"
            }
        ) -> (known after apply)
        tags             = {}
        # (7 unchanged attributes hidden)
    }

  # aws_iam_role.kafka will be created
  + resource "aws_iam_role" "kafka" {
      + arn                   = (known after apply)
      + assume_role_policy    = jsonencode(
            {
              + Statement = [
                  + {
                      + Action    = "sts:AssumeRole"
                      + Effect    = "Allow"
                      + Principal = {
                          + Service = "ec2.amazonaws.com"
                        }
                    },
                ]
              + Version   = "2012-10-17"
            }
        )
      + create_date           = (known after apply)
      + description           = "Rol de la instancia EC2 de Kafka: únicamente SSM Session Manager para gestión sin SSH (tarea 042)."
      + force_detach_policies = false
      + id                    = (known after apply)
      + managed_policy_arns   = (known after apply)
      + max_session_duration  = 3600
      + name                  = "madrono-tfm-dev-kafka-role"
      + name_prefix           = (known after apply)
      + path                  = "/"
      + tags_all              = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + unique_id             = (known after apply)

      + inline_policy (known after apply)
    }

  # aws_iam_role_policy_attachment.kafka_ssm will be created
  + resource "aws_iam_role_policy_attachment" "kafka_ssm" {
      + id         = (known after apply)
      + policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
      + role       = "madrono-tfm-dev-kafka-role"
    }

  # aws_instance.kafka will be created
  + resource "aws_instance" "kafka" {
      + ami                                  = (sensitive value)
      + arn                                  = (known after apply)
      + associate_public_ip_address          = true
      + availability_zone                    = (known after apply)
      + cpu_core_count                       = (known after apply)
      + cpu_threads_per_core                 = (known after apply)
      + disable_api_stop                     = (known after apply)
      + disable_api_termination              = (known after apply)
      + ebs_optimized                        = (known after apply)
      + enable_primary_ipv6                  = (known after apply)
      + get_password_data                    = false
      + host_id                              = (known after apply)
      + host_resource_group_arn              = (known after apply)
      + iam_instance_profile                 = "madrono-tfm-dev-kafka-profile"
      + id                                   = (known after apply)
      + instance_initiated_shutdown_behavior = (known after apply)
      + instance_lifecycle                   = (known after apply)
      + instance_state                       = (known after apply)
      + instance_type                        = "t3.small"
      + ipv6_address_count                   = (known after apply)
      + ipv6_addresses                       = (known after apply)
      + key_name                             = (known after apply)
      + monitoring                           = (known after apply)
      + outpost_arn                          = (known after apply)
      + password_data                        = (known after apply)
      + placement_group                      = (known after apply)
      + placement_partition_number           = (known after apply)
      + primary_network_interface_id         = (known after apply)
      + private_dns                          = (known after apply)
      + private_ip                           = (known after apply)
      + public_dns                           = (known after apply)
      + public_ip                            = (known after apply)
      + secondary_private_ips                = (known after apply)
      + security_groups                      = (known after apply)
      + source_dest_check                    = true
      + spot_instance_request_id             = (known after apply)
      + subnet_id                            = "subnet-0032ab061e3e642f2"
      + tags                                 = {
          + "Name" = "madrono-tfm-dev-kafka"
        }
      + tags_all                             = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Name"        = "madrono-tfm-dev-kafka"
          + "Project"     = "madrono-tfm"
        }
      + tenancy                              = (known after apply)
      + user_data                            = "5f253a10aac9ac8ad98e273e6d49d1cb38206476"
      + user_data_base64                     = (known after apply)
      + user_data_replace_on_change          = false
      + vpc_security_group_ids               = (known after apply)

      + capacity_reservation_specification (known after apply)

      + cpu_options (known after apply)

      + ebs_block_device (known after apply)

      + enclave_options (known after apply)

      + ephemeral_block_device (known after apply)

      + instance_market_options (known after apply)

      + maintenance_options (known after apply)

      + metadata_options (known after apply)

      + network_interface (known after apply)

      + private_dns_name_options (known after apply)

      + root_block_device {
          + delete_on_termination = true
          + device_name           = (known after apply)
          + encrypted             = true
          + iops                  = (known after apply)
          + kms_key_id            = (known after apply)
          + tags_all              = (known after apply)
          + throughput            = (known after apply)
          + volume_id             = (known after apply)
          + volume_size           = 20
          + volume_type           = "gp3"
        }
    }

  # aws_lambda_function.producer["aemet_prevision_avisos"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-aemet_prevision_avisos"
      ~ last_modified                  = "2026-08-15T17:45:41.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["afluencia_lugares"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-afluencia_lugares"
      ~ last_modified                  = "2026-08-15T17:45:29.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["aforos_peatones_bicicletas"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-aforos_peatones_bicicletas"
      ~ last_modified                  = "2026-08-15T17:45:53.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["agenda_eventos"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-agenda_eventos"
      ~ last_modified                  = "2026-08-15T17:45:59.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["aparcamientos"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-aparcamientos"
      ~ last_modified                  = "2026-08-15T17:46:10.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["bicimad"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-bicimad"
      ~ last_modified                  = "2026-08-15T17:46:05.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["bluesky_menciones"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-bluesky_menciones"
      ~ last_modified                  = "2026-08-15T17:45:17.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["calidad_aire"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-calidad_aire"
      ~ last_modified                  = "2026-08-15T17:45:23.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["cams_calidad_aire"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-cams_calidad_aire"
      ~ last_modified                  = "2026-08-16T00:25:07.000+0000" -> (known after apply)
      ~ source_code_hash               = "d7EQu1dgphlitciVE2HTKx/chix5s+vz4rA/a0fWr+Q=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["cartelera_cines_estrenos"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-cartelera_cines_estrenos"
      ~ last_modified                  = "2026-08-26T09:37:40.000+0000" -> (known after apply)
      ~ source_code_hash               = "iFA3hTAEzlyHs/yNtT2hFZEt5iaLCbwxJsQYpLBYbso=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["meteorologia"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-meteorologia"
      ~ last_modified                  = "2026-08-15T17:44:59.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["ruido"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-ruido"
      ~ last_modified                  = "2026-08-15T17:45:11.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["trafico"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-trafico"
      ~ last_modified                  = "2026-08-15T17:46:16.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["transporte_publico_emt"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-transporte_publico_emt"
      ~ last_modified                  = "2026-08-15T17:45:05.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "N3y0pi3hWwmaFD3VRSrfwetxbzXgCksOeJ5Ph5uCYrw="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_s3_object.glue_script_aforos_peatones_bicicletas_silver_to_gold must be replaced
-/+ resource "aws_s3_object" "glue_script_aforos_peatones_bicicletas_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/aforos_peatones_bicicletas_silver_to_gold-1ed5acbc05f8bc8dc8c53eae4e789893.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
            """Job de AWS Glue: Silver -> Gold del dataset `aforos_peatones_bicicletas`
            (conteo total/medio por estación, modo y hora).
            
            **No ejecutado en esta tarea** (mismas condiciones que
            `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
            disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
            
            A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
            `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
            través de múltiples particiones/ficheros de Silver necesita las primitivas
            nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
            mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
            siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
            expresiones de Spark de este job están escritas para producir exactamente el
            mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
            en uno debe reflejarse en el otro.
            
            Parámetros del job (`--<nombre>`, ver `glue.tf`):
            
            - `JOB_NAME`: nombre del job (estándar de Glue).
            - `silver_path`: prefijo S3 de origen, p.ej.
              `s3://madrono-tfm-dev-silver-222234418587/aforos_peatones_bicicletas/`.
            - `gold_path`: prefijo S3 de destino, p.ej.
              `s3://madrono-tfm-dev-gold-222234418587/aforos_peatones_bicicletas_por_estacion_modo_hora/`.
            """
            
            from __future__ import annotations
            
            import sys
            from datetime import datetime
            from zoneinfo import ZoneInfo
            
            import boto3
            from awsglue.context import GlueContext
            from awsglue.job import Job
            from awsglue.utils import getResolvedOptions
            from pyspark.context import SparkContext
            from pyspark.sql import SparkSession
            from pyspark.sql import functions as F
            
            from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
            
            MADRID_TZ = ZoneInfo("Europe/Madrid")
            
            
            def main() -> None:
                args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
            
                sc = SparkContext()
                glue_context = GlueContext(sc)
                spark: SparkSession = glue_context.spark_session
                # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
                # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
                # desalineado con `today()` (Python, Europe/Madrid).
                spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
                job = Job(glue_context)
                job.init(args["JOB_NAME"], args)
            
                processed_at = datetime.now(MADRID_TZ)
            
                # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
                # nunca la raiz completa del dataset -- mismo motivo de coste que
                # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio conteo
                # (`measured_at`, ver glue_bronze_to_silver.py), que coincide con el dia
                # de ingestion para este dataset (conteos casi en tiempo real, sin
                # horizonte futuro) -- cada particion `fecha=<dia>` se visita una unica
                # vez, el dia en que ese dia es "hoy".
                fecha = today(processed_at)
                silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
                if not partition_has_objects(boto3.client("s3"), silver_partition_path):
                    job.commit()
                    return
            
          -     silver_df = spark.read.parquet(silver_partition_path)
          +     # `hora` sí se infiere como columna de partición física (es el nivel
          +     # inmediato bajo la ruta leída), pero `fecha` no -- al acotar la lectura
          +     # a `fecha=<fecha>/` (tarea 076) esa partición queda fija en la propia
          +     # ruta y Spark deja de exponerla como columna, igual que
          +     # `aparcamientos_silver_to_gold.py` (tarea 072). Se añade de vuelta con
          +     # el valor ya conocido en vez de asumir que Spark la habría inferido --
          +     # mismo bug real que `cartelera_cines_estrenos_silver_to_gold.py`
          +     # (`AnalysisException: Column 'fecha' does not exist`), encontrado y
          +     # corregido en la tarea 090 en los 3 jobs del patrón que lo tenían
          +     # latente; este en concreto no había fallado aún en producción porque la
          +     # fuente de `aforos_peatones_bicicletas` está descontinuada desde
          +     # 2026-06-30 (ver doc/087) y `partition_has_objects` nunca deja pasar
          +     # ninguna ejecución real hasta aquí.
          +     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
            
          -     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          -     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
          -     # partition pruning si `silver_path` acota un rango de fechas concreto.
                # `mode` entra en la clave de agrupación (mismo criterio que `pollutant`
                # en `calidad_aire`/`magnitude` en `meteorologia`): peatones y bicicletas
                # se miden en redes de estaciones distintas, ver docstring de
                # `aggregate.py`.
                gold_df = (
                    silver_df.groupBy("station_id", "mode", "fecha", "hora")
                    .agg(
                        F.count(F.lit(1)).alias("samples_count"),
                        F.first("district_code", ignorenulls=True).alias("district_code"),
                        F.first("district", ignorenulls=True).alias("district"),
                        F.first("address", ignorenulls=True).alias("address"),
                        F.first("address_notes", ignorenulls=True).alias("address_notes"),
                        F.min("measured_at").alias("first_measured_at"),
                        F.max("measured_at").alias("last_measured_at"),
                        F.sum("count").alias("total_count"),
                        F.avg("count").alias("avg_count"),
                        F.max("count").alias("max_count"),
                        F.min("count").alias("min_count"),
                        F.first("location.lat", ignorenulls=True).alias("lat"),
                        F.first("location.lon", ignorenulls=True).alias("lon"),
                    )
                    .withColumnRenamed("fecha", "date")
                    .withColumn("hour", F.col("hora").cast("int"))
                    .drop("hora")
                    .withColumn("schema_version", F.lit(1))
                    .withColumn("processed_at", F.lit(processed_at.isoformat()))
                )
            
                # Gold es órdenes de magnitud más pequeño que Silver (una fila por
                # estación, modo y hora, no cada ~5 minutos): particionar solo por
                # `date` es suficiente para podar particiones sin generar ficheros
                # diminutos.
                gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
            
                job.commit()
            
            
            if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "a7df88f8aa89cea895c3e594ff738600" -> "98ae6a2fa1ca9fc05b6451aaffbd690b"
      ~ id                            = "glue-scripts/aforos_peatones_bicicletas_silver_to_gold-1ed5acbc05f8bc8dc8c53eae4e789893.py" -> (known after apply)
      ~ key                           = "glue-scripts/aforos_peatones_bicicletas_silver_to_gold-1ed5acbc05f8bc8dc8c53eae4e789893.py" -> "glue-scripts/aforos_peatones_bicicletas_silver_to_gold-98ae6a2fa1ca9fc05b6451aaffbd690b.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      ~ tags_all                      = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + version_id                    = (known after apply)
        # (10 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_agenda_eventos_silver_to_gold must be replaced
-/+ resource "aws_s3_object" "glue_script_agenda_eventos_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/agenda_eventos_silver_to_gold-73b5e533d9966653fcd6f2597254ba59.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
            """Job de AWS Glue: Silver -> Gold del dataset `agenda_eventos` (número de
            eventos por categoría, distrito y día de celebración).
            
            **No ejecutado en esta tarea** (mismas condiciones que
            `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
            disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
            
            A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
            `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
            través de múltiples particiones/ficheros de Silver necesita las primitivas
            nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
            mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
            siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
            expresiones de Spark de este job están escritas para producir exactamente el
            mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
            en uno debe reflejarse en el otro.
            
            Parámetros del job (`--<nombre>`, ver `glue.tf`):
            
            - `JOB_NAME`: nombre del job (estándar de Glue).
            - `silver_path`: prefijo S3 de origen, p.ej.
              `s3://madrono-tfm-dev-silver-222234418587/agenda_eventos/`.
            - `gold_path`: prefijo S3 de destino, p.ej.
              `s3://madrono-tfm-dev-gold-222234418587/agenda_eventos_por_categoria_distrito_fecha/`.
            """
            
            from __future__ import annotations
            
            import sys
            from datetime import datetime
            from zoneinfo import ZoneInfo
            
            import boto3
            from awsglue.context import GlueContext
            from awsglue.job import Job
            from awsglue.utils import getResolvedOptions
            from pyspark.context import SparkContext
            from pyspark.sql import SparkSession
            from pyspark.sql import functions as F
            
            from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
            
            MADRID_TZ = ZoneInfo("Europe/Madrid")
            
            UNKNOWN_CATEGORY = "__sin_categoria__"
            UNKNOWN_DISTRICT = "__sin_distrito__"
            
            
            def main() -> None:
                args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
            
                sc = SparkContext()
                glue_context = GlueContext(sc)
                spark: SparkSession = glue_context.spark_session
                # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
                # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
                # desalineado con `today()` (Python, Europe/Madrid).
                spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
                job = Job(glue_context)
                job.init(args["JOB_NAME"], args)
            
                processed_at = datetime.now(MADRID_TZ)
            
                # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
                # nunca la raiz completa del dataset -- mismo motivo de coste que
                # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio evento
                # (`start_datetime`), que puede ser semanas/meses en el futuro respecto
                # al dia de ingestion (agenda cultural real: eventos publicados con
                # mucha antelacion, ver muestra real de `agenda_eventos_madrid_sample.json`
                # con fechas de fin hasta 2027) -- no la de ingestion. Silver es un
                # almacen persistente: cada particion `fecha=<dia>` recibe escrituras de
                # muchos dias de ingestion distintos mientras el evento sigue vigente en
                # la fuente, pero esta lectura visita esa particion una unica vez, el
                # dia en que ese dia de calendario se convierte en "hoy" -- momento en
                # el que ya contiene todo lo que se llegó a capturar de ese evento.
                fecha = today(processed_at)
                silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
                if not partition_has_objects(boto3.client("s3"), silver_partition_path):
                    job.commit()
                    return
            
          -     silver_df = spark.read.parquet(silver_partition_path)
          +     # `fecha` es columna de partición física de Silver (derivada de
          +     # `start_datetime`, ver glue_bronze_to_silver.py), pero al acotar la
          +     # lectura a una única partición `fecha=<fecha>/` (tarea 076) Spark deja
          +     # de inferirla como columna -- esa partición queda fija en la propia
          +     # ruta leída. Se añade de vuelta con el valor ya conocido -- bug real
          +     # (`AnalysisException: Column 'fecha' does not exist`) que llevaba
          +     # fallando en producción todos los días desde el 2026-08-23 (ver
          +     # historial real de `madrono-tfm-dev-agenda-eventos-silver-to-gold`),
          +     # encontrado y corregido en la tarea 090 junto con el mismo bug en
          +     # `cartelera_cines_estrenos`/`aforos_peatones_bicicletas`.
          +     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
            
                # `category`/`district` ausentes se agrupan bajo un sentinela en vez de
                # descartarse -- mismo criterio que `aggregate.py` (ver docstring de ese
                # módulo).
                normalized_df = silver_df.withColumn(
                    "category_key", F.coalesce(F.col("category"), F.lit(UNKNOWN_CATEGORY))
                ).withColumn("district_key", F.coalesce(F.col("district"), F.lit(UNKNOWN_DISTRICT)))
          - 
          -     # `fecha` ya es una columna de partición física de Silver (derivada de
          -     # `start_datetime`, ver glue_bronze_to_silver.py); agrupar por ella
          -     # permite a Spark aprovechar partition pruning si `silver_path` acota un
          -     # rango de fechas concreto.
                gold_df = (
                    normalized_df.groupBy("category_key", "district_key", "fecha")
                    .agg(
                        F.count(F.lit(1)).alias("samples_count"),
                        F.countDistinct("event_id").alias("events_count"),
                        F.countDistinct(F.when(F.col("free") == True, F.col("event_id"))).alias(  # noqa: E712
                            "free_events_count"
                        ),
                        F.sort_array(F.collect_set("source")).alias("sources"),
                        F.min("start_datetime").alias("first_start_datetime"),
                        F.max("start_datetime").alias("last_start_datetime"),
                    )
                    .withColumnRenamed("category_key", "category")
                    .withColumnRenamed("district_key", "district")
                    .withColumnRenamed("fecha", "date")
                    .withColumn("schema_version", F.lit(1))
                    .withColumn("processed_at", F.lit(processed_at.isoformat()))
                )
            
                # Gold es órdenes de magnitud más pequeño que Silver (una fila por
                # categoría, distrito y día, no una por evento): particionar solo por
                # `date` es suficiente para podar particiones sin generar ficheros
                # diminutos.
                gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
            
                job.commit()
            
            
            if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "4d854fda4df74abc055b9eba9af92b0f" -> "7ed6c1455ead3aef19f9e40b96c23a51"
      ~ id                            = "glue-scripts/agenda_eventos_silver_to_gold-73b5e533d9966653fcd6f2597254ba59.py" -> (known after apply)
      ~ key                           = "glue-scripts/agenda_eventos_silver_to_gold-73b5e533d9966653fcd6f2597254ba59.py" -> "glue-scripts/agenda_eventos_silver_to_gold-7ed6c1455ead3aef19f9e40b96c23a51.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      ~ tags_all                      = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + version_id                    = (known after apply)
        # (10 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_bluesky_menciones_silver_to_gold must be replaced
-/+ resource "aws_s3_object" "glue_script_bluesky_menciones_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/bluesky_menciones_silver_to_gold-eebc2e82aa50cb399f022af861372782.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
            """Job de AWS Glue: Silver -> Gold del dataset `bluesky_menciones` (número de
            menciones por término de búsqueda, modo, día y hora).
            
            **No ejecutado en esta tarea** (mismas condiciones que
            `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
            disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
            
            A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
            `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
            través de múltiples particiones/ficheros de Silver necesita las primitivas
            nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
            mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
            siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
            expresiones de Spark de este job están escritas para producir exactamente el
            mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
            en uno debe reflejarse en el otro.
            
            Parámetros del job (`--<nombre>`, ver `glue.tf`):
            
            - `JOB_NAME`: nombre del job (estándar de Glue).
            - `silver_path`: prefijo S3 de origen, p.ej.
              `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
            - `gold_path`: prefijo S3 de destino, p.ej.
              `s3://madrono-tfm-dev-gold-222234418587/bluesky_menciones_por_termino_modo_hora/`.
            """
            
            from __future__ import annotations
            
            import sys
            from datetime import datetime
            from zoneinfo import ZoneInfo
            
            import boto3
            from awsglue.context import GlueContext
            from awsglue.job import Job
            from awsglue.utils import getResolvedOptions
            from pyspark.context import SparkContext
            from pyspark.sql import SparkSession
            from pyspark.sql import functions as F
            
            from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
            
            MADRID_TZ = ZoneInfo("Europe/Madrid")
            
            
            def main() -> None:
                args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
            
                sc = SparkContext()
                glue_context = GlueContext(sc)
                spark: SparkSession = glue_context.spark_session
                # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
                # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
                # desalineado con `today()` (Python, Europe/Madrid).
                spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
                job = Job(glue_context)
                job.init(args["JOB_NAME"], args)
            
                processed_at = datetime.now(MADRID_TZ)
            
                # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
                # nunca la raiz completa del dataset -- mismo motivo de coste que
                # Bronze->Silver (tarea 072). `fecha` en Silver es la de publicacion del
                # post (`created_at`, ver glue_bronze_to_silver.py), que coincide con el
                # dia de ingestion para este dataset (barrido casi en tiempo real, sin
                # horizonte futuro) -- cada particion `fecha=<dia>` se visita una unica
                # vez, el dia en que ese dia es "hoy".
                fecha = today(processed_at)
                silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
                if not partition_has_objects(boto3.client("s3"), silver_partition_path):
                    job.commit()
                    return
            
          -     silver_df = spark.read.parquet(silver_partition_path)
          +     # `hora` sí se infiere como columna de partición física (nivel inmediato
          +     # bajo la ruta leída), pero `fecha` no -- al acotar la lectura a
          +     # `fecha=<fecha>/` (tarea 076) esa partición queda fija en la ruta y
          +     # Spark deja de exponerla como columna. Se añade de vuelta con el valor
          +     # ya conocido -- bug real (`AnalysisException: Column 'fecha' does not
          +     # exist`) que ya había fallado en producción los días 2026-08-23 y
          +     # 2026-08-24 (ver historial real de
          +     # `madrono-tfm-dev-bluesky-menciones-silver-to-gold`; los días en que el
          +     # job "tuvo éxito" fue porque `partition_has_objects` cortó antes de
          +     # llegar aquí, no porque el `groupBy` funcionara), encontrado y
          +     # corregido en la tarea 090 junto con el mismo bug en
          +     # `cartelera_cines_estrenos`/`agenda_eventos`/`aforos_peatones_bicicletas`.
          +     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
            
          -     # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
          -     # glue_bronze_to_silver.py); agrupar por ellas permite a Spark
          -     # aprovechar partition pruning si `silver_path` acota un rango de
          -     # fechas concreto. `mode`/`match_term` entran en la clave junto a
          -     # `fecha`/`hora` -- mismo criterio que `aggregate.py`.
          +     # `mode`/`match_term` entran en la clave junto a `fecha`/`hora` -- mismo
          +     # criterio que `aggregate.py`.
                gold_df = (
                    silver_df.groupBy("mode", "match_term", "fecha", "hora")
                    .agg(
                        F.count(F.lit(1)).alias("samples_count"),
                        F.countDistinct("post_hash").alias("mentions_count"),
                        F.sort_array(F.collect_set("lang")).alias("langs"),
                        F.coalesce(F.sum("like_count"), F.lit(0)).alias("total_like_count"),
                        F.coalesce(F.sum("repost_count"), F.lit(0)).alias("total_repost_count"),
                        F.coalesce(F.sum("reply_count"), F.lit(0)).alias("total_reply_count"),
                        F.coalesce(F.sum("quote_count"), F.lit(0)).alias("total_quote_count"),
                        F.min("created_at").alias("first_created_at"),
                        F.max("created_at").alias("last_created_at"),
                    )
                    .withColumnRenamed("fecha", "date")
                    .withColumn("hour", F.col("hora").cast("int"))
                    .drop("hora")
                    .withColumn("schema_version", F.lit(1))
                    .withColumn("processed_at", F.lit(processed_at.isoformat()))
                )
            
                # Gold es órdenes de magnitud más pequeño que Silver (una fila por
                # término/modo/hora, no una por post): particionar solo por `date` es
                # suficiente para podar particiones sin generar ficheros diminutos --
                # mismo criterio que el resto del patrón (trafico, cartelera_cines_estrenos...).
                gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
            
                job.commit()
            
            
            if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "8c43f4a9df541e2eea43a8456514dc10" -> "261976e04868c0265f79a78dacffb6ed"
      ~ id                            = "glue-scripts/bluesky_menciones_silver_to_gold-eebc2e82aa50cb399f022af861372782.py" -> (known after apply)
      ~ key                           = "glue-scripts/bluesky_menciones_silver_to_gold-eebc2e82aa50cb399f022af861372782.py" -> "glue-scripts/bluesky_menciones_silver_to_gold-261976e04868c0265f79a78dacffb6ed.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      ~ tags_all                      = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + version_id                    = (known after apply)
        # (10 unchanged attributes hidden)
    }

  # aws_s3_object.glue_script_cartelera_cines_estrenos_silver_to_gold must be replaced
-/+ resource "aws_s3_object" "glue_script_cartelera_cines_estrenos_silver_to_gold" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-scripts/cartelera_cines_estrenos_silver_to_gold-90a5785103ca4aa3ef331d91a67d2851.py" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content                       = <<-EOT
            """Job de AWS Glue: Silver -> Gold del dataset `cartelera_cines_estrenos`
            (número de sesiones por película, cine y día).
            
            **No ejecutado en esta tarea** (mismas condiciones que
            `glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
            disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).
            
            A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
            `aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
            través de múltiples particiones/ficheros de Silver necesita las primitivas
            nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
            mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
            siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
            expresiones de Spark de este job están escritas para producir exactamente el
            mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
            en uno debe reflejarse en el otro.
            
            Parámetros del job (`--<nombre>`, ver `glue.tf`):
            
            - `JOB_NAME`: nombre del job (estándar de Glue).
            - `silver_path`: prefijo S3 de origen, p.ej.
              `s3://madrono-tfm-dev-silver-222234418587/cartelera_cines_estrenos/`.
            - `gold_path`: prefijo S3 de destino, p.ej.
              `s3://madrono-tfm-dev-gold-222234418587/cartelera_cines_estrenos_por_pelicula_cine_fecha/`.
            """
            
            from __future__ import annotations
            
            import sys
            from datetime import datetime
            from zoneinfo import ZoneInfo
            
            import boto3
            from awsglue.context import GlueContext
            from awsglue.job import Job
            from awsglue.utils import getResolvedOptions
            from pyspark.context import SparkContext
            from pyspark.sql import SparkSession
            from pyspark.sql import functions as F
            
            from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today
            
            MADRID_TZ = ZoneInfo("Europe/Madrid")
            
            
            def main() -> None:
                args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])
            
                sc = SparkContext()
                glue_context = GlueContext(sc)
                spark: SparkSession = glue_context.spark_session
                # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
                # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
                # desalineado con `today()` (Python, Europe/Madrid).
                spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
                job = Job(glue_context)
                job.init(args["JOB_NAME"], args)
            
                processed_at = datetime.now(MADRID_TZ)
            
                # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
                # nunca la raiz completa del dataset -- mismo motivo de coste que
                # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio dia de
                # la sesion (`showtime_datetime`), no la de ingestion (ver
                # glue_bronze_to_silver.py) -- pero por como funciona realmente
                # SensaCine (la cartelera scrapeada es de sesiones de hoy/muy cercanas,
                # ver "showtime_already_passed" en transform.py, nunca semanas vista),
                # cada particion `fecha=<dia>` recibe practicamente todos sus datos el
                # mismo dia (o el dia anterior), y esta lectura la visita el dia en que
                # ese dia es "hoy" -- si alguna sesion quedase en una particion futura no
                # visitada aun, se recogeria igual cuando esa particion se convierta en
                # "hoy" (Silver es un almacen persistente, no se borra entre
                # ejecuciones).
                fecha = today(processed_at)
                silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
                if not partition_has_objects(boto3.client("s3"), silver_partition_path):
                    job.commit()
                    return
            
          -     silver_df = spark.read.parquet(silver_partition_path)
          +     # `fecha` es columna de partición física de Silver (ver
          +     # glue_bronze_to_silver.py), pero al acotar la lectura a una única
          +     # partición `fecha=<fecha>/` (tarea 076, lectura incremental) Spark deja
          +     # de inferirla como columna -- solo `hora=` varía bajo esa ruta, mismo
          +     # motivo por el que `aparcamientos_silver_to_gold.py` recalcula sus
          +     # columnas de partición tras acotar la lectura (tarea 072). Se añade de
          +     # vuelta con el valor ya conocido (`fecha`, calculado arriba) en vez de
          +     # asumir que Spark la habría inferido -- bug real encontrado en la
          +     # verificación contra datos reales de la tarea 090 (`AnalysisException:
          +     # Column 'fecha' does not exist`).
          +     silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))
            
          -     # `fecha` ya es una columna de partición física de Silver (ver
          -     # glue_bronze_to_silver.py); agrupar por ella permite a Spark aprovechar
          -     # partition pruning si `silver_path` acota un rango de fechas concreto.
                # `movie_url`/`cinema_id` entran en la clave de agrupación junto a
                # `fecha` (mismo criterio que `aggregate.py`: incluir ambas dimensiones
                # deja disponibles tanto la vista "por película" como "por cine" sin
                # perder información en la propia agregación de Gold).
                gold_df = (
                    silver_df.groupBy("movie_url", "cinema_id", "fecha")
                    .agg(
                        F.count(F.lit(1)).alias("samples_count"),
                        F.countDistinct("showtime_id").alias("sessions_count"),
                        F.first("movie_title", ignorenulls=True).alias("movie_title"),
                        F.first("chain", ignorenulls=True).alias("chain"),
                        F.first("cinema_name", ignorenulls=True).alias("cinema_name"),
                        F.first("address", ignorenulls=True).alias("address"),
                        F.first("postal_code", ignorenulls=True).alias("postal_code"),
                        F.first("locality", ignorenulls=True).alias("locality"),
                        F.min("showtime_datetime").alias("first_showtime_datetime"),
                        F.max("showtime_datetime").alias("last_showtime_datetime"),
                        F.sort_array(F.collect_set("language_version")).alias("language_versions"),
                    )
                    .withColumnRenamed("fecha", "date")
                    .withColumn("schema_version", F.lit(1))
                    .withColumn("processed_at", F.lit(processed_at.isoformat()))
                )
            
                # Gold es órdenes de magnitud más pequeño que Silver (una fila por
                # película, cine y día, no una por sesión): particionar solo por `date`
                # es suficiente para podar particiones sin generar ficheros diminutos.
                gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])
            
                job.commit()
            
            
            if __name__ == "__main__":
                main()
        EOT
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "aa6c09b63c18f746da024c09a020b01f" -> "8d4592f5bf658249febbacc5cca7df26"
      ~ id                            = "glue-scripts/cartelera_cines_estrenos_silver_to_gold-90a5785103ca4aa3ef331d91a67d2851.py" -> (known after apply)
      ~ key                           = "glue-scripts/cartelera_cines_estrenos_silver_to_gold-90a5785103ca4aa3ef331d91a67d2851.py" -> "glue-scripts/cartelera_cines_estrenos_silver_to_gold-8d4592f5bf658249febbacc5cca7df26.py" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      ~ tags_all                      = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + version_id                    = (known after apply)
        # (10 unchanged attributes hidden)
    }

  # aws_s3_object.procesamiento_source must be replaced
-/+ resource "aws_s3_object" "procesamiento_source" {
      + acl                           = (known after apply)
      ~ arn                           = "arn:aws:s3:::madrono-tfm-dev-build-artifacts-222234418587/glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> (known after apply)
      ~ bucket_key_enabled            = false -> (known after apply)
      + checksum_crc32                = (known after apply)
      + checksum_crc32c               = (known after apply)
      + checksum_crc64nvme            = (known after apply)
      + checksum_sha1                 = (known after apply)
      + checksum_sha256               = (known after apply)
      ~ content_type                  = "application/octet-stream" -> (known after apply)
      ~ etag                          = "41c225d658b2c0460396d681d7ef0062" -> "6b73c9ac8ba8143845e9f8429ed0b4ce"
      ~ id                            = "glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> (known after apply)
      ~ key                           = "glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip" -> "glue-libs/procesamiento-6b73c9ac8ba8143845e9f8429ed0b4ce.zip" # forces replacement
      + kms_key_id                    = (known after apply)
      - metadata                      = {} -> null
      ~ server_side_encryption        = "AES256" -> (known after apply)
      ~ storage_class                 = "STANDARD" -> (known after apply)
      - tags                          = {} -> null
      + version_id                    = (known after apply)
        # (12 unchanged attributes hidden)
    }

  # aws_security_group.kafka will be created
  + resource "aws_security_group" "kafka" {
      + arn                    = (known after apply)
      + description            = "Kafka de madrono-tfm-dev-kafka: puerto de cliente solo desde la VPC, sin SSH (gestion via SSM). Tarea 042."
      + egress                 = [
          + {
              + cidr_blocks      = [
                  + "0.0.0.0/0",
                ]
              + description      = "Salida abierta: instalacion de paquetes/descarga del binario de Kafka y endpoints publicos del agente SSM."
              + from_port        = 0
              + ipv6_cidr_blocks = []
              + prefix_list_ids  = []
              + protocol         = "-1"
              + security_groups  = []
              + self             = false
              + to_port          = 0
            },
        ]
      + id                     = (known after apply)
      + ingress                = [
          + {
              + cidr_blocks      = [
                  + "172.31.0.0/16",
                ]
              + description      = "Puerto de cliente Kafka (PLAINTEXT), solo desde dentro de la VPC."
              + from_port        = 9092
              + ipv6_cidr_blocks = []
              + prefix_list_ids  = []
              + protocol         = "tcp"
              + security_groups  = []
              + self             = false
              + to_port          = 9092
            },
        ]
      + name                   = "madrono-tfm-dev-kafka-sg"
      + name_prefix            = (known after apply)
      + owner_id               = (known after apply)
      + revoke_rules_on_delete = false
      + tags                   = {
          + "Name" = "madrono-tfm-dev-kafka-sg"
        }
      + tags_all               = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Name"        = "madrono-tfm-dev-kafka-sg"
          + "Project"     = "madrono-tfm"
        }
      + vpc_id                 = "vpc-0cd0f252bd38d9edf"
    }

Plan: 10 to add, 55 to change, 5 to destroy.

Changes to Outputs:
  + kafka_instance_id                      = (known after apply)
  + kafka_instance_private_ip              = (known after apply)
  + kafka_security_group_id                = (known after apply)

─────────────────────────────────────────────────────────────────────────────

Saved the plan to: /tmp/plan093.tfplan

To perform exactly these actions, run the following command to apply:
    terraform apply "/tmp/plan093.tfplan"
```

El fichero de plan binario (`/tmp/plan093.tfplan`) es un artefacto local efímero de esta
sesión (gitignored, `*.tfplan`), no se ha commiteado ni persiste — la tarea de "apply"
debe generar su propio `terraform plan` antes de `apply`, no reutilizar este.
