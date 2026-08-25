# 088 — `terraform plan` completo del drift real, sin aplicar nada

**Tarea deliberadamente de solo lectura** (`allow_infra_apply: false`, prioridad 1 de
`NEXT_STEPS.md`, decisión ya tomada el 25/8 tras `doc/083-investigacion-google-maps-arquitectura.md`).
Sigue el patrón de dos tareas que exige `tasks/README.md` para cambios de Terraform: esta
solo prepara y muestra el `plan`; una tarea posterior, creada aparte y solo después de que
un humano revise este documento, es la que aplicará.

## Resultado: el plan sin acotar completó limpio, sin necesitar ningún cambio de código

```
Plan: 5 to add, 15 to change, 0 to destroy.
```

Cero errores, cero recursos destruidos, cero reemplazos (`forces replacement`). El plan
completo y literal (`terraform plan` sin `-target`, con refresh completo del estado real)
queda volcado íntegro más abajo.

## Hallazgo 1 (invalida un supuesto de `doc/083`/`NEXT_STEPS.md`): el rol del deployer no está en el código Terraform de este repo

El punto 1 del alcance de esta tarea pedía "añade `codebuild:BatchGetProjects` a la
política IAM de `madrono-terraform-deployer` **en el código Terraform**
(`infra/terraform/`)". Se comprobó primero si tal recurso existe:

```
$ grep -n 'resource "aws_iam_role"' infra/terraform/*.tf
# 18 roles definidos -- todos de aplicación (glue_*, scheduler, ingestion, kafka,
# athena_query, lambda_layer_codebuild) -- ninguno es el rol de despliegue.
```

