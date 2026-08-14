# 029 — Terraform: Lambda + EventBridge Scheduler para los productores (plan, sin aplicar)

## Qué se implementó

Quinto paso hacia producción, tras la 025 (`BronzeWriter` con soporte S3) y los
lotes 026/027/028 (`lambda_handler` por productor). Esta tarea añade a
`infra/terraform/` (mismo proyecto que la 001/014/015, no uno aparte) el
Terraform que despliega los **14 productores** que ya tienen `lambda_handler`
como funciones `aws_lambda_function`, cada una con su propio schedule real de
`aws_scheduler_schedule` (EventBridge Scheduler), y genera el `terraform plan`
completo — **sin ejecutar `terraform apply`**, tal como pedía el enunciado
(el `apply` queda para la tarea 030, tras revisión humana de este plan).

Fichero nuevo: `infra/terraform/lambda.tf`. Ficheros ampliados: `versions.tf`
(provider `hashicorp/archive`, para construir el .zip de despliegue),
`variables.tf` (runtime/timeout/memoria/retención de logs por defecto, ARN
opcional de una futura layer de dependencias, placeholder de secretos),
`outputs.tf` (nombres/ARNs de las funciones, nombres de los schedules, ARN
del rol de scheduler, nombres —no valores— de los parámetros SSM).
`main.tf` **no se ha tocado**: el rol de ingesta (`aws_iam_role.ingestion`,
tareas 001/015) se amplía únicamente con una policy adicional, no se
modifica el recurso en sí.

## Diseño: `local.producers` (14) + `local.schedules` (20), dos mapas con `for_each`

El enunciado sugiere "una entrada por fila de la tabla" para un único mapa que
alimente tanto la función Lambda como su schedule. Se usan **dos** mapas en su
lugar, por una razón ya decidida en la tarea 028 y que este Terraform debe
respetar: `aemet_prevision_avisos.py` implementa un **único**
`lambda_handler` que atiende tanto "avisos" como "previsión" según
`event.get("tipo")`, precisamente para no duplicar función/rol IAM entre las
dos cadencias reales de AEMET. Si la tabla de 15 filas (14 productores + la
fila extra de `aemet_prevision` separada de `aemet_avisos`) se hubiera
llevado a un único mapa 1:1 función↔schedule, habría forzado crear una
segunda función Lambda idéntica solo para tener un segundo schedule —
contradiciendo esa decisión ya tomada. Además, `cams_calidad_aire` tiene 2
schedules (07:15 y 09:00 UTC) sobre la misma función, y `aemet_prevision_avisos`
tiene 6 (4 avisos + 2 previsión).

Por eso:

- **`local.producers`** (`infra/terraform/lambda.tf`): 14 entradas, una por
  módulo con `lambda_handler` (`trafico`, `transporte_publico_emt`, `bicimad`,
  `aparcamientos`, `calidad_aire`, `meteorologia`, `ruido`,
  `afluencia_lugares`, `aforos_peatones_bicicletas`, `bluesky_menciones`,
  `agenda_eventos`, `aemet_prevision_avisos`, `cams_calidad_aire`,
  `cartelera_cines_estrenos`). Alimenta `aws_lambda_function.producer`
  (`for_each`).
- **`local.schedules`** (20 entradas): una por regla real de EventBridge
  Scheduler, cada una con `producer_key` apuntando a una clave de
  `local.producers`. Alimenta `aws_scheduler_schedule.producer` (`for_each`).
  12 productores tienen 1 schedule 1:1; `aemet_prevision_avisos` tiene 6
  (`aemet_avisos_0800/1100/1800/2350` con `input={"tipo":"avisos"}` y
  `aemet_prevision_0700/1400` con `input={"tipo":"prevision"}`);
  `cams_calidad_aire` tiene 2 (`cams_0715_utc`, `cams_0900_utc`).

Ningún bloque de recurso se repite a mano: 58 recursos en total, todos vía
`for_each` sobre estos dos mapas (o sobre `local.secrets`, ver más abajo).

## Cadencias aplicadas

Tal como especificaba el enunciado (no reinventadas): `rate(5 minutes)` para
trafico/EMT/BiciMAD, `rate(15 minutes)` para aparcamientos, `cron(15,35,55 * *
* ? *)` con `ScheduleExpressionTimezone = "Europe/Madrid"` para calidad del
aire y meteorología, `cron(0 7 ? * MON-FRI *)` (Madrid) para ruido,
`cron(0 6 ? * MON *)` (Madrid) semanal para afluencia, `cron(0 6 1 * ? *)`
(Madrid) mensual para aforos, `rate(1 hour)` para Bluesky, `cron(0 6 * * ? *)`
(Madrid) diario para agenda de eventos, 4 schedules Madrid para avisos AEMET
(08:00/11:00/18:00/23:50), 2 para previsión AEMET (07:00/14:00), 2 schedules
en **UTC explícito** para CAMS (07:15/09:00, tras las tandas reales de CAMS a
las 06:45/08:30 UTC), y `cron(0 8 * * ? *)` (Madrid) diario para cartelera de
cines. Las expresiones `rate(...)` no dependen de zona horaria; se deja
`schedule_expression_timezone = null` para esas (el proveedor usa su valor
por defecto, sin efecto real sobre un `rate`).

## Empaquetado: código fuente sí, dependencias de terceros no (decisión y motivo)