**El rol real es `madrono-terraform-deployerEC2`** (confirmado con
`aws sts get-caller-identity`, que devuelve
`arn:aws:sts::222234418587:assumed-role/madrono-terraform-deployerEC2/...` como identidad
de esta propia sesión) — y **no está definido en ningún fichero `.tf` de este repositorio**.
Es el rol de instancia EC2 creado a mano, fuera de Terraform, como parte del bootstrap
original del proyecto (`doc/014-bootstrap-terraform-state-y-plan.md`: "usando el rol de
instancia `madrono-terraform-deployerEC2` ya asociado a esta EC2"), el mismo patrón de
"bootstrap fuera de Terraform" que el bucket de estado S3 y la tabla de locking DynamoDB
de esa misma tarea. `athena.tf` solo lo *menciona* en un comentario (línea 139), no lo
gestiona.

**Consecuencia**: no se ha tocado ningún fichero `.tf` para el punto 1 del alcance —no hay
ningún recurso al que añadirle la acción `codebuild:BatchGetProjects`. No es un
incumplimiento del alcance, es que la premisa ("el permiso vive en código Terraform de
este repo") no era correcta; se documenta aquí en vez de fabricar un recurso IAM ficticio
para un rol que este repositorio no gestiona ni ha gestionado nunca.

## Hallazgo 2: el permiso que faltaba en `doc/083` ya está concedido en AWS (fuera de este repo)

```
$ aws iam list-attached-role-policies --role-name madrono-terraform-deployerEC2
```

...incluye `AWSCodeBuildAdminAccess` (`arn:aws:iam::aws:policy/AWSCodeBuildAdminAccess`),
una managed policy de AWS cuyo `Statement` `AWSServicesAccess` concede `codebuild:*`
(verificado leyendo `aws iam get-policy-version` de esa policy, versión `v20`) — que
incluye `codebuild:BatchGetProjects`, la acción concreta cuya ausencia bloqueó el `plan`
sin acotar en `doc/083`. **No estaba en la lista de policies de `doc/083`** (que documentó
`*FullAccess` en 10 servicios, sin `AWSCodeBuildAdminAccess`) — alguien la añadió a mano en
AWS entre esa sesión y esta, exactamente el paso que `NEXT_STEPS.md` (Prioridad 1, punto 1)
pedía hacer. Como el rol no es gestionable desde este repo (Hallazgo 1), esa es también la
única forma en que se puede aplicar: a mano, por un humano con acceso a IAM, fuera de este
pipeline.

Por este motivo el plan sin acotar de esta tarea **ya completó limpio** sin que hiciera
falta ningún paso adicional de los puntos 2/4 del alcance (`plan -target` acotado al
permiso, o documentar un error parcial) — se aplica directamente el punto 3.

## Hallazgo 3 (caveat de esta sesión, no drift real en AWS): `terraform.tfvars.example` no incluye `lambda_dependencies_layer_arn`

Al copiar `terraform.tfvars.example` → `terraform.tfvars` (no versionado, como en todas las
tareas anteriores que han ejecutado Terraform, p.ej. `doc/014`), la variable
`lambda_dependencies_layer_arn` queda en su valor por defecto (`null`, `variables.tf`).
Un primer `plan` con ese valor por defecto mostraba, además del drift real, un cambio
espurio: quitar la Lambda Layer de dependencias (`layers = [...]` → `[]`) de las 14
funciones productoras — **esto no es drift real de AWS, es un artefacto de que el ejemplo
commiteado no lleva el ARN real de la Layer ya publicada** (`terraform.tfvars` es
gitignored a propósito porque puede llevar valores específicos del entorno, pero este
valor en concreto no es secreto y sin él cualquier `plan` fresco desde cero reproduce este
mismo falso positivo).

Se resolvió consultando el ARN real desplegado con
`aws lambda list-layer-versions --layer-name madrono-tfm-dev-ingesta-dependencies`
(una única versión, `:1`, la misma que ya usan las 14 funciones) y fijándolo explícitamente
en el `terraform.tfvars` local de esta sesión (no commiteado) antes de generar el plan
definitivo. **Recomendación para quien revise este documento**: considerar añadir
`lambda_dependencies_layer_arn = "arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1"`
a `terraform.tfvars.example` (con un comentario explicando que hay que actualizarlo si se
publica una versión nueva de la Layer), para que un `terraform plan` futuro generado desde
cero no vuelva a mostrar este falso drift.

## Categorización del plan real (5 to add, 15 to change, 0 to destroy)

### A. Redespliegue de código a la versión actual de `main` (14 cambios) — sin cambio de comportamiento esperado

Los 14 `aws_lambda_function.producer["<dataset>"]` (uno por cada productor: `aemet_prevision_avisos`,
`afluencia_lugares`, `aforos_peatones_bicicletas`, `agenda_eventos`, `aparcamientos`,
`bicimad`, `bluesky_menciones`, `calidad_aire`, `cams_calidad_aire`,
`cartelera_cines_estrenos`, `meteorologia`, `ruido`, `trafico`, `transporte_publico_emt`)
muestran `~ source_code_hash` cambiado — el `.zip` de `ingesta/` empaquetado desde el
`main` real de este worktree difiere del código Lambda desplegado hoy en AWS. Es la misma
categoría de drift que `doc/083` documentó como los 48 `aws_s3_object.glue_script_*`
(código fusionado en `main` que puede no estar realmente en ejecución) — aquí aplicado a
las funciones Lambda de producción en vez de a los scripts de Glue.

**Importante, y distinto de `doc/083`: los 48 `aws_s3_object.glue_script_*` (y
`procesamiento_source`/`ingesta_source`) que sí aparecían como reemplazo en aquella sesión
NO aparecen ya en este plan** — se refrescan (`Refreshing state...`) sin generar ningún
`~`/`+`/`-`. Es decir, **esa parte del drift original ya no existe**: el código Glue
desplegado ya coincide con `main` a fecha de esta tarea (25/8), aunque no hay ningún
`doc/` intermedio que documente quién lo redesplegó — se deja constancia aquí para que
quien revise no asuma que sigue pendiente.

Colateral de estos 14 cambios (mismos recursos, no un problema independiente): el `data
"aws_iam_policy_document" "scheduler_invoke_lambda"` se relee (por depender de los ARN de
las funciones que se están actualizando) y arrastra un `~` en
`aws_iam_policy.scheduler_invoke_lambda` que Terraform muestra como
`(known after apply)` — los ARNs de destino (nombres de función, estables) no cambian, por
lo que tras aplicar debería resolver exactamente al mismo JSON. No es un cambio de alcance
de permisos, es ruido de dependencia dentro del mismo `apply`.

### B. Infraestructura de Kafka (5 creaciones) — conocida, tarea 042, nunca aplicada

`aws_security_group.kafka`, `aws_iam_role.kafka`, `aws_iam_instance_profile.kafka`,
`aws_iam_role_policy_attachment.kafka_ssm`, `aws_instance.kafka` — exactamente los 5
recursos que `kafka.tf` deja escritos y documentados como "deliberadamente sin aplicar"
desde la tarea 042, ya señalados como esperados en `doc/083` (Hallazgo 2). No es un
hallazgo nuevo.

### C. Cualquier otra cosa fuera de A/B

**Ninguna.** Revisado el plan completo recurso por recurso (`grep -n "^  # "` sobre la
salida): los 20 bloques de cambio son exactamente los 14 de la categoría A (+ 1 policy IAM
colateral + 1 data source colateral) y los 5 de la categoría B. Cero destroys, cero
reemplazos forzados (`forces replacement`), cero cambios sobre `aws_s3_bucket*`
(Bronze/Silver/Gold intactos, igual que en `doc/083`), cero cambios sobre
`afluencia_lugares`/Google Maps más allá del mismo redespliegue de código de la categoría A
que recibe cualquier otro productor (no se ha tocado su retirada, fuera de alcance de esta
tarea).

## Qué NO se hizo (respeta las restricciones del alcance)

- No se ha ejecutado `terraform apply` en ningún momento.
- No se ha usado `-destroy -target` en ningún momento.
- No se ha tocado ningún fichero `.tf` (el punto 1 del alcance resultó no tener ningún
  recurso al que aplicarse — Hallazgo 1 — así que no hay ningún diff en `infra/terraform/`
  al terminar esta tarea).
- No se ha tocado `afluencia_lugares`/Google Maps más allá de lo que ya recibe
  cualquier otro productor por igual (categoría A).
- `backend.hcl`/`terraform.tfvars`/`.terraform/`/`*.tfplan` usados durante esta tarea son
  todos gitignored (verificado con `git status --porcelain` antes y después: limpio) — no
  quedan en el commit.

## Siguiente paso (para la tarea 2 de este patrón, no esta)

1. Revisar sección por sección el plan volcado abajo con un humano (tal como pide
   `NEXT_STEPS.md`, Prioridad 1, punto 2).
2. Si se confirma, `terraform apply` — categoría A actualiza el código de las 14 Lambdas a
   `main`, categoría B crea la infraestructura de Kafka de la tarea 042 (confirmar primero
   con quien revise si Kafka debe desplegarse ya, o si sigue siendo deliberadamente
   pendiente — no estaba en el alcance de esta tarea decidirlo).
3. Volver a verificar en vivo tras aplicar (mismo patrón que `doc/083`/`doc/084`:
   `aws lambda list-functions`, comprobar `LastModified`/`CodeSha256` de al menos una
   función).
4. Si se decide fijar `lambda_dependencies_layer_arn` en `terraform.tfvars.example`
   (Hallazgo 3), hacerlo en esa misma tarea o en una previa dedicada a limpieza de
   Terraform — no se ha hecho aquí para no exceder "no toques ningún fichero `.tf`/de
   configuración más allá de lo estrictamente necesario para producir el plan".

## Salida completa y literal de `terraform plan` (sin acotar, sin aplicar)

Generada con:

```
$ terraform init -backend-config=backend.hcl -input=false
$ terraform plan -input=false -no-color
```

usando el rol de instancia real `madrono-terraform-deployerEC2` de esta EC2 (mismas
credenciales que cualquier tarea anterior que haya tocado `infra/terraform/`), contra el
backend S3 remoto real (`madrono-tfm-terraform-state`) y el estado real de la cuenta
`222234418587` (`eu-west-1`).

```text

Warning: Deprecated Parameter

The parameter "dynamodb_table" is deprecated. Use parameter "use_lockfile"
instead.
data.archive_file.layer_build_source: Reading...
data.archive_file.layer_build_source: Read complete after 0s [id=91cff7c2e142516b467eed53571b9533a0dccf81]
data.archive_file.ingesta_source: Reading...
data.aws_iam_policy_document.glue_ruido_assume_role: Reading...
aws_cloudwatch_log_group.glue_afluencia_lugares: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-afluencia-lugares]
data.aws_iam_policy_document.kafka_assume_role: Reading...
aws_cloudwatch_log_group.glue_aemet_prevision_avisos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-aemet-prevision-avisos]
data.aws_iam_policy_document.ingestion_assume_role: Reading...
data.aws_iam_policy_document.glue_calidad_aire_assume_role: Reading...
aws_cloudwatch_log_group.producer["trafico"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-trafico]
aws_cloudwatch_log_group.glue_transporte_publico_emt: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-transporte-publico-emt]
data.aws_iam_policy_document.glue_ruido_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_calidad_aire_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.kafka_assume_role: Read complete after 0s [id=2851119427]
data.aws_iam_policy_document.ingestion_assume_role: Read complete after 0s [id=2690255455]
data.aws_iam_policy_document.lambda_layer_codebuild_assume_role: Reading...
data.aws_iam_policy_document.glue_trafico_assume_role: Reading...
aws_ssm_parameter.secrets["EMT_CLIENT_ID"]: Refreshing state... [id=/madrono-tfm/dev/secrets/emt-client-id]
data.aws_iam_policy_document.glue_bluesky_menciones_assume_role: Reading...
data.aws_iam_policy_document.lambda_layer_codebuild_assume_role: Read complete after 0s [id=1229436035]
data.aws_iam_policy_document.glue_bluesky_menciones_assume_role: Read complete after 0s [id=2681768870]
aws_cloudwatch_log_group.glue_calidad_aire: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-calidad-aire]
data.aws_iam_policy_document.glue_trafico_assume_role: Read complete after 0s [id=2681768870]
aws_cloudwatch_log_group.glue_aforos_peatones_bicicletas: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-aforos-peatones-bicicletas]
aws_cloudwatch_log_group.glue_bicimad: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-bicimad]
aws_cloudwatch_log_group.glue_cams_calidad_aire: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-cams-calidad-aire]
aws_cloudwatch_log_group.producer["aemet_prevision_avisos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-aemet_prevision_avisos]
aws_cloudwatch_log_group.glue_cartelera_cines_estrenos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-cartelera-cines-estrenos]
aws_cloudwatch_log_group.producer["ruido"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-ruido]
aws_cloudwatch_log_group.producer["bluesky_menciones"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-bluesky_menciones]
aws_cloudwatch_log_group.producer["transporte_publico_emt"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-transporte_publico_emt]
aws_cloudwatch_log_group.producer["afluencia_lugares"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-afluencia_lugares]
aws_cloudwatch_log_group.producer["aforos_peatones_bicicletas"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-aforos_peatones_bicicletas]
aws_cloudwatch_log_group.producer["bicimad"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-bicimad]
aws_cloudwatch_log_group.producer["meteorologia"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-meteorologia]
aws_cloudwatch_log_group.producer["agenda_eventos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-agenda_eventos]
aws_cloudwatch_log_group.producer["aparcamientos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-aparcamientos]
aws_cloudwatch_log_group.producer["cams_calidad_aire"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-cams_calidad_aire]
aws_cloudwatch_log_group.producer["calidad_aire"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-calidad_aire]
aws_cloudwatch_log_group.producer["cartelera_cines_estrenos"]: Refreshing state... [id=/aws/lambda/madrono-tfm-dev-cartelera_cines_estrenos]
aws_cloudwatch_log_group.glue_agenda_eventos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-agenda-eventos]
aws_cloudwatch_log_group.glue_shared["error"]: Refreshing state... [id=/aws-glue/jobs/error]
aws_cloudwatch_log_group.glue_shared["logs-v2"]: Refreshing state... [id=/aws-glue/jobs/logs-v2]
data.archive_file.procesamiento_source: Reading...
aws_cloudwatch_log_group.glue_shared["output"]: Refreshing state... [id=/aws-glue/jobs/output]
aws_cloudwatch_log_group.glue_aparcamientos: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-aparcamientos]
data.aws_iam_policy_document.glue_agenda_eventos_assume_role: Reading...
data.aws_caller_identity.current: Reading...
data.aws_iam_policy_document.glue_cams_calidad_aire_assume_role: Reading...
data.aws_iam_policy_document.glue_agenda_eventos_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_cams_calidad_aire_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_aparcamientos_assume_role: Reading...
aws_cloudwatch_log_group.glue_bluesky_menciones: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-bluesky-menciones]
data.aws_iam_policy_document.glue_aparcamientos_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_afluencia_lugares_assume_role: Reading...
data.aws_iam_policy_document.glue_meteorologia_assume_role: Reading...
data.aws_caller_identity.current: Read complete after 0s [id=222234418587]
data.aws_iam_policy_document.glue_meteorologia_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_afluencia_lugares_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.scheduler_assume_role: Reading...
data.aws_iam_policy_document.glue_transporte_publico_emt_assume_role: Reading...
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_assume_role: Reading...
data.aws_iam_policy_document.scheduler_assume_role: Read complete after 0s [id=52247394]
data.aws_iam_policy_document.glue_bicimad_assume_role: Reading...
data.aws_iam_policy_document.glue_transporte_publico_emt_assume_role: Read complete after 0s [id=2681768870]
aws_glue_catalog_database.gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold]
data.aws_iam_policy_document.glue_aemet_prevision_avisos_assume_role: Reading...
data.aws_iam_policy_document.glue_bicimad_assume_role: Read complete after 1s [id=2681768870]
data.aws_iam_policy_document.glue_aemet_prevision_avisos_assume_role: Read complete after 0s [id=2681768870]
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_assume_role: Read complete after 1s [id=2681768870]
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_assume_role: Reading...
aws_cloudwatch_log_group.glue_trafico: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-trafico]
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_assume_role: Read complete after 0s [id=2681768870]
aws_glue_catalog_database.silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver]
data.aws_ssm_parameter.al2023_ami: Reading...
data.aws_vpc.default: Reading...
aws_cloudwatch_log_group.glue_meteorologia: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-meteorologia]
aws_ssm_parameter.secrets["EMT_PASS_KEY"]: Refreshing state... [id=/madrono-tfm/dev/secrets/emt-pass-key]
aws_ssm_parameter.secrets["GOOGLE_MAPS_API_KEY"]: Refreshing state... [id=/madrono-tfm/dev/secrets/google-maps-api-key]
data.aws_ssm_parameter.al2023_ami: Read complete after 0s [id=/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64]
aws_ssm_parameter.secrets["AEMET_API_KEY"]: Refreshing state... [id=/madrono-tfm/dev/secrets/aemet-api-key]
aws_ssm_parameter.secrets["CAMS_ADS_API_KEY"]: Refreshing state... [id=/madrono-tfm/dev/secrets/cams-ads-api-key]
aws_cloudwatch_log_group.glue_ruido: Refreshing state... [id=/aws-glue/jobs/madrono-tfm-dev-ruido]
aws_iam_role.glue_ruido: Refreshing state... [id=madrono-tfm-dev-ruido-glue-role]
aws_iam_role.glue_calidad_aire: Refreshing state... [id=madrono-tfm-dev-calidad-aire-glue-role]
aws_iam_role.ingestion: Refreshing state... [id=madrono-tfm-dev-ingestion-role]
aws_iam_role.lambda_layer_codebuild: Refreshing state... [id=madrono-tfm-dev-lambda-layer-codebuild-role]
aws_iam_role.glue_bluesky_menciones: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-glue-role]
aws_iam_role.glue_trafico: Refreshing state... [id=madrono-tfm-dev-trafico-glue-role]
data.aws_iam_policy_document.ingestion_lambda_logs: Reading...
data.aws_iam_policy_document.ingestion_lambda_logs: Read complete after 0s [id=64690464]
aws_iam_role.glue_agenda_eventos: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-glue-role]
data.aws_vpc.default: Read complete after 0s [id=vpc-0cd0f252bd38d9edf]
aws_iam_role.glue_cams_calidad_aire: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-glue-role]
aws_iam_role.glue_aparcamientos: Refreshing state... [id=madrono-tfm-dev-aparcamientos-glue-role]
aws_s3_bucket.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
data.aws_iam_policy_document.athena_query_assume_role: Reading...
data.aws_iam_policy_document.athena_query_assume_role: Read complete after 0s [id=337710939]
aws_s3_bucket.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_iam_role.glue_meteorologia: Refreshing state... [id=madrono-tfm-dev-meteorologia-glue-role]
aws_iam_role.glue_afluencia_lugares: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-glue-role]
aws_iam_role.scheduler: Refreshing state... [id=madrono-tfm-dev-scheduler-role]
aws_iam_role.glue_transporte_publico_emt: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-glue-role]
data.archive_file.ingesta_source: Read complete after 2s [id=8c43bf85c6158f114b0e28436c4d9c0880c7766a]
aws_iam_role.glue_aemet_prevision_avisos: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-glue-role]
aws_iam_role.glue_bicimad: Refreshing state... [id=madrono-tfm-dev-bicimad-glue-role]
aws_iam_role.glue_cartelera_cines_estrenos: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-glue-role]
aws_iam_role.glue_aforos_peatones_bicicletas: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-glue-role]
aws_iam_policy.ingestion_lambda_logs: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-ingestion-lambda-logs]
data.aws_subnets.default: Reading...
data.aws_subnets.default: Read complete after 0s [id=eu-west-1]
aws_iam_role_policy_attachment.glue_ruido_service_role: Refreshing state... [id=madrono-tfm-dev-ruido-glue-role-20260817225242315200000005]
aws_iam_role_policy_attachment.glue_calidad_aire_service_role: Refreshing state... [id=madrono-tfm-dev-calidad-aire-glue-role-20260816075639813800000006]
aws_s3_bucket.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_iam_role.athena_query: Refreshing state... [id=madrono-tfm-dev-athena-query-role]
aws_s3_bucket.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_s3_bucket.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_iam_role_policy_attachment.glue_bluesky_menciones_service_role: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-glue-role-20260817225241998700000001]
aws_iam_role_policy_attachment.glue_agenda_eventos_service_role: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-glue-role-20260817225242339700000007]
aws_iam_role_policy_attachment.glue_trafico_service_role: Refreshing state... [id=madrono-tfm-dev-trafico-glue-role-20260816075639044000000003]
aws_iam_role_policy_attachment.glue_cams_calidad_aire_service_role: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-glue-role-20260817225242109200000002]
aws_iam_role_policy_attachment.glue_aparcamientos_service_role: Refreshing state... [id=madrono-tfm-dev-aparcamientos-glue-role-20260816075639434100000004]
aws_iam_role_policy_attachment.glue_afluencia_lugares_service_role: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-glue-role-20260817225242316200000006]
aws_iam_role_policy_attachment.glue_meteorologia_service_role: Refreshing state... [id=madrono-tfm-dev-meteorologia-glue-role-20260816075639015600000001]
aws_iam_role_policy_attachment.glue_transporte_publico_emt_service_role: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-glue-role-20260816075639707000000005]
aws_iam_role_policy_attachment.glue_aemet_prevision_avisos_service_role: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-glue-role-20260817225242271000000004]
aws_athena_workgroup.silver_gold: Refreshing state... [id=madrono-tfm-dev-silver-gold]
data.aws_iam_policy_document.athena_results_bucket_policy: Reading...
data.aws_iam_policy_document.athena_results_bucket_policy: Read complete after 0s [id=3728792540]
aws_s3_bucket_server_side_encryption_configuration.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
aws_s3_bucket_lifecycle_configuration.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
aws_s3_bucket_public_access_block.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
aws_s3_object.glue_script_transporte_publico_emt_backfill_dedup: Refreshing state... [id=glue-scripts/transporte_publico_emt_backfill_dedup-23abd9cec70fa40fd164acace5643b81.py]
aws_iam_role_policy_attachment.ingestion_lambda_logs: Refreshing state... [id=madrono-tfm-dev-ingestion-role-20260814212955875100000001]
aws_s3_object.glue_script_aemet_prevision_avisos_bronze_to_silver: Refreshing state... [id=glue-scripts/aemet_prevision_avisos_bronze_to_silver-5874411ad6f28f158f685ce90841add5.py]
aws_s3_object.glue_script_aemet_prevision_avisos_silver_to_gold: Refreshing state... [id=glue-scripts/aemet_prevision_avisos_silver_to_gold-735e6a4f6938be2c1d4d15ce74735529.py]
aws_s3_object.glue_script_bicimad_bronze_to_silver: Refreshing state... [id=glue-scripts/bicimad_bronze_to_silver-44a29129cff7226b539da9071dd8f8b7.py]
aws_iam_role_policy_attachment.glue_bicimad_service_role: Refreshing state... [id=madrono-tfm-dev-bicimad-glue-role-20260816075639036000000002]
aws_s3_object.glue_script_cams_calidad_aire_bronze_to_silver: Refreshing state... [id=glue-scripts/cams_calidad_aire_bronze_to_silver-c0577843a652fafb4ba8dc477363c545.py]
aws_s3_object.glue_script_meteorologia_silver_to_gold: Refreshing state... [id=glue-scripts/meteorologia_silver_to_gold-169c14fd98eac491489861d9e5192564.py]
aws_s3_object.glue_script_cartelera_cines_estrenos_silver_to_gold: Refreshing state... [id=glue-scripts/cartelera_cines_estrenos_silver_to_gold-90a5785103ca4aa3ef331d91a67d2851.py]
aws_s3_object.glue_script_transporte_publico_emt_silver_to_gold: Refreshing state... [id=glue-scripts/transporte_publico_emt_silver_to_gold-31a48a9152356f0fb479193b278e8d0c.py]
aws_s3_object.glue_script_afluencia_lugares_silver_to_gold: Refreshing state... [id=glue-scripts/afluencia_lugares_silver_to_gold-62c7375ae0141dbeab3bcc17a4936081.py]
aws_s3_object.glue_script_ruido_bronze_to_silver: Refreshing state... [id=glue-scripts/ruido_bronze_to_silver-4578e5651d5577da838113244d5be142.py]
aws_s3_object.glue_script_calidad_aire_bronze_to_silver: Refreshing state... [id=glue-scripts/calidad_aire_bronze_to_silver-da2056544438c70f538d76fa59f438a4.py]
aws_s3_object.glue_script_cams_calidad_aire_backfill_dedup: Refreshing state... [id=glue-scripts/cams_calidad_aire_backfill_dedup-f740ec883030bc43077f1cf7c79cffd7.py]
aws_s3_object.glue_script_transporte_publico_emt_bronze_to_silver: Refreshing state... [id=glue-scripts/transporte_publico_emt_bronze_to_silver-227b9894b2fc66730ce2cbb6a7a9f6a3.py]
aws_s3_object.glue_script_ruido_backfill_dedup_gold: Refreshing state... [id=glue-scripts/ruido_backfill_dedup_gold-f687c85eeca0b75468cfe68bb01c48c3.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_backfill_dedup_gold: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_backfill_dedup_gold-dedd44063c766e8475986650df404498.py]
aws_s3_object.glue_script_bluesky_menciones_backfill_dedup: Refreshing state... [id=glue-scripts/bluesky_menciones_backfill_dedup-2efdec7fc5aa3a4ed77dbee6c1a5e2d4.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_bronze_to_silver: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_bronze_to_silver-d037fa3c1d50aa6cdf1a4355e4af910b.py]
aws_s3_object.layer_build_source: Refreshing state... [id=source/ingesta-requirements-dda68d48ce6639f0dc4b67370d63ca56.zip]
aws_s3_object.glue_script_agenda_eventos_silver_to_gold: Refreshing state... [id=glue-scripts/agenda_eventos_silver_to_gold-73b5e533d9966653fcd6f2597254ba59.py]
aws_s3_object.glue_script_silver_to_gold: Refreshing state... [id=glue-scripts/trafico_silver_to_gold-60a5f338a6cc68a8c760176719c0db97.py]
aws_s3_bucket_server_side_encryption_configuration.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
data.aws_iam_policy_document.lambda_layer_codebuild: Reading...
aws_s3_object.glue_script_aparcamientos_backfill_dedup_gold: Refreshing state... [id=glue-scripts/aparcamientos_backfill_dedup_gold-b03433c6e4e72c7e33e557790f1809b2.py]
data.aws_iam_policy_document.lambda_layer_codebuild: Read complete after 0s [id=2269842593]
aws_s3_object.glue_script_bluesky_menciones_backfill_dedup_gold: Refreshing state... [id=glue-scripts/bluesky_menciones_backfill_dedup_gold-eaac70080a579db34ec3c54244f4e426.py]
aws_s3_bucket_lifecycle_configuration.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_s3_bucket_public_access_block.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_s3_object.glue_script_cams_calidad_aire_backfill_dedup_gold: Refreshing state... [id=glue-scripts/cams_calidad_aire_backfill_dedup_gold-1a9154bc6c0c71a12b1e6c42eea25f30.py]
aws_s3_object.glue_script_agenda_eventos_backfill_dedup: Refreshing state... [id=glue-scripts/agenda_eventos_backfill_dedup-406949108f74a212bfa3dd0a5f67acca.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_backfill_dedup: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_backfill_dedup-8dc97077e9a7b0d793edb42e68c8a090.py]
aws_s3_object.glue_script_bluesky_menciones_silver_to_gold: Refreshing state... [id=glue-scripts/bluesky_menciones_silver_to_gold-eebc2e82aa50cb399f022af861372782.py]
aws_s3_object.glue_script_bicimad_backfill_dedup: Refreshing state... [id=glue-scripts/bicimad_backfill_dedup-ed6e6af42559477339b933051cafe77b.py]
aws_s3_object.glue_script_cams_calidad_aire_silver_to_gold: Refreshing state... [id=glue-scripts/cams_calidad_aire_silver_to_gold-b314b6a6fc7c546a4c090fe2e01f052d.py]
aws_s3_object.glue_script_afluencia_lugares_bronze_to_silver: Refreshing state... [id=glue-scripts/afluencia_lugares_bronze_to_silver-e019ce6127891d24af49cb253082177b.py]
aws_s3_object.glue_script_agenda_eventos_backfill_dedup_gold: Refreshing state... [id=glue-scripts/agenda_eventos_backfill_dedup_gold-b4c8693ee116e2f50aee1b96fd7018c6.py]
aws_s3_object.glue_script_aforos_peatones_bicicletas_silver_to_gold: Refreshing state... [id=glue-scripts/aforos_peatones_bicicletas_silver_to_gold-1ed5acbc05f8bc8dc8c53eae4e789893.py]
aws_s3_object.glue_script_ruido_silver_to_gold: Refreshing state... [id=glue-scripts/ruido_silver_to_gold-df06da27741ea0c03b88aab3ac7e0a51.py]
aws_s3_object.glue_script_meteorologia_backfill_dedup: Refreshing state... [id=glue-scripts/meteorologia_backfill_dedup-d0fd57ddf99e04744edfcba8d690721c.py]
aws_s3_object.glue_script_bicimad_backfill_dedup_gold: Refreshing state... [id=glue-scripts/bicimad_backfill_dedup_gold-3cc7762735e125d2ba40c9a759900087.py]
aws_lambda_layer_version.ingesta_dependencies: Refreshing state... [id=arn:aws:lambda:eu-west-1:222234418587:layer:madrono-tfm-dev-ingesta-dependencies:1]
aws_s3_object.glue_script_calidad_aire_backfill_dedup: Refreshing state... [id=glue-scripts/calidad_aire_backfill_dedup-34fd8107fa813f83f6e1b5b6ad747653.py]
aws_s3_object.glue_script_aparcamientos_backfill_dedup: Refreshing state... [id=glue-scripts/aparcamientos_backfill_dedup-d2f4134d5b53957b15e82d4bed24c7eb.py]
aws_s3_object.glue_script_meteorologia_backfill_dedup_gold: Refreshing state... [id=glue-scripts/meteorologia_backfill_dedup_gold-f919944ff6593ee881f3d4d2a4c57ecf.py]
aws_s3_object.glue_script_bronze_to_silver: Refreshing state... [id=glue-scripts/trafico_bronze_to_silver-168f6d4b74abbb184207e7548dc13bdb.py]
data.aws_iam_policy_document.build_artifacts_bucket_policy: Reading...
data.aws_iam_policy_document.build_artifacts_bucket_policy: Read complete after 0s [id=1312249984]
aws_s3_object.glue_script_transporte_publico_emt_backfill_dedup_gold: Refreshing state... [id=glue-scripts/transporte_publico_emt_backfill_dedup_gold-fe90bd1230ec95accd5efc6836a9c7f5.py]
aws_s3_object.glue_script_agenda_eventos_bronze_to_silver: Refreshing state... [id=glue-scripts/agenda_eventos_bronze_to_silver-e24cfdad3be04dfe065231b9643719c0.py]
aws_s3_object.glue_script_ruido_backfill_dedup: Refreshing state... [id=glue-scripts/ruido_backfill_dedup-fce8661c6ea351323d8dbec6a79e1377.py]
aws_s3_object.glue_script_cartelera_cines_estrenos_bronze_to_silver: Refreshing state... [id=glue-scripts/cartelera_cines_estrenos_bronze_to_silver-2b7b796b05eb81035f181fa7ae643321.py]
aws_s3_object.glue_script_aparcamientos_silver_to_gold: Refreshing state... [id=glue-scripts/aparcamientos_silver_to_gold-ce49527d7c8d3dd98bcb65d2ca1b38ad.py]
aws_s3_object.glue_script_calidad_aire_silver_to_gold: Refreshing state... [id=glue-scripts/calidad_aire_silver_to_gold-2aa3d2a268bb6c9d89020347d439f194.py]
aws_s3_object.glue_script_meteorologia_bronze_to_silver: Refreshing state... [id=glue-scripts/meteorologia_bronze_to_silver-9f8c92a3c75695ffe310682ba8d437b0.py]
aws_s3_object.glue_script_aparcamientos_bronze_to_silver: Refreshing state... [id=glue-scripts/aparcamientos_bronze_to_silver-90e5ef17131a899ea2f70fcff0bb1962.py]
aws_s3_object.glue_script_calidad_aire_backfill_dedup_gold: Refreshing state... [id=glue-scripts/calidad_aire_backfill_dedup_gold-b1b779d81465784f5abab97e0cbdab0c.py]
aws_s3_object.glue_script_bicimad_silver_to_gold: Refreshing state... [id=glue-scripts/bicimad_silver_to_gold-c843909cc91d34dcfdcf321695e074a2.py]
aws_s3_object.glue_script_bluesky_menciones_bronze_to_silver: Refreshing state... [id=glue-scripts/bluesky_menciones_bronze_to_silver-3911e443483f4b8bccf853ec600d43b6.py]
aws_iam_role_policy_attachment.glue_aforos_peatones_bicicletas_service_role: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-glue-role-20260817225242176000000003]
aws_iam_role_policy_attachment.glue_cartelera_cines_estrenos_service_role: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-glue-role-2026081722524271480000000b]
aws_s3_bucket_policy.athena_results: Refreshing state... [id=madrono-tfm-dev-athena-results-222234418587]
aws_lambda_function.producer["transporte_publico_emt"]: Refreshing state... [id=madrono-tfm-dev-transporte_publico_emt]
aws_lambda_function.producer["aemet_prevision_avisos"]: Refreshing state... [id=madrono-tfm-dev-aemet_prevision_avisos]
aws_lambda_function.producer["afluencia_lugares"]: Refreshing state... [id=madrono-tfm-dev-afluencia_lugares]
aws_lambda_function.producer["bluesky_menciones"]: Refreshing state... [id=madrono-tfm-dev-bluesky_menciones]
aws_lambda_function.producer["meteorologia"]: Refreshing state... [id=madrono-tfm-dev-meteorologia]
aws_lambda_function.producer["cams_calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-cams_calidad_aire]
aws_lambda_function.producer["agenda_eventos"]: Refreshing state... [id=madrono-tfm-dev-agenda_eventos]
aws_lambda_function.producer["trafico"]: Refreshing state... [id=madrono-tfm-dev-trafico]
aws_lambda_function.producer["aforos_peatones_bicicletas"]: Refreshing state... [id=madrono-tfm-dev-aforos_peatones_bicicletas]
aws_lambda_function.producer["bicimad"]: Refreshing state... [id=madrono-tfm-dev-bicimad]
aws_lambda_function.producer["calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-calidad_aire]
aws_lambda_function.producer["aparcamientos"]: Refreshing state... [id=madrono-tfm-dev-aparcamientos]
aws_lambda_function.producer["cartelera_cines_estrenos"]: Refreshing state... [id=madrono-tfm-dev-cartelera_cines_estrenos]
aws_lambda_function.producer["ruido"]: Refreshing state... [id=madrono-tfm-dev-ruido]
data.aws_iam_policy_document.athena_query: Reading...
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_data_access: Reading...
data.aws_iam_policy_document.athena_query: Read complete after 0s [id=1764529612]
data.aws_iam_policy_document.bucket_policy["silver"]: Reading...
data.aws_iam_policy_document.glue_bluesky_menciones_data_access: Reading...
data.aws_iam_policy_document.bucket_policy["silver"]: Read complete after 0s [id=168412883]
data.aws_iam_policy_document.bucket_policy["bronze"]: Reading...
data.aws_iam_policy_document.glue_aforos_peatones_bicicletas_data_access: Read complete after 0s [id=2497092921]
data.aws_iam_policy_document.bucket_policy["bronze"]: Read complete after 0s [id=42177744]
data.aws_iam_policy_document.bucket_policy["gold"]: Reading...
data.aws_iam_policy_document.bucket_policy["gold"]: Read complete after 0s [id=1014628649]
data.aws_iam_policy_document.glue_bluesky_menciones_data_access: Read complete after 0s [id=3016547089]
aws_glue_catalog_table.calidad_aire_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:calidad_aire]
data.aws_iam_policy_document.glue_transporte_publico_emt_data_access: Reading...
data.aws_iam_policy_document.glue_ruido_data_access: Reading...
data.aws_iam_policy_document.glue_transporte_publico_emt_data_access: Read complete after 0s [id=1469263382]
data.aws_iam_policy_document.glue_ruido_data_access: Read complete after 0s [id=3942754620]
data.aws_iam_policy_document.glue_calidad_aire_data_access: Reading...
aws_glue_catalog_table.meteorologia_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:meteorologia_por_estacion_magnitud_hora]
data.aws_iam_policy_document.glue_calidad_aire_data_access: Read complete after 0s [id=3442098839]
data.aws_iam_policy_document.glue_aparcamientos_data_access: Reading...
aws_glue_catalog_table.transporte_publico_emt_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:transporte_publico_emt_por_parada_hora]
data.aws_iam_policy_document.glue_aparcamientos_data_access: Read complete after 0s [id=3918684311]
data.aws_iam_policy_document.glue_cams_calidad_aire_data_access: Reading...
data.aws_iam_policy_document.glue_cams_calidad_aire_data_access: Read complete after 0s [id=3873881262]
aws_glue_catalog_table.cams_calidad_aire_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:cams_calidad_aire_por_contaminante_fecha_validez]
aws_glue_catalog_table.trafico_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:trafico_por_punto_hora]
aws_glue_catalog_table.aemet_avisos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aemet_avisos_por_zona_fecha_nivel]
data.aws_iam_policy_document.glue_meteorologia_data_access: Reading...
data.aws_iam_policy_document.glue_meteorologia_data_access: Read complete after 0s [id=1660976330]
aws_glue_catalog_table.bluesky_menciones_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:bluesky_menciones_por_termino_modo_hora]
data.aws_iam_policy_document.glue_afluencia_lugares_data_access: Reading...
data.aws_iam_policy_document.glue_afluencia_lugares_data_access: Read complete after 0s [id=2439414232]
aws_glue_catalog_table.afluencia_lugares_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:afluencia_lugares]
aws_glue_catalog_table.meteorologia_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:meteorologia]
aws_glue_catalog_table.cartelera_cines_estrenos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:cartelera_cines_estrenos]
data.aws_iam_policy_document.glue_trafico_data_access: Reading...
aws_glue_catalog_table.trafico_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:trafico]
data.aws_iam_policy_document.glue_trafico_data_access: Read complete after 0s [id=3067492418]
aws_glue_catalog_table.agenda_eventos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:agenda_eventos]
aws_glue_catalog_table.ruido_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:ruido]
aws_glue_catalog_table.aemet_prevision_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aemet_prevision]
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_data_access: Reading...
aws_glue_catalog_table.aparcamientos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aparcamientos]
data.aws_iam_policy_document.glue_aemet_prevision_avisos_data_access: Reading...
data.aws_iam_policy_document.glue_cartelera_cines_estrenos_data_access: Read complete after 0s [id=3258002293]
aws_glue_catalog_table.bicimad_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:bicimad_por_estacion_hora]
aws_glue_catalog_table.aemet_avisos_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aemet_avisos]
data.aws_iam_policy_document.glue_aemet_prevision_avisos_data_access: Read complete after 0s [id=192142698]
aws_glue_catalog_table.calidad_aire_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:calidad_aire_por_estacion_contaminante_hora]
aws_glue_catalog_table.aemet_prevision_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aemet_prevision_por_municipio_leadtime]
aws_glue_catalog_table.bicimad_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:bicimad]
aws_glue_catalog_table.aforos_peatones_bicicletas_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aforos_peatones_bicicletas_por_estacion_modo_hora]
data.aws_iam_policy_document.glue_agenda_eventos_data_access: Reading...
data.archive_file.procesamiento_source: Read complete after 9s [id=3b52f985354ade75fe0b672fd8023832139dbd08]
aws_glue_catalog_table.ruido_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:ruido_por_estacion_periodo_fecha]
data.aws_iam_policy_document.glue_agenda_eventos_data_access: Read complete after 0s [id=2233283693]
aws_glue_catalog_table.afluencia_lugares_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:afluencia_lugares_por_lugar_fecha_hora]
aws_s3_bucket_versioning.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_glue_catalog_table.aforos_peatones_bicicletas_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:aforos_peatones_bicicletas]
aws_s3_bucket_versioning.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_versioning.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_glue_catalog_table.bluesky_menciones_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:bluesky_menciones]
aws_glue_catalog_table.cartelera_cines_estrenos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:cartelera_cines_estrenos_por_pelicula_cine_fecha]
data.aws_iam_policy_document.ingestion_bronze_write: Reading...
data.aws_iam_policy_document.ingestion_bronze_write: Read complete after 0s [id=175239690]
aws_s3_bucket_public_access_block.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_public_access_block.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_s3_bucket_public_access_block.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_glue_catalog_table.cams_calidad_aire_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:cams_calidad_aire]
aws_glue_catalog_table.agenda_eventos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:agenda_eventos_por_categoria_distrito_fecha]
aws_glue_catalog_table.transporte_publico_emt_silver: Refreshing state... [id=222234418587:madrono-tfm_dev_silver:transporte_publico_emt]
aws_glue_catalog_table.aparcamientos_gold: Refreshing state... [id=222234418587:madrono-tfm_dev_gold:aparcamientos_por_parking_hora]
aws_glue_job.ruido_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-ruido-gold-backfill-dedup]
data.aws_iam_policy_document.glue_bicimad_data_access: Reading...
data.aws_iam_policy_document.glue_bicimad_data_access: Read complete after 0s [id=2467033104]
aws_glue_job.aforos_peatones_bicicletas_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-gold-backfill-dedup]
aws_iam_role_policy.lambda_layer_codebuild: Refreshing state... [id=madrono-tfm-dev-lambda-layer-codebuild-role:madrono-tfm-dev-lambda-layer-codebuild-policy]
aws_glue_job.bluesky_menciones_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-gold-backfill-dedup]
aws_glue_job.cams_calidad_aire_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-gold-backfill-dedup]
aws_s3_bucket_policy.build_artifacts: Refreshing state... [id=madrono-tfm-dev-build-artifacts-222234418587]
aws_glue_job.aparcamientos_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aparcamientos-gold-backfill-dedup]
aws_glue_job.agenda_eventos_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-gold-backfill-dedup]
aws_glue_job.bicimad_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bicimad-gold-backfill-dedup]
aws_glue_job.meteorologia_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-meteorologia-gold-backfill-dedup]
aws_glue_job.transporte_publico_emt_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-gold-backfill-dedup]
aws_glue_job.calidad_aire_gold_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-calidad-aire-gold-backfill-dedup]
aws_iam_policy.glue_aforos_peatones_bicicletas_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-aforos-peatones-bicicletas-data-access]
aws_iam_policy.athena_query: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-athena-query]
aws_s3_bucket_policy.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_iam_policy.glue_bluesky_menciones_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-bluesky-menciones-data-access]
aws_s3_bucket_policy.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_policy.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_iam_policy.glue_transporte_publico_emt_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-transporte-publico-emt-data-access]
aws_iam_policy.glue_ruido_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-ruido-data-access]
aws_iam_policy.glue_calidad_aire_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-calidad-aire-data-access]
aws_iam_policy.glue_aparcamientos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-aparcamientos-data-access]
aws_iam_policy.glue_cams_calidad_aire_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-cams-calidad-aire-data-access]
aws_iam_policy.glue_meteorologia_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-meteorologia-data-access]
aws_iam_policy.glue_afluencia_lugares_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-afluencia-lugares-data-access]
aws_iam_policy.glue_trafico_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-trafico-data-access]
aws_iam_policy.glue_cartelera_cines_estrenos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-cartelera-cines-estrenos-data-access]
aws_scheduler_schedule.producer["trafico"]: Refreshing state... [id=default/madrono-tfm-dev-trafico]
aws_scheduler_schedule.producer["agenda_eventos"]: Refreshing state... [id=default/madrono-tfm-dev-agenda_eventos]
aws_scheduler_schedule.producer["aparcamientos"]: Refreshing state... [id=default/madrono-tfm-dev-aparcamientos]
aws_scheduler_schedule.producer["calidad_aire"]: Refreshing state... [id=default/madrono-tfm-dev-calidad_aire]
aws_scheduler_schedule.producer["aemet_avisos_0800"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_0800]
aws_scheduler_schedule.producer["aemet_avisos_2350"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_2350]
aws_scheduler_schedule.producer["aemet_prevision_0700"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_prevision_0700]
aws_scheduler_schedule.producer["ruido"]: Refreshing state... [id=default/madrono-tfm-dev-ruido]
aws_scheduler_schedule.producer["meteorologia"]: Refreshing state... [id=default/madrono-tfm-dev-meteorologia]
aws_scheduler_schedule.producer["aemet_avisos_1800"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_1800]
aws_scheduler_schedule.producer["afluencia_lugares"]: Refreshing state... [id=default/madrono-tfm-dev-afluencia_lugares]
aws_scheduler_schedule.producer["aemet_avisos_1100"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_avisos_1100]
aws_scheduler_schedule.producer["bluesky_menciones"]: Refreshing state... [id=default/madrono-tfm-dev-bluesky_menciones]
aws_scheduler_schedule.producer["emt_llegadas"]: Refreshing state... [id=default/madrono-tfm-dev-emt_llegadas]
aws_scheduler_schedule.producer["cartelera_cines_estrenos"]: Refreshing state... [id=default/madrono-tfm-dev-cartelera_cines_estrenos]
aws_scheduler_schedule.producer["aforos_peatones_bicicletas"]: Refreshing state... [id=default/madrono-tfm-dev-aforos_peatones_bicicletas]
aws_scheduler_schedule.producer["bicimad"]: Refreshing state... [id=default/madrono-tfm-dev-bicimad]
aws_scheduler_schedule.producer["aemet_prevision_1400"]: Refreshing state... [id=default/madrono-tfm-dev-aemet_prevision_1400]
aws_scheduler_schedule.producer["cams_0900_utc"]: Refreshing state... [id=default/madrono-tfm-dev-cams_0900_utc]
aws_scheduler_schedule.producer["cams_0715_utc"]: Refreshing state... [id=default/madrono-tfm-dev-cams_0715_utc]
aws_iam_policy.glue_aemet_prevision_avisos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-aemet-prevision-avisos-data-access]
aws_iam_policy.ingestion_bronze_write: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-ingestion-bronze-write]
aws_iam_policy.glue_agenda_eventos_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-agenda-eventos-data-access]
aws_iam_policy.glue_bicimad_data_access: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-bicimad-data-access]
aws_s3_object.procesamiento_source: Refreshing state... [id=glue-libs/procesamiento-41c225d658b2c0460396d681d7ef0062.zip]
aws_codebuild_project.lambda_dependencies_layer: Refreshing state... [id=arn:aws:codebuild:eu-west-1:222234418587:project/madrono-tfm-dev-lambda-dependencies-layer]
aws_iam_role_policy_attachment.glue_aforos_peatones_bicicletas_data_access: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-glue-role-20260817225242712100000009]
aws_iam_role_policy_attachment.athena_query: Refreshing state... [id=madrono-tfm-dev-athena-query-role-20260820014319117700000001]
aws_iam_role_policy_attachment.glue_bluesky_menciones_data_access: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-glue-role-2026081722524272500000000d]
aws_iam_role_policy_attachment.glue_transporte_publico_emt_data_access: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-glue-role-2026081607564024520000000b]
aws_iam_role_policy_attachment.glue_ruido_data_access: Refreshing state... [id=madrono-tfm-dev-ruido-glue-role-20260817225242694700000008]
aws_iam_role_policy_attachment.glue_aparcamientos_data_access: Refreshing state... [id=madrono-tfm-dev-aparcamientos-glue-role-20260816075639899700000008]
aws_iam_role_policy_attachment.glue_calidad_aire_data_access: Refreshing state... [id=madrono-tfm-dev-calidad-aire-glue-role-20260816075639853300000007]
aws_iam_role_policy_attachment.glue_cams_calidad_aire_data_access: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-glue-role-2026081722524272170000000c]
aws_iam_role_policy_attachment.glue_meteorologia_data_access: Refreshing state... [id=madrono-tfm-dev-meteorologia-glue-role-2026081607564030390000000c]
aws_s3_bucket_lifecycle_configuration.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_s3_bucket_lifecycle_configuration.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_iam_role_policy_attachment.glue_afluencia_lugares_data_access: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-glue-role-2026081722524275410000000e]
aws_s3_bucket_lifecycle_configuration.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_iam_role_policy_attachment.glue_trafico_data_access: Refreshing state... [id=madrono-tfm-dev-trafico-glue-role-2026081607564002340000000a]
aws_iam_role_policy_attachment.glue_cartelera_cines_estrenos_data_access: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-glue-role-2026081722524271210000000a]
aws_iam_role_policy_attachment.glue_aemet_prevision_avisos_data_access: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-glue-role-20260817225242985500000010]
aws_iam_policy.scheduler_invoke_lambda: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-scheduler-invoke-lambda]
aws_iam_role_policy_attachment.glue_agenda_eventos_data_access: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-glue-role-2026081722524290960000000f]
aws_iam_role_policy_attachment.ingestion_bronze_write: Refreshing state... [id=madrono-tfm-dev-ingestion-role-20260813160151981500000001]
aws_iam_role_policy_attachment.glue_bicimad_data_access: Refreshing state... [id=madrono-tfm-dev-bicimad-glue-role-20260816075639983400000009]
aws_iam_role_policy_attachment.scheduler_invoke_lambda: Refreshing state... [id=madrono-tfm-dev-scheduler-role-20260814213123137400000002]
aws_glue_job.aemet_prevision_avisos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-bronze-to-silver]
aws_glue_job.aparcamientos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-aparcamientos-bronze-to-silver]
aws_glue_job.meteorologia_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-meteorologia-silver-to-gold]
aws_glue_job.bicimad_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-bicimad-bronze-to-silver]
aws_glue_job.agenda_eventos_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-silver-backfill-dedup]
aws_glue_job.trafico_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-trafico-silver-to-gold]
aws_glue_job.aforos_peatones_bicicletas_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-bronze-to-silver]
aws_glue_job.agenda_eventos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-bronze-to-silver]
aws_glue_job.bluesky_menciones_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-silver-backfill-dedup]
aws_glue_job.cams_calidad_aire_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-bronze-to-silver]
aws_glue_job.bicimad_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-bicimad-silver-to-gold]
aws_glue_job.cartelera_cines_estrenos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-silver-to-gold]
aws_glue_job.transporte_publico_emt_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-bronze-to-silver]
aws_glue_job.trafico_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-trafico-bronze-to-silver]
aws_glue_job.ruido_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-ruido-silver-backfill-dedup]
aws_glue_job.cartelera_cines_estrenos_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-bronze-to-silver]
aws_glue_job.calidad_aire_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-calidad-aire-silver-to-gold]
aws_glue_job.cams_calidad_aire_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-silver-to-gold]
aws_glue_job.aparcamientos_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aparcamientos-silver-backfill-dedup]
aws_glue_job.bluesky_menciones_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-bronze-to-silver]
aws_glue_job.meteorologia_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-meteorologia-bronze-to-silver]
aws_glue_job.afluencia_lugares_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-silver-to-gold]
aws_glue_job.aparcamientos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-aparcamientos-silver-to-gold]
aws_glue_job.transporte_publico_emt_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-silver-backfill-dedup]
aws_glue_job.aemet_prevision_avisos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-silver-to-gold]
aws_glue_job.calidad_aire_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-calidad-aire-bronze-to-silver]
aws_glue_job.cams_calidad_aire_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-silver-backfill-dedup]
aws_glue_job.transporte_publico_emt_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-silver-to-gold]
aws_glue_job.agenda_eventos_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-silver-to-gold]
aws_glue_job.ruido_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-ruido-bronze-to-silver]
aws_glue_job.bicimad_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-bicimad-silver-backfill-dedup]
aws_glue_job.aforos_peatones_bicicletas_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-silver-to-gold]
aws_glue_job.aforos_peatones_bicicletas_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-silver-backfill-dedup]
aws_glue_job.calidad_aire_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-calidad-aire-silver-backfill-dedup]
aws_glue_job.meteorologia_silver_backfill_dedup: Refreshing state... [id=madrono-tfm-dev-meteorologia-silver-backfill-dedup]
aws_glue_job.ruido_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-ruido-silver-to-gold]
aws_glue_job.afluencia_lugares_bronze_to_silver: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-bronze-to-silver]
aws_glue_job.bluesky_menciones_silver_to_gold: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-silver-to-gold]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["transporte_publico_emt"]: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["aemet_prevision_avisos"]: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["bluesky_menciones"]: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["aforos_peatones_bicicletas"]: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["cams_calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["trafico"]: Refreshing state... [id=madrono-tfm-dev-trafico-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["afluencia_lugares"]: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["bicimad"]: Refreshing state... [id=madrono-tfm-dev-bicimad-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["aparcamientos"]: Refreshing state... [id=madrono-tfm-dev-aparcamientos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["ruido"]: Refreshing state... [id=madrono-tfm-dev-ruido-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["agenda_eventos"]: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_daily["cartelera_cines_estrenos"]: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-calidad-aire-scheduled-bronze-to-silver]
aws_glue_trigger.scheduled_bronze_to_silver_hourly["meteorologia"]: Refreshing state... [id=madrono-tfm-dev-meteorologia-scheduled-bronze-to-silver]
aws_glue_trigger.conditional_silver_to_gold_hourly["aparcamientos"]: Refreshing state... [id=madrono-tfm-dev-aparcamientos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["transporte_publico_emt"]: Refreshing state... [id=madrono-tfm-dev-transporte-publico-emt-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["ruido"]: Refreshing state... [id=madrono-tfm-dev-ruido-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["bicimad"]: Refreshing state... [id=madrono-tfm-dev-bicimad-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-calidad-aire-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["meteorologia"]: Refreshing state... [id=madrono-tfm-dev-meteorologia-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_hourly["trafico"]: Refreshing state... [id=madrono-tfm-dev-trafico-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["cartelera_cines_estrenos"]: Refreshing state... [id=madrono-tfm-dev-cartelera-cines-estrenos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["agenda_eventos"]: Refreshing state... [id=madrono-tfm-dev-agenda-eventos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["aemet_prevision_avisos"]: Refreshing state... [id=madrono-tfm-dev-aemet-prevision-avisos-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["bluesky_menciones"]: Refreshing state... [id=madrono-tfm-dev-bluesky-menciones-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["cams_calidad_aire"]: Refreshing state... [id=madrono-tfm-dev-cams-calidad-aire-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["afluencia_lugares"]: Refreshing state... [id=madrono-tfm-dev-afluencia-lugares-conditional-silver-to-gold]
aws_glue_trigger.conditional_silver_to_gold_daily["aforos_peatones_bicicletas"]: Refreshing state... [id=madrono-tfm-dev-aforos-peatones-bicicletas-conditional-silver-to-gold]

Terraform used the selected providers to generate the following execution
plan. Resource actions are indicated with the following symbols:
  + create
  ~ update in-place
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
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["afluencia_lugares"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-afluencia_lugares"
      ~ last_modified                  = "2026-08-15T17:45:29.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["aforos_peatones_bicicletas"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-aforos_peatones_bicicletas"
      ~ last_modified                  = "2026-08-15T17:45:53.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["agenda_eventos"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-agenda_eventos"
      ~ last_modified                  = "2026-08-15T17:45:59.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["aparcamientos"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-aparcamientos"
      ~ last_modified                  = "2026-08-15T17:46:10.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["bicimad"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-bicimad"
      ~ last_modified                  = "2026-08-15T17:46:05.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["bluesky_menciones"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-bluesky_menciones"
      ~ last_modified                  = "2026-08-15T17:45:17.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["calidad_aire"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-calidad_aire"
      ~ last_modified                  = "2026-08-15T17:45:23.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["cams_calidad_aire"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-cams_calidad_aire"
      ~ last_modified                  = "2026-08-16T00:25:07.000+0000" -> (known after apply)
      ~ source_code_hash               = "d7EQu1dgphlitciVE2HTKx/chix5s+vz4rA/a0fWr+Q=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["cartelera_cines_estrenos"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-cartelera_cines_estrenos"
      ~ last_modified                  = "2026-08-15T17:45:47.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["meteorologia"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-meteorologia"
      ~ last_modified                  = "2026-08-15T17:44:59.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["ruido"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-ruido"
      ~ last_modified                  = "2026-08-15T17:45:11.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["trafico"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-trafico"
      ~ last_modified                  = "2026-08-15T17:46:16.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
    }

  # aws_lambda_function.producer["transporte_publico_emt"] will be updated in-place
  ~ resource "aws_lambda_function" "producer" {
        id                             = "madrono-tfm-dev-transporte_publico_emt"
      ~ last_modified                  = "2026-08-15T17:45:05.000+0000" -> (known after apply)
      ~ source_code_hash               = "5+JhQ/Yo615NRbC0wNoddfmEGgfaLxjhVerQYW6Gg+k=" -> "RkVNCoExK65F+bIGfZT5ZoKf643td60jrlOG+rJncj0="
        tags                           = {}
        # (27 unchanged attributes hidden)

        # (4 unchanged blocks hidden)
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

Plan: 5 to add, 15 to change, 0 to destroy.

Changes to Outputs:
  + kafka_instance_id                      = (known after apply)
  + kafka_instance_private_ip              = (known after apply)
  + kafka_security_group_id                = (known after apply)

─────────────────────────────────────────────────────────────────────────────

Saved the plan to: /tmp/plan088b.tfplan

To perform exactly these actions, run the following command to apply:
    terraform apply "/tmp/plan088b.tfplan"

```

El fichero de plan binario (`/tmp/plan088b.tfplan`) es un artefacto local efímero de esta
sesión (gitignored, `*.tfplan`), no se ha commiteado ni persiste — la tarea siguiente que
aplique debe generar su propio `terraform plan` antes de `apply`, no reutilizar este.