- **Código**: `data.archive_file.ingesta_source` construye un único .zip a
  partir de `ingesta/` (excluyendo `tests/` y `capturas/samples/`), **~140 KB**
  reales tras excluir esos directorios — reutilizado como `filename` de las
  14 funciones; solo cambia el `handler` (`ingesta.capturas.<módulo>.lambda_handler`)
  por función. `boto3` no se empaqueta (ya está en el runtime de Lambda,
  como ya asumía `bronze.py` desde la tarea 025).
- **Dependencias de terceros** (`ingesta/requirements.txt`: `requests`,
  `beautifulsoup4`, `cdsapi`, `netCDF4`, `populartimes`) **NO se han
  empaquetado en esta tarea**. Motivo: esta EC2 tiene muy poco disco libre
  (~2 GB al empezar la tarea, compartido con el resto del pipeline;
  `terraform init` ya consume ~700 MB solo en el provider de AWS). Construir
  una Lambda Layer con paquetes que incluyen extensiones compiladas
  (`netCDF4` en particular) requiere una herramienta de build compatible con
  el runtime de Lambda (Docker + imagen `manylinux`, o AWS SAM/CodeBuild),
  no un `pip install` directo en esta máquina — hacerlo aquí sin esa
  herramienta arriesgaría binarios incompatibles con Lambda además de
  agotar el disco. Se deja como paso pendiente, explícito, antes de que la
  tarea 030 (`apply`) despliegue algo realmente funcional:
  `variable "lambda_dependencies_layer_arn"` (default `null`) — cuando
  exista esa layer, basta con fijar su ARN en `terraform.tfvars` y
  aplicar; ninguna función lleva layer todavía (`layers = []` en el plan).
  **Con esto, las funciones Lambda que ya se desplegasen tal cual no
  ejecutarían correctamente** (fallarían al importar `requests` u otras
  dependencias) — es una limitación conocida y documentada, no un olvido:
  el alcance de esta tarea es el `plan`, no un despliegue funcional
  completo.

## Permisos IAM añadidos

- **Rol de ingesta existente** (`aws_iam_role.ingestion`, tareas 001/015,
  **no modificado como recurso**): se le adjunta una policy nueva
  (`aws_iam_policy.ingestion_lambda_logs` +
  `aws_iam_role_policy_attachment.ingestion_lambda_logs`) con
  `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`,
  acotada exactamente a los 14 log groups de estas funciones
  (`aws_cloudwatch_log_group.producer`, uno por función, con
  `retention_in_days = var.lambda_log_retention_days` = 14 días por
  defecto, para no acumular logs indefinidamente). Nada más se le añade a
  este rol: sigue sin poder leer/borrar en Bronze ni acceder a
  Silver/Gold.
- **Rol nuevo `aws_iam_role.scheduler`**: distinto del rol de ejecución de
  las Lambdas, con `scheduler.amazonaws.com` como único principal de
  confianza y una policy (`aws_iam_policy.scheduler_invoke_lambda`) que
  permite `lambda:InvokeFunction` **únicamente** sobre los ARN exactos de
  las 14 funciones de esta tarea (lista generada desde
  `aws_lambda_function.producer`, no un wildcard).

## Secretos: SSM Parameter Store, placeholder gestionado por Terraform, valor real fuera de git

4 productores necesitan una credencial que no vive en este repositorio
(`transporte_publico_emt`: `EMT_CLIENT_ID`/`EMT_PASS_KEY`, ya usados desde la
tarea 024; `afluencia_lugares`: `GOOGLE_MAPS_API_KEY`, bloqueo documentado
desde la tarea 012; `aemet_prevision_avisos`: `AEMET_API_KEY`, tarea 018;
`cams_calidad_aire`: `CAMS_ADS_API_KEY`, tarea 019). Decisión: **SSM
Parameter Store**, no Secrets Manager (más simple y sin coste adicional para
5 parámetros de solo lectura, frente al coste por secreto de Secrets
Manager) — `aws_ssm_parameter.secrets`, `for_each` sobre `local.secrets` (5
entradas, un parámetro `SecureString` por credencial, nombrados
`/madrono-tfm/dev/secrets/<nombre>`).

Cada parámetro se crea con el valor de `var.ssm_secret_placeholder_value`
(por defecto la cadena literal `"CHANGEME-SET-MANUALLY-OUTSIDE-TERRAFORM"`,
**no un secreto real** — ninguna credencial real aparece en ningún fichero
`.tf` ni en este documento) y `lifecycle { ignore_changes = [value] }`: tras
el primer `apply` (tarea 030), alguien con las credenciales reales las fija
a mano (`aws ssm put-parameter --name ... --value <real> --overwrite`), fuera
de git y fuera del control de Terraform; los `apply` siguientes no las
pisan con el placeholder. Cada función Lambda que necesita una credencial
referencia directamente `aws_ssm_parameter.secrets[<nombre>].value` como
variable de entorno (mismo nombre que ya lee `os.environ` en el módulo
correspondiente, p.ej. `EMT_CLIENT_ID`) — no hace falta que el código de
`ingesta/` cambie ni llame a SSM en tiempo de ejecución, ni se le da permiso
IAM de `ssm:GetParameter` a la función (no lo necesita con este diseño). La
variable `var.ssm_secret_placeholder_value` está marcada `sensitive = true`
en `variables.tf`; por eso el plan de más abajo muestra `(sensitive value)`
en vez del placeholder en los bloques `environment` de las 4 funciones
afectadas y en el propio `aws_ssm_parameter.secrets[*].value` — no es un
secreto real oculto, es el placeholder no imprimido por diseño.

## Verificación en AWS real (alcance de esta tarea: solo lectura + `init`/`plan`)

Se ejecutaron, en este orden, únicamente comandos de solo lectura y
`terraform init`/`plan` (permitidos explícitamente por el `allow_infra_apply`
de esta tarea) contra la cuenta AWS real (`222234418587`, región
`eu-west-1`), reutilizando el backend remoto (bucket `madrono-tfm-terraform-state`,
tabla de locking `madrono-tfm-terraform-locks`) y el mismo `state` del
lakehouse ya aplicado (tarea 015):

```bash
aws sts get-caller-identity            # confirma el rol de instancia madrono-terraform-deployerEC2
aws s3api head-bucket --bucket madrono-tfm-terraform-state --region eu-west-1
aws dynamodb describe-table --table-name madrono-tfm-terraform-locks --region eu-west-1

cd infra/terraform
cp backend.hcl.example backend.hcl              # no commiteado, gitignored
cp terraform.tfvars.example terraform.tfvars    # no commiteado, gitignored
terraform init -backend-config=backend.hcl
terraform validate
terraform plan -var-file=terraform.tfvars
```

`terraform init` se completó sin error (mismo warning no bloqueante que en la
tarea 014 sobre `dynamodb_table` deprecado, no se ha tocado `versions.tf` en
ese punto por estar fuera de alcance). `terraform validate` confirmó
`Success! The configuration is valid.`. `terraform plan` se completó **sin
error**, refrescando el estado real de los 3 buckets del lakehouse y del rol
de ingesta (ya aplicados desde la tarea 015 — el plan los lee, no los toca:
**0 to change** sobre ellos) y proponiendo exactamente:

```
Plan: 58 to add, 0 to change, 0 to destroy.
```

Desglose de los 58 recursos nuevos (verificado contando cada bloque del plan,
no solo el resumen): 14 `aws_lambda_function.producer`, 20
`aws_scheduler_schedule.producer`, 14 `aws_cloudwatch_log_group.producer`, 5
`aws_ssm_parameter.secrets`, y 5 recursos IAM
(`aws_iam_role.scheduler`, `aws_iam_policy.ingestion_lambda_logs`,
`aws_iam_policy.scheduler_invoke_lambda`,
`aws_iam_role_policy_attachment.ingestion_lambda_logs`,
`aws_iam_role_policy_attachment.scheduler_invoke_lambda`) = 14+20+14+5+5 = 58.

**No se ha ejecutado `terraform apply` en ningún momento de esta tarea.**
Tampoco se ha creado, modificado ni destruido ningún recurso real en AWS: el
único efecto de los comandos anteriores es la lectura (`init`/`plan`/`validate`
y los comandos `aws ...` de solo lectura) contra infraestructura ya existente.
Los ficheros `backend.hcl`, `terraform.tfvars`, `.terraform/` y
`infra/terraform/build/ingesta_source.zip` generados durante la verificación
son gitignored y se han eliminado del disco de esta EC2 al terminar la tarea
(no aportan nada persistente; la tarea 030 los regenerará igual que aquí al
ejecutar su propio `init`/`plan`/`apply`).

## Salida completa de `terraform plan -var-file=terraform.tfvars`

```

Warning: Deprecated Parameter

The parameter "dynamodb_table" is deprecated. Use parameter "use_lockfile"
instead.
data.archive_file.ingesta_source: Reading...
data.archive_file.ingesta_source: Read complete after 0s [id=765b9e52035816d019d44020c3ced1d151f8e22d]
data.aws_iam_policy_document.ingestion_assume_role: Reading...
data.aws_caller_identity.current: Reading...
data.aws_iam_policy_document.ingestion_assume_role: Read complete after 0s [id=2690255455]
aws_iam_role.ingestion: Refreshing state... [id=madrono-tfm-dev-ingestion-role]
data.aws_iam_policy_document.scheduler_assume_role: Reading...
data.aws_iam_policy_document.scheduler_assume_role: Read complete after 0s [id=52247394]
data.aws_caller_identity.current: Read complete after 0s [id=222234418587]
aws_s3_bucket.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_s3_bucket.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
data.aws_iam_policy_document.bucket_policy["bronze"]: Reading...
data.aws_iam_policy_document.bucket_policy["silver"]: Reading...
data.aws_iam_policy_document.bucket_policy["gold"]: Reading...
data.aws_iam_policy_document.ingestion_bronze_write: Reading...
data.aws_iam_policy_document.ingestion_bronze_write: Read complete after 0s [id=175239690]
aws_s3_bucket_public_access_block.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
data.aws_iam_policy_document.bucket_policy["gold"]: Read complete after 0s [id=1014628649]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
data.aws_iam_policy_document.bucket_policy["bronze"]: Read complete after 0s [id=42177744]
aws_s3_bucket_public_access_block.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_s3_bucket_versioning.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_s3_bucket_public_access_block.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_versioning.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
data.aws_iam_policy_document.bucket_policy["silver"]: Read complete after 0s [id=168412883]
aws_s3_bucket_server_side_encryption_configuration.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_s3_bucket_versioning.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_iam_policy.ingestion_bronze_write: Refreshing state... [id=arn:aws:iam::222234418587:policy/madrono-tfm-dev-ingestion-bronze-write]
aws_s3_bucket_policy.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_policy.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_s3_bucket_policy.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]
aws_iam_role_policy_attachment.ingestion_bronze_write: Refreshing state... [id=madrono-tfm-dev-ingestion-role-20260813160151981500000001]
aws_s3_bucket_lifecycle_configuration.lakehouse["silver"]: Refreshing state... [id=madrono-tfm-dev-silver-222234418587]
aws_s3_bucket_lifecycle_configuration.lakehouse["gold"]: Refreshing state... [id=madrono-tfm-dev-gold-222234418587]
aws_s3_bucket_lifecycle_configuration.lakehouse["bronze"]: Refreshing state... [id=madrono-tfm-dev-bronze-222234418587]

Terraform used the selected providers to generate the following execution
plan. Resource actions are indicated with the following symbols:
  + create
 <= read (data resources)

Terraform will perform the following actions:

  # data.aws_iam_policy_document.ingestion_lambda_logs will be read during apply
  # (config refers to values not yet known)
 <= data "aws_iam_policy_document" "ingestion_lambda_logs" {
      + id            = (known after apply)
      + json          = (known after apply)
      + minified_json = (known after apply)

      + statement {
          + actions   = [
              + "logs:CreateLogGroup",
              + "logs:CreateLogStream",
              + "logs:PutLogEvents",
            ]
          + effect    = "Allow"
          + resources = [
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
            ]
          + sid       = "WriteProducerLambdaLogs"
        }
    }

  # data.aws_iam_policy_document.scheduler_invoke_lambda will be read during apply
  # (config refers to values not yet known)
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
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
              + (known after apply),
            ]
          + sid       = "InvokeProducerLambdas"
        }
    }

  # aws_cloudwatch_log_group.producer["aemet_prevision_avisos"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-aemet_prevision_avisos"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["afluencia_lugares"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-afluencia_lugares"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["aforos_peatones_bicicletas"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-aforos_peatones_bicicletas"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["agenda_eventos"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-agenda_eventos"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["aparcamientos"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-aparcamientos"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["bicimad"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-bicimad"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["bluesky_menciones"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-bluesky_menciones"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["calidad_aire"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-calidad_aire"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["cams_calidad_aire"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-cams_calidad_aire"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["cartelera_cines_estrenos"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-cartelera_cines_estrenos"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["meteorologia"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-meteorologia"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["ruido"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-ruido"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["trafico"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-trafico"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_cloudwatch_log_group.producer["transporte_publico_emt"] will be created
  + resource "aws_cloudwatch_log_group" "producer" {
      + arn               = (known after apply)
      + id                = (known after apply)
      + log_group_class   = (known after apply)
      + name              = "/aws/lambda/madrono-tfm-dev-transporte_publico_emt"
      + name_prefix       = (known after apply)
      + retention_in_days = 14
      + skip_destroy      = false
      + tags_all          = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_iam_policy.ingestion_lambda_logs will be created
  + resource "aws_iam_policy" "ingestion_lambda_logs" {
      + arn              = (known after apply)
      + attachment_count = (known after apply)
      + description      = "Permite a las funciones Lambda de productores escribir en sus propios log groups de CloudWatch Logs (tarea 029)."
      + id               = (known after apply)
      + name             = "madrono-tfm-dev-ingestion-lambda-logs"
      + name_prefix      = (known after apply)
      + path             = "/"
      + policy           = (known after apply)
      + policy_id        = (known after apply)
      + tags_all         = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_iam_policy.scheduler_invoke_lambda will be created
  + resource "aws_iam_policy" "scheduler_invoke_lambda" {
      + arn              = (known after apply)
      + attachment_count = (known after apply)
      + description      = "Permite a EventBridge Scheduler invocar exclusivamente las funciones Lambda de productores de esta tarea."
      + id               = (known after apply)
      + name             = "madrono-tfm-dev-scheduler-invoke-lambda"
      + name_prefix      = (known after apply)
      + path             = "/"
      + policy           = (known after apply)
      + policy_id        = (known after apply)
      + tags_all         = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
    }

  # aws_iam_role.scheduler will be created
  + resource "aws_iam_role" "scheduler" {
      + arn                   = (known after apply)
      + assume_role_policy    = jsonencode(
            {
              + Statement = [
                  + {
                      + Action    = "sts:AssumeRole"
                      + Effect    = "Allow"
                      + Principal = {
                          + Service = "scheduler.amazonaws.com"
                        }
                    },
                ]
              + Version   = "2012-10-17"
            }
        )
      + create_date           = (known after apply)
      + description           = "Rol asumido por EventBridge Scheduler para invocar las funciones Lambda de productores (tarea 029)."
      + force_detach_policies = false
      + id                    = (known after apply)
      + managed_policy_arns   = (known after apply)
      + max_session_duration  = 3600
      + name                  = "madrono-tfm-dev-scheduler-role"
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

  # aws_iam_role_policy_attachment.ingestion_lambda_logs will be created
  + resource "aws_iam_role_policy_attachment" "ingestion_lambda_logs" {
      + id         = (known after apply)
      + policy_arn = (known after apply)
      + role       = "madrono-tfm-dev-ingestion-role"
    }

  # aws_iam_role_policy_attachment.scheduler_invoke_lambda will be created
  + resource "aws_iam_role_policy_attachment" "scheduler_invoke_lambda" {
      + id         = (known after apply)
      + policy_arn = (known after apply)
      + role       = "madrono-tfm-dev-scheduler-role"
    }

  # aws_lambda_function.producer["aemet_prevision_avisos"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Previsión/avisos AEMET Madrid; decide dataset según event.tipo -> Bronze/aemet_prevision o Bronze/aemet_avisos"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-aemet_prevision_avisos"
      + handler                        = "ingesta.capturas.aemet_prevision_avisos.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 60
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "AEMET_API_KEY"    = (sensitive value)
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["afluencia_lugares"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Patrón típico de afluencia de lugares (Google Popular Times) -> Bronze/afluencia_lugares_patron_tipico"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-afluencia_lugares"
      + handler                        = "ingesta.capturas.afluencia_lugares_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 300
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH"    = "s3://madrono-tfm-dev-bronze-222234418587/"
              + "GOOGLE_MAPS_API_KEY" = (sensitive value)
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["aforos_peatones_bicicletas"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Aforos de peatones/bicicletas de Madrid (último día disponible) -> Bronze/aforos_peatones_bicicletas"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-aforos_peatones_bicicletas"
      + handler                        = "ingesta.capturas.aforos_peatones_bicicletas_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 120
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["agenda_eventos"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Agenda de eventos municipal + esMadrid (captura completa) -> Bronze/agenda_eventos"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-agenda_eventos"
      + handler                        = "ingesta.capturas.agenda_eventos_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 180
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["aparcamientos"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Ocupación de aparcamientos de Madrid (SOAP, 1 llamada por aparcamiento) -> Bronze/aparcamientos"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-aparcamientos"
      + handler                        = "ingesta.capturas.aparcamientos_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 180
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["bicimad"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Estado de estaciones BiciMAD (GBFS) -> Bronze/bicimad"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-bicimad"
      + handler                        = "ingesta.capturas.bicimad.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 60
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["bluesky_menciones"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Barrido de menciones de Bluesky por distrito/evento -> Bronze/bluesky_menciones"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-bluesky_menciones"
      + handler                        = "ingesta.capturas.bluesky_menciones_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 180
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["calidad_aire"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Calidad del aire de Madrid (estaciones municipales) -> Bronze/calidad_aire"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-calidad_aire"
      + handler                        = "ingesta.capturas.calidad_aire_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 60
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["cams_calidad_aire"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Previsión de calidad del aire UE (Copernicus CAMS, NetCDF) -> Bronze/cams_calidad_aire"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-cams_calidad_aire"
      + handler                        = "ingesta.capturas.cams_calidad_aire_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 512
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 600
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
              + "CAMS_ADS_API_KEY" = (sensitive value)
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["cartelera_cines_estrenos"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Barrido de estrenos de cartelera de cines de Madrid (SensaCine) -> Bronze/cartelera_cines_estrenos"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-cartelera_cines_estrenos"
      + handler                        = "ingesta.capturas.cartelera_cines_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 180
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["meteorologia"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Meteorología de Madrid (estaciones municipales) -> Bronze/meteorologia"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-meteorologia"
      + handler                        = "ingesta.capturas.meteorologia_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 60
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["ruido"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Ruido de Madrid (estaciones municipales, último día disponible) -> Bronze/ruido"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-ruido"
      + handler                        = "ingesta.capturas.ruido_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 60
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["trafico"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Intensidad de tráfico de Madrid (Informo) -> Bronze/trafico"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-trafico"
      + handler                        = "ingesta.capturas.trafico_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 60
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_lambda_function.producer["transporte_publico_emt"] will be created
  + resource "aws_lambda_function" "producer" {
      + architectures                  = (known after apply)
      + arn                            = (known after apply)
      + code_sha256                    = (known after apply)
      + description                    = "Llegadas EMT Madrid (MobilityLabs) -> Bronze/transporte_publico_emt"
      + filename                       = "./build/ingesta_source.zip"
      + function_name                  = "madrono-tfm-dev-transporte_publico_emt"
      + handler                        = "ingesta.capturas.transporte_publico_madrid.lambda_handler"
      + id                             = (known after apply)
      + invoke_arn                     = (known after apply)
      + last_modified                  = (known after apply)
      + layers                         = []
      + memory_size                    = 256
      + package_type                   = "Zip"
      + publish                        = false
      + qualified_arn                  = (known after apply)
      + qualified_invoke_arn           = (known after apply)
      + reserved_concurrent_executions = -1
      + role                           = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
      + runtime                        = "python3.13"
      + signing_job_arn                = (known after apply)
      + signing_profile_version_arn    = (known after apply)
      + skip_destroy                   = false
      + source_code_hash               = "fLtynYEXqwFMjfgLgyg5W9KP9q16S3vQdyVbACBZFh0="
      + source_code_size               = (known after apply)
      + tags_all                       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + timeout                        = 30
      + version                        = (known after apply)

      + environment {
          + variables = {
              + "BRONZE_BASE_PATH" = "s3://madrono-tfm-dev-bronze-222234418587/"
              + "EMT_CLIENT_ID"    = (sensitive value)
              + "EMT_PASS_KEY"     = (sensitive value)
            }
        }

      + ephemeral_storage (known after apply)

      + logging_config (known after apply)

      + tracing_config (known after apply)
    }

  # aws_scheduler_schedule.producer["aemet_avisos_0800"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-aemet_avisos_0800"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(0 8 * * ? *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + input    = jsonencode(
                {
                  + tipo = "avisos"
                }
            )
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["aemet_avisos_1100"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-aemet_avisos_1100"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(0 11 * * ? *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + input    = jsonencode(
                {
                  + tipo = "avisos"
                }
            )
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["aemet_avisos_1800"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-aemet_avisos_1800"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(0 18 * * ? *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + input    = jsonencode(
                {
                  + tipo = "avisos"
                }
            )
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["aemet_avisos_2350"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-aemet_avisos_2350"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(50 23 * * ? *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + input    = jsonencode(
                {
                  + tipo = "avisos"
                }
            )
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["aemet_prevision_0700"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-aemet_prevision_0700"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(0 7 * * ? *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + input    = jsonencode(
                {
                  + tipo = "prevision"
                }
            )
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["aemet_prevision_1400"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-aemet_prevision_1400"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(0 14 * * ? *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + input    = jsonencode(
                {
                  + tipo = "prevision"
                }
            )
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["afluencia_lugares"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-afluencia_lugares"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(0 6 ? * MON *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["aforos_peatones_bicicletas"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-aforos_peatones_bicicletas"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(0 6 1 * ? *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["agenda_eventos"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-agenda_eventos"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(0 6 * * ? *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["aparcamientos"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-aparcamientos"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "rate(15 minutes)"
      + schedule_expression_timezone = "UTC"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["bicimad"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-bicimad"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "rate(5 minutes)"
      + schedule_expression_timezone = "UTC"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["bluesky_menciones"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-bluesky_menciones"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "rate(1 hour)"
      + schedule_expression_timezone = "UTC"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["calidad_aire"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-calidad_aire"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(15,35,55 * * * ? *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["cams_0715_utc"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-cams_0715_utc"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(15 7 * * ? *)"
      + schedule_expression_timezone = "UTC"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["cams_0900_utc"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-cams_0900_utc"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(0 9 * * ? *)"
      + schedule_expression_timezone = "UTC"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["cartelera_cines_estrenos"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-cartelera_cines_estrenos"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(0 8 * * ? *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["emt_llegadas"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-emt_llegadas"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "rate(5 minutes)"
      + schedule_expression_timezone = "UTC"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["meteorologia"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-meteorologia"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(15,35,55 * * * ? *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["ruido"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-ruido"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "cron(0 7 ? * MON-FRI *)"
      + schedule_expression_timezone = "Europe/Madrid"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_scheduler_schedule.producer["trafico"] will be created
  + resource "aws_scheduler_schedule" "producer" {
      + arn                          = (known after apply)
      + group_name                   = (known after apply)
      + id                           = (known after apply)
      + name                         = "madrono-tfm-dev-trafico"
      + name_prefix                  = (known after apply)
      + schedule_expression          = "rate(5 minutes)"
      + schedule_expression_timezone = "UTC"
      + state                        = "ENABLED"

      + flexible_time_window {
          + mode = "OFF"
        }

      + target {
          + arn      = (known after apply)
          + role_arn = (known after apply)
        }
    }

  # aws_ssm_parameter.secrets["AEMET_API_KEY"] will be created
  + resource "aws_ssm_parameter" "secrets" {
      + arn            = (known after apply)
      + data_type      = (known after apply)
      + description    = "Placeholder gestionado por Terraform para AEMET_API_KEY (tarea 029). Valor real fijado manualmente fuera de git; ver variables.tf."
      + has_value_wo   = (known after apply)
      + id             = (known after apply)
      + insecure_value = (known after apply)
      + key_id         = (known after apply)
      + name           = "/madrono-tfm/dev/secrets/aemet-api-key"
      + tags_all       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + tier           = (known after apply)
      + type           = "SecureString"
      + value          = (sensitive value)
      + value_wo       = (write-only attribute)
      + version        = (known after apply)
    }

  # aws_ssm_parameter.secrets["CAMS_ADS_API_KEY"] will be created
  + resource "aws_ssm_parameter" "secrets" {
      + arn            = (known after apply)
      + data_type      = (known after apply)
      + description    = "Placeholder gestionado por Terraform para CAMS_ADS_API_KEY (tarea 029). Valor real fijado manualmente fuera de git; ver variables.tf."
      + has_value_wo   = (known after apply)
      + id             = (known after apply)
      + insecure_value = (known after apply)
      + key_id         = (known after apply)
      + name           = "/madrono-tfm/dev/secrets/cams-ads-api-key"
      + tags_all       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + tier           = (known after apply)
      + type           = "SecureString"
      + value          = (sensitive value)
      + value_wo       = (write-only attribute)
      + version        = (known after apply)
    }

  # aws_ssm_parameter.secrets["EMT_CLIENT_ID"] will be created
  + resource "aws_ssm_parameter" "secrets" {
      + arn            = (known after apply)
      + data_type      = (known after apply)
      + description    = "Placeholder gestionado por Terraform para EMT_CLIENT_ID (tarea 029). Valor real fijado manualmente fuera de git; ver variables.tf."
      + has_value_wo   = (known after apply)
      + id             = (known after apply)
      + insecure_value = (known after apply)
      + key_id         = (known after apply)
      + name           = "/madrono-tfm/dev/secrets/emt-client-id"
      + tags_all       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + tier           = (known after apply)
      + type           = "SecureString"
      + value          = (sensitive value)
      + value_wo       = (write-only attribute)
      + version        = (known after apply)
    }

  # aws_ssm_parameter.secrets["EMT_PASS_KEY"] will be created
  + resource "aws_ssm_parameter" "secrets" {
      + arn            = (known after apply)
      + data_type      = (known after apply)
      + description    = "Placeholder gestionado por Terraform para EMT_PASS_KEY (tarea 029). Valor real fijado manualmente fuera de git; ver variables.tf."
      + has_value_wo   = (known after apply)
      + id             = (known after apply)
      + insecure_value = (known after apply)
      + key_id         = (known after apply)
      + name           = "/madrono-tfm/dev/secrets/emt-pass-key"
      + tags_all       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + tier           = (known after apply)
      + type           = "SecureString"
      + value          = (sensitive value)
      + value_wo       = (write-only attribute)
      + version        = (known after apply)
    }

  # aws_ssm_parameter.secrets["GOOGLE_MAPS_API_KEY"] will be created
  + resource "aws_ssm_parameter" "secrets" {
      + arn            = (known after apply)
      + data_type      = (known after apply)
      + description    = "Placeholder gestionado por Terraform para GOOGLE_MAPS_API_KEY (tarea 029). Valor real fijado manualmente fuera de git; ver variables.tf."
      + has_value_wo   = (known after apply)
      + id             = (known after apply)
      + insecure_value = (known after apply)
      + key_id         = (known after apply)
      + name           = "/madrono-tfm/dev/secrets/google-maps-api-key"
      + tags_all       = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + tier           = (known after apply)
      + type           = "SecureString"
      + value          = (sensitive value)
      + value_wo       = (write-only attribute)
      + version        = (known after apply)
    }

Plan: 58 to add, 0 to change, 0 to destroy.

Changes to Outputs:
  + producer_lambda_function_arns  = {
      + aemet_prevision_avisos     = (known after apply)
      + afluencia_lugares          = (known after apply)
      + aforos_peatones_bicicletas = (known after apply)
      + agenda_eventos             = (known after apply)
      + aparcamientos              = (known after apply)
      + bicimad                    = (known after apply)
      + bluesky_menciones          = (known after apply)
      + calidad_aire               = (known after apply)
      + cams_calidad_aire          = (known after apply)
      + cartelera_cines_estrenos   = (known after apply)
      + meteorologia               = (known after apply)
      + ruido                      = (known after apply)
      + trafico                    = (known after apply)
      + transporte_publico_emt     = (known after apply)
    }
  + producer_lambda_function_names = {
      + aemet_prevision_avisos     = "madrono-tfm-dev-aemet_prevision_avisos"
      + afluencia_lugares          = "madrono-tfm-dev-afluencia_lugares"
      + aforos_peatones_bicicletas = "madrono-tfm-dev-aforos_peatones_bicicletas"
      + agenda_eventos             = "madrono-tfm-dev-agenda_eventos"
      + aparcamientos              = "madrono-tfm-dev-aparcamientos"
      + bicimad                    = "madrono-tfm-dev-bicimad"
      + bluesky_menciones          = "madrono-tfm-dev-bluesky_menciones"
      + calidad_aire               = "madrono-tfm-dev-calidad_aire"
      + cams_calidad_aire          = "madrono-tfm-dev-cams_calidad_aire"
      + cartelera_cines_estrenos   = "madrono-tfm-dev-cartelera_cines_estrenos"
      + meteorologia               = "madrono-tfm-dev-meteorologia"
      + ruido                      = "madrono-tfm-dev-ruido"
      + trafico                    = "madrono-tfm-dev-trafico"
      + transporte_publico_emt     = "madrono-tfm-dev-transporte_publico_emt"
    }
  + producer_schedule_names        = {
      + aemet_avisos_0800          = "madrono-tfm-dev-aemet_avisos_0800"
      + aemet_avisos_1100          = "madrono-tfm-dev-aemet_avisos_1100"
      + aemet_avisos_1800          = "madrono-tfm-dev-aemet_avisos_1800"
      + aemet_avisos_2350          = "madrono-tfm-dev-aemet_avisos_2350"
      + aemet_prevision_0700       = "madrono-tfm-dev-aemet_prevision_0700"
      + aemet_prevision_1400       = "madrono-tfm-dev-aemet_prevision_1400"
      + afluencia_lugares          = "madrono-tfm-dev-afluencia_lugares"
      + aforos_peatones_bicicletas = "madrono-tfm-dev-aforos_peatones_bicicletas"
      + agenda_eventos             = "madrono-tfm-dev-agenda_eventos"
      + aparcamientos              = "madrono-tfm-dev-aparcamientos"
      + bicimad                    = "madrono-tfm-dev-bicimad"
      + bluesky_menciones          = "madrono-tfm-dev-bluesky_menciones"
      + calidad_aire               = "madrono-tfm-dev-calidad_aire"
      + cams_0715_utc              = "madrono-tfm-dev-cams_0715_utc"
      + cams_0900_utc              = "madrono-tfm-dev-cams_0900_utc"
      + cartelera_cines_estrenos   = "madrono-tfm-dev-cartelera_cines_estrenos"
      + emt_llegadas               = "madrono-tfm-dev-emt_llegadas"
      + meteorologia               = "madrono-tfm-dev-meteorologia"
      + ruido                      = "madrono-tfm-dev-ruido"
      + trafico                    = "madrono-tfm-dev-trafico"
    }
  + scheduler_role_arn             = (known after apply)
  + secret_ssm_parameter_names     = {
      + AEMET_API_KEY       = "/madrono-tfm/dev/secrets/aemet-api-key"
      + CAMS_ADS_API_KEY    = "/madrono-tfm/dev/secrets/cams-ads-api-key"
      + EMT_CLIENT_ID       = "/madrono-tfm/dev/secrets/emt-client-id"
      + EMT_PASS_KEY        = "/madrono-tfm/dev/secrets/emt-pass-key"
      + GOOGLE_MAPS_API_KEY = "/madrono-tfm/dev/secrets/google-maps-api-key"
    }

─────────────────────────────────────────────────────────────────────────────

Note: You didn't use the -out option to save this plan, so Terraform can't
guarantee to take exactly these actions if you run "terraform apply" now.
```

## Restricciones respetadas

- **No se ha ejecutado `terraform apply`** en ningún momento; el `plan` de
  arriba es el entregable de infraestructura de esta tarea.
- **No se ha modificado ningún recurso ya aplicado** del lakehouse (los 3
  buckets S3, `aws_iam_role.ingestion`): el plan confirma `0 to change`
  sobre ellos; el rol de ingesta solo gana una policy **adicional**
  (`ingestion_lambda_logs`), no se toca como recurso.
- **Ninguna credencial real aparece en ningún fichero commiteado** ni en este
  documento: los 5 parámetros SSM se crean con un placeholder literal no
  sensible (`CHANGEME-SET-MANUALLY-OUTSIDE-TERRAFORM`), y el plan de arriba
  imprime `(sensitive value)` en vez del placeholder para esos 4 bloques
  `environment` y para `aws_ssm_parameter.secrets[*].value` (por
  `sensitive = true` en `variables.tf`).
- **No se ha instalado ninguna dependencia de terceros ni se ha construido
  ninguna Lambda Layer real** en esta EC2 de disco limitado — ver sección de
  empaquetado arriba. El único artefacto construido localmente
  (`data.archive_file.ingesta_source`, ~140 KB de código fuente puro) es
  bounded, se genera en `infra/terraform/build/` (gitignored) y se ha
  eliminado al terminar la tarea.
- **No se ha dejado nada programado** (cron, systemd timer, bucle) en esta
  EC2: los 20 schedules son definiciones de Terraform, no aplicadas — no
  hay ninguna EventBridge Scheduler real invocando nada todavía.

## Relevante para tareas futuras

- **Antes del `apply` real (tarea 030)**, hacen falta dos cosas fuera de
  Terraform, documentadas aquí para que esa tarea no las redescubra desde
  cero:
  1. Construir una Lambda Layer real con las dependencias de
     `ingesta/requirements.txt` en un entorno compatible con el runtime de
     Lambda (`python3.13`, Linux x86_64) — p.ej. `pip install -r
     ingesta/requirements.txt --platform manylinux2014_x86_64
     --implementation cp --python-version 3.13 --only-binary=:all: --target
     layer/python` dentro de un contenedor Docker con esa imagen base (no
     en esta EC2), subir el .zip resultante como
     `aws_lambda_layer_version` (recurso nuevo, no añadido en esta tarea) y
     fijar su ARN en `terraform.tfvars` vía
     `lambda_dependencies_layer_arn`. `netCDF4` y `populartimes` (instalado
     desde GitHub, no PyPI) son los dos paquetes que más probablemente
     necesiten atención especial; puede que valga la pena separarlos en su
     propia layer si `cams_calidad_aire`/`afluencia_lugares` la necesitan
     pero el resto de funciones no, para no engordar el paquete de las 12
     funciones que no la usan.
  2. Fijar el valor real de los 5 parámetros SSM
     (`terraform output secret_ssm_parameter_names` da los nombres exactos)
     con `aws ssm put-parameter --name <nombre> --value <credencial real>
     --type SecureString --overwrite`, a mano, fuera de Terraform — el
     `lifecycle.ignore_changes = [value]` de `aws_ssm_parameter.secrets` ya
     está pensado para que ningún `apply` posterior los pise.
- El `for_each` sobre `local.producers` asume que **todas** las funciones
  comparten el mismo .zip de código fuente y el mismo rol de ejecución
  (`aws_iam_role.ingestion`). Si una tarea futura necesita que un productor
  concreto tenga permisos IAM adicionales que el resto no debería tener
  (más allá de escribir en Bronze y sus propios logs), hará falta darle su
  propio rol — el diseño actual no lo permite sin romper la simplicidad del
  `for_each` compartido, a propósito: los 14 productores tienen hoy
  exactamente los mismos permisos (Bronze + sus propios logs), y así debe
  seguir mientras eso sea cierto.
- Si una tarea futura añade un productor nuevo (módulo con `lambda_handler`
  y `DATASET_NAME` propios, siguiendo el patrón de las tareas 026/027/028),
  desplegarlo es tan simple como añadir una entrada a `local.producers` (y
  una o más a `local.schedules`) en `infra/terraform/lambda.tf` — no hace
  falta ningún otro cambio de Terraform.
- `agenda_recintos_madrid.py` (tarea 022) sigue sin `lambda_handler` propio
  (confirmado también en la tarea 028) y, por tanto, sin entrada en
  `local.producers`: no le falta nada a esta tarea, no tiene captura propia
  que desplegar.
- El nombre de cada función Lambda (`${project_name}-${environment}-<clave>`,
  p.ej. `madrono-tfm-dev-trafico`) y de cada schedule
  (`madrono-tfm-dev-<clave-de-schedule>`, p.ej.
  `madrono-tfm-dev-aemet_avisos_0800`) queda fijado por las claves de
  `local.producers`/`local.schedules` — cambiar esas claves en una tarea
  futura renombraría (destruye+recrea) el recurso real una vez aplicado, no
  es un cambio inocuo tras el primer `apply`.
