# 014 — Bootstrap del backend de Terraform y plan de la infraestructura AWS

## Qué se implementó

Esta tarea da el siguiente paso tras la 001 (que dejó escrito, sin aplicar, el
Terraform del lakehouse en `infra/terraform/`): preparar el backend remoto real
de Terraform (bucket S3 + tabla DynamoDB de locking, el "paso 0" documentado en
`infra/terraform/README.md`) y generar el `plan` de la infraestructura del
lakehouse, **sin aplicarla todavía**. Aplicarla (`terraform apply`) queda para
una tarea posterior (015), después de que un humano revise el plan que queda
documentado aquí.

No hay cambios de código: `infra/terraform/*.tf` no se ha tocado. El único
entregable de código de esta tarea es este propio fichero de documentación; los
ficheros `infra/terraform/backend.hcl` y `infra/terraform/terraform.tfvars`
creados durante la tarea son gitignored (ver `infra/terraform/.gitignore` y
`.gitignore` raíz) y no se commitean, tal como pedía el alcance de la tarea.

## ⚠️ Nombres reales del bucket de estado y tabla de locking (para la tarea 015)

Los nombres de ejemplo del README (`madrono-tfm-terraform-state` /
`madrono-tfm-terraform-locks`) **estaban libres** en el momento de esta tarea —
no hubo colisión de nombre de bucket S3 (comprobado con `head-bucket` antes de
crear) y no hizo falta añadir el account id como sufijo. Se usaron literalmente
esos nombres, tal cual figuran en `backend.hcl.example`:

| Recurso | Nombre/valor | Región |
|---|---|---|
| Bucket de estado (S3) | `madrono-tfm-terraform-state` | `eu-west-1` |
| Tabla de locking (DynamoDB) | `madrono-tfm-terraform-locks` | `eu-west-1` |
| Key del state dentro del bucket | `infra/lakehouse/terraform.tfstate` | — |
| Cuenta AWS | `222234418587` | — |

La tarea 015 puede reutilizar `infra/terraform/backend.hcl.example` /
`terraform.tfvars.example` tal cual (copiándolos a `backend.hcl` /
`terraform.tfvars`, no commiteados) sin necesidad de ajustar ningún nombre: ya
coinciden con lo realmente creado en AWS.

## Efectos reales en AWS (auditoría, único alcance de infraestructura de esta tarea)

Se ejecutaron, en este orden, exactamente los comandos de la sección "Paso 0"
de `infra/terraform/README.md`, con la CLI `aws` directa (usando el rol de
instancia `madrono-terraform-deployerEC2` ya asociado a esta EC2, sin
credenciales adicionales):

1. **`aws s3api create-bucket`** — bucket `madrono-tfm-terraform-state`,
   región `eu-west-1` (`LocationConstraint=eu-west-1`).
2. **`aws s3api put-bucket-versioning`** — versionado `Enabled` en ese bucket.
3. **`aws s3api put-bucket-encryption`** — cifrado por defecto SSE-S3 (AES256)
   en ese bucket.
4. **`aws s3api put-public-access-block`** — las 4 protecciones
   (`BlockPublicAcls`, `IgnorePublicAcls`, `BlockPublicPolicy`,
   `RestrictPublicBuckets`) a `true` en ese bucket.
5. **`aws dynamodb create-table`** — tabla `madrono-tfm-terraform-locks`,
   clave de partición `LockID` (tipo `S`), `PAY_PER_REQUEST`, región
   `eu-west-1`. Se esperó su transición a `ACTIVE` con
   `aws dynamodb wait table-exists` antes de continuar.

Verificado tras la creación:

```
$ aws s3api head-bucket --bucket madrono-tfm-terraform-state --region eu-west-1
{"BucketArn": "arn:aws:s3:::madrono-tfm-terraform-state", "BucketRegion": "eu-west-1", "AccessPointAlias": false}

$ aws dynamodb describe-table --table-name madrono-tfm-terraform-locks --region eu-west-1 --query 'Table.TableStatus' --output text
ACTIVE
```

**No se creó, modificó ni destruyó ningún otro recurso en AWS.** En particular,
**no se ha ejecutado `terraform apply` sobre `infra/terraform/`**: ni los 3
buckets del lakehouse (Bronze/Silver/Gold), ni el rol/policy IAM de ingesta,
existen todavía en la cuenta. Tampoco se ejecutó `terraform destroy` en ningún
momento.

## `terraform init` / `terraform plan`

Dentro de `infra/terraform/`, con `backend.hcl` y `terraform.tfvars` copiados
sin cambios desde sus `.example` (los valores por defecto —región
`eu-west-1`, `project_name=madrono-tfm`, `environment=dev`,
`ingestion_trusted_services=["lambda.amazonaws.com"]`— ya coincidían con lo
razonable para este bootstrap, no hizo falta ajustar nada):

```bash
cd infra/terraform
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan -var-file=terraform.tfvars
```

`terraform init` se completó **sin error**, contra el backend S3 real recién
creado (solo un warning no bloqueante: el proveedor AWS 5.100 sugiere migrar
de `dynamodb_table` a `use_lockfile`, el nuevo locking nativo de S3 — no se
tocó `versions.tf` porque está fuera del alcance de esta tarea, que no debía
modificar ningún `.tf`).

`terraform plan -var-file=terraform.tfvars` se completó **sin error**, con el
resultado:

```
Plan: 21 to add, 0 to change, 0 to destroy.
```

Es decir: no hay ningún recurso ya existente en la cuenta que Terraform
detecte como "a modificar" (el bootstrap del paso 0 vive fuera del state de
este proyecto, en su propio backend, tal como está diseñado) y los 21 recursos
son exactamente los que documenta `infra/terraform/README.md` como "Recursos
que crea" (3 buckets S3 × 6 recursos asociados cada uno —bucket, versionado,
cifrado, bloqueo de acceso público, política, ciclo de vida— más el rol IAM de
ingesta, su policy y el attachment entre ambos).

### Salida completa de `terraform plan -var-file=terraform.tfvars`

```
Warning: Deprecated Parameter

The parameter "dynamodb_table" is deprecated. Use parameter "use_lockfile"
instead.
data.aws_iam_policy_document.ingestion_assume_role: Reading...
data.aws_caller_identity.current: Reading...
data.aws_iam_policy_document.ingestion_assume_role: Read complete after 0s [id=2690255455]
data.aws_caller_identity.current: Read complete after 0s [id=222234418587]

Terraform used the selected providers to generate the following execution
plan. Resource actions are indicated with the following symbols:
  + create
 <= read (data resources)

Terraform will perform the following actions:

  # data.aws_iam_policy_document.bucket_policy["bronze"] will be read during apply
  # (config refers to values not yet known)
 <= data "aws_iam_policy_document" "bucket_policy" {
      + id            = (known after apply)
      + json          = (known after apply)
      + minified_json = (known after apply)

      + statement {
          + actions   = [
              + "s3:*",
            ]
          + effect    = "Deny"
          + resources = [
              + (known after apply),
              + (known after apply),
            ]
          + sid       = "DenyInsecureTransport"

          + condition {
              + test     = "Bool"
              + values   = [
                  + "false",
                ]
              + variable = "aws:SecureTransport"
            }

          + principals {
              + identifiers = [
                  + "*",
                ]
              + type        = "AWS"
            }
        }
    }

  # data.aws_iam_policy_document.bucket_policy["gold"] will be read during apply
  # (config refers to values not yet known)
 <= data "aws_iam_policy_document" "bucket_policy" {
      + id            = (known after apply)
      + json          = (known after apply)
      + minified_json = (known after apply)

      + statement {
          + actions   = [
              + "s3:*",
            ]
          + effect    = "Deny"
          + resources = [
              + (known after apply),
              + (known after apply),
            ]
          + sid       = "DenyInsecureTransport"

          + condition {
              + test     = "Bool"
              + values   = [
                  + "false",
                ]
              + variable = "aws:SecureTransport"
            }

          + principals {
              + identifiers = [
                  + "*",
                ]
              + type        = "AWS"
            }
        }
    }

  # data.aws_iam_policy_document.bucket_policy["silver"] will be read during apply
  # (config refers to values not yet known)
 <= data "aws_iam_policy_document" "bucket_policy" {
      + id            = (known after apply)
      + json          = (known after apply)
      + minified_json = (known after apply)

      + statement {
          + actions   = [
              + "s3:*",
            ]
          + effect    = "Deny"
          + resources = [
              + (known after apply),
              + (known after apply),
            ]
          + sid       = "DenyInsecureTransport"

          + condition {
              + test     = "Bool"
              + values   = [
                  + "false",
                ]
              + variable = "aws:SecureTransport"
            }

          + principals {
              + identifiers = [
                  + "*",
                ]
              + type        = "AWS"
            }
        }
    }

  # data.aws_iam_policy_document.ingestion_bronze_write will be read during apply
  # (config refers to values not yet known)
 <= data "aws_iam_policy_document" "ingestion_bronze_write" {
      + id            = (known after apply)
      + json          = (known after apply)
      + minified_json = (known after apply)

      + statement {
          + actions   = [
              + "s3:AbortMultipartUpload",
              + "s3:ListMultipartUploadParts",
              + "s3:PutObject",
              + "s3:PutObjectTagging",
            ]
          + effect    = "Allow"
          + resources = [
              + (known after apply),
            ]
          + sid       = "WriteBronzeObjects"
        }
      + statement {
          + actions   = [
              + "s3:ListBucket",
            ]
          + effect    = "Allow"
          + resources = [
              + (known after apply),
            ]
          + sid       = "ListBronzeBucket"
        }
    }

  # aws_iam_policy.ingestion_bronze_write will be created
  + resource "aws_iam_policy" "ingestion_bronze_write" {
      + arn              = (known after apply)
      + attachment_count = (known after apply)
      + description      = "Permite escribir objetos en el bucket Bronze del lakehouse (sin lectura ni borrado, y sin acceso a Silver/Gold)."
      + id               = (known after apply)
      + name             = "madrono-tfm-dev-ingestion-bronze-write"
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

  # aws_iam_role.ingestion will be created
  + resource "aws_iam_role" "ingestion" {
      + arn                   = (known after apply)
      + assume_role_policy    = jsonencode(
            {
              + Statement = [
                  + {
                      + Action    = "sts:AssumeRole"
                      + Effect    = "Allow"
                      + Principal = {
                          + Service = "lambda.amazonaws.com"
                        }
                    },
                ]
              + Version   = "2012-10-17"
            }
        )
      + create_date           = (known after apply)
      + description           = "Rol asumido por los servicios de ingesta (productores de datos) para escribir en la capa Bronze del lakehouse."
      + force_detach_policies = false
      + id                    = (known after apply)
      + managed_policy_arns   = (known after apply)
      + max_session_duration  = 3600
      + name                  = "madrono-tfm-dev-ingestion-role"
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

  # aws_iam_role_policy_attachment.ingestion_bronze_write will be created
  + resource "aws_iam_role_policy_attachment" "ingestion_bronze_write" {
      + id         = (known after apply)
      + policy_arn = (known after apply)
      + role       = "madrono-tfm-dev-ingestion-role"
    }

  # aws_s3_bucket.lakehouse["bronze"] will be created
  + resource "aws_s3_bucket" "lakehouse" {
      + acceleration_status         = (known after apply)
      + acl                         = (known after apply)
      + arn                         = (known after apply)
      + bucket                      = "madrono-tfm-dev-bronze-222234418587"
      + bucket_domain_name          = (known after apply)
      + bucket_prefix               = (known after apply)
      + bucket_regional_domain_name = (known after apply)
      + force_destroy               = false
      + hosted_zone_id              = (known after apply)
      + id                          = (known after apply)
      + object_lock_enabled         = (known after apply)
      + policy                      = (known after apply)
      + region                      = (known after apply)
      + request_payer               = (known after apply)
      + tags                        = {
          + "Layer" = "bronze"
        }
      + tags_all                    = {
          + "Environment" = "dev"
          + "Layer"       = "bronze"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + website_domain              = (known after apply)
      + website_endpoint            = (known after apply)

      + cors_rule (known after apply)

      + grant (known after apply)

      + lifecycle_rule (known after apply)

      + logging (known after apply)

      + object_lock_configuration (known after apply)

      + replication_configuration (known after apply)

      + server_side_encryption_configuration (known after apply)

      + versioning (known after apply)

      + website (known after apply)
    }

  # aws_s3_bucket.lakehouse["gold"] will be created
  + resource "aws_s3_bucket" "lakehouse" {
      + acceleration_status         = (known after apply)
      + acl                         = (known after apply)
      + arn                         = (known after apply)
      + bucket                      = "madrono-tfm-dev-gold-222234418587"
      + bucket_domain_name          = (known after apply)
      + bucket_prefix               = (known after apply)
      + bucket_regional_domain_name = (known after apply)
      + force_destroy               = false
      + hosted_zone_id              = (known after apply)
      + id                          = (known after apply)
      + object_lock_enabled         = (known after apply)
      + policy                      = (known after apply)
      + region                      = (known after apply)
      + request_payer               = (known after apply)
      + tags                        = {
          + "Layer" = "gold"
        }
      + tags_all                    = {
          + "Environment" = "dev"
          + "Layer"       = "gold"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + website_domain              = (known after apply)
      + website_endpoint            = (known after apply)

      + cors_rule (known after apply)

      + grant (known after apply)

      + lifecycle_rule (known after apply)

      + logging (known after apply)

      + object_lock_configuration (known after apply)

      + replication_configuration (known after apply)

      + server_side_encryption_configuration (known after apply)

      + versioning (known after apply)

      + website (known after apply)
    }

  # aws_s3_bucket.lakehouse["silver"] will be created
  + resource "aws_s3_bucket" "lakehouse" {
      + acceleration_status         = (known after apply)
      + acl                         = (known after apply)
      + arn                         = (known after apply)
      + bucket                      = "madrono-tfm-dev-silver-222234418587"
      + bucket_domain_name          = (known after apply)
      + bucket_prefix               = (known after apply)
      + bucket_regional_domain_name = (known after apply)
      + force_destroy               = false
      + hosted_zone_id              = (known after apply)
      + id                          = (known after apply)
      + object_lock_enabled         = (known after apply)
      + policy                      = (known after apply)
      + region                      = (known after apply)
      + request_payer               = (known after apply)
      + tags                        = {
          + "Layer" = "silver"
        }
      + tags_all                    = {
          + "Environment" = "dev"
          + "Layer"       = "silver"
          + "ManagedBy"   = "terraform"
          + "Project"     = "madrono-tfm"
        }
      + website_domain              = (known after apply)
      + website_endpoint            = (known after apply)

      + cors_rule (known after apply)

      + grant (known after apply)

      + lifecycle_rule (known after apply)

      + logging (known after apply)

      + object_lock_configuration (known after apply)

      + replication_configuration (known after apply)

      + server_side_encryption_configuration (known after apply)

      + versioning (known after apply)

      + website (known after apply)
    }

  # aws_s3_bucket_lifecycle_configuration.lakehouse["bronze"] will be created
  + resource "aws_s3_bucket_lifecycle_configuration" "lakehouse" {
      + bucket                                 = (known after apply)
      + expected_bucket_owner                  = (known after apply)
      + id                                     = (known after apply)
      + transition_default_minimum_object_size = "all_storage_classes_128K"

      + rule {
          + id     = "cost-optimization"
          + status = "Enabled"
            # (1 unchanged attribute hidden)

          + abort_incomplete_multipart_upload {
              + days_after_initiation = 7
            }

          + filter {
                # (1 unchanged attribute hidden)
            }

          + noncurrent_version_expiration {
              + noncurrent_days = 90
            }

          + noncurrent_version_transition {
              + noncurrent_days = 30
              + storage_class   = "GLACIER"
            }

          + transition {
              + days          = 30
              + storage_class = "STANDARD_IA"
            }
        }
    }

  # aws_s3_bucket_lifecycle_configuration.lakehouse["gold"] will be created
  + resource "aws_s3_bucket_lifecycle_configuration" "lakehouse" {
      + bucket                                 = (known after apply)
      + expected_bucket_owner                  = (known after apply)
      + id                                     = (known after apply)
      + transition_default_minimum_object_size = "all_storage_classes_128K"

      + rule {
          + id     = "cost-optimization"
          + status = "Enabled"
            # (1 unchanged attribute hidden)

          + abort_incomplete_multipart_upload {
              + days_after_initiation = 7
            }

          + filter {
                # (1 unchanged attribute hidden)
            }

          + noncurrent_version_expiration {
              + noncurrent_days = 90
            }

          + noncurrent_version_transition {
              + noncurrent_days = 30
              + storage_class   = "GLACIER"
            }

          + transition {
              + days          = 30
              + storage_class = "STANDARD_IA"
            }
        }
    }

  # aws_s3_bucket_lifecycle_configuration.lakehouse["silver"] will be created
  + resource "aws_s3_bucket_lifecycle_configuration" "lakehouse" {
      + bucket                                 = (known after apply)
      + expected_bucket_owner                  = (known after apply)
      + id                                     = (known after apply)
      + transition_default_minimum_object_size = "all_storage_classes_128K"

      + rule {
          + id     = "cost-optimization"
          + status = "Enabled"
            # (1 unchanged attribute hidden)

          + abort_incomplete_multipart_upload {
              + days_after_initiation = 7
            }

          + filter {
                # (1 unchanged attribute hidden)
            }

          + noncurrent_version_expiration {
              + noncurrent_days = 90
            }

          + noncurrent_version_transition {
              + noncurrent_days = 30
              + storage_class   = "GLACIER"
            }

          + transition {
              + days          = 30
              + storage_class = "STANDARD_IA"
            }
        }
    }

  # aws_s3_bucket_policy.lakehouse["bronze"] will be created
  + resource "aws_s3_bucket_policy" "lakehouse" {
      + bucket = (known after apply)
      + id     = (known after apply)
      + policy = (known after apply)
    }

  # aws_s3_bucket_policy.lakehouse["gold"] will be created
  + resource "aws_s3_bucket_policy" "lakehouse" {
      + bucket = (known after apply)
      + id     = (known after apply)
      + policy = (known after apply)
    }

  # aws_s3_bucket_policy.lakehouse["silver"] will be created
  + resource "aws_s3_bucket_policy" "lakehouse" {
      + bucket = (known after apply)
      + id     = (known after apply)
      + policy = (known after apply)
    }

  # aws_s3_bucket_public_access_block.lakehouse["bronze"] will be created
  + resource "aws_s3_bucket_public_access_block" "lakehouse" {
      + block_public_acls       = true
      + block_public_policy     = true
      + bucket                  = (known after apply)
      + id                      = (known after apply)
      + ignore_public_acls      = true
      + restrict_public_buckets = true
    }

  # aws_s3_bucket_public_access_block.lakehouse["gold"] will be created
  + resource "aws_s3_bucket_public_access_block" "lakehouse" {
      + block_public_acls       = true
      + block_public_policy     = true
      + bucket                  = (known after apply)
      + id                      = (known after apply)
      + ignore_public_acls      = true
      + restrict_public_buckets = true
    }

  # aws_s3_bucket_public_access_block.lakehouse["silver"] will be created
  + resource "aws_s3_bucket_public_access_block" "lakehouse" {
      + block_public_acls       = true
      + block_public_policy     = true
      + bucket                  = (known after apply)
      + id                      = (known after apply)
      + ignore_public_acls      = true
      + restrict_public_buckets = true
    }

  # aws_s3_bucket_server_side_encryption_configuration.lakehouse["bronze"] will be created
  + resource "aws_s3_bucket_server_side_encryption_configuration" "lakehouse" {
      + bucket = (known after apply)
      + id     = (known after apply)

      + rule {
          + bucket_key_enabled = true

          + apply_server_side_encryption_by_default {
              + sse_algorithm     = "AES256"
                # (1 unchanged attribute hidden)
            }
        }
    }

  # aws_s3_bucket_server_side_encryption_configuration.lakehouse["gold"] will be created
  + resource "aws_s3_bucket_server_side_encryption_configuration" "lakehouse" {
      + bucket = (known after apply)
      + id     = (known after apply)

      + rule {
          + bucket_key_enabled = true

          + apply_server_side_encryption_by_default {
              + sse_algorithm     = "AES256"
                # (1 unchanged attribute hidden)
            }
        }
    }

  # aws_s3_bucket_server_side_encryption_configuration.lakehouse["silver"] will be created
  + resource "aws_s3_bucket_server_side_encryption_configuration" "lakehouse" {
      + bucket = (known after apply)
      + id     = (known after apply)

      + rule {
          + bucket_key_enabled = true

          + apply_server_side_encryption_by_default {
              + sse_algorithm     = "AES256"
                # (1 unchanged attribute hidden)
            }
        }
    }

  # aws_s3_bucket_versioning.lakehouse["bronze"] will be created
  + resource "aws_s3_bucket_versioning" "lakehouse" {
      + bucket = (known after apply)
      + id     = (known after apply)

      + versioning_configuration {
          + mfa_delete = (known after apply)
          + status     = "Enabled"
        }
    }

  # aws_s3_bucket_versioning.lakehouse["gold"] will be created
  + resource "aws_s3_bucket_versioning" "lakehouse" {
      + bucket = (known after apply)
      + id     = (known after apply)

      + versioning_configuration {
          + mfa_delete = (known after apply)
          + status     = "Enabled"
        }
    }

  # aws_s3_bucket_versioning.lakehouse["silver"] will be created
  + resource "aws_s3_bucket_versioning" "lakehouse" {
      + bucket = (known after apply)
      + id     = (known after apply)

      + versioning_configuration {
          + mfa_delete = (known after apply)
          + status     = "Enabled"
        }
    }

Plan: 21 to add, 0 to change, 0 to destroy.

Changes to Outputs:
  + aws_account_id         = "222234418587"
  + ingestion_policy_arn   = (known after apply)
  + ingestion_role_arn     = (known after apply)
  + lakehouse_bucket_arns  = {
      + bronze = (known after apply)
      + gold   = (known after apply)
      + silver = (known after apply)
    }
  + lakehouse_bucket_names = {
      + bronze = "madrono-tfm-dev-bronze-222234418587"
      + gold   = "madrono-tfm-dev-gold-222234418587"
      + silver = "madrono-tfm-dev-silver-222234418587"
    }

─────────────────────────────────────────────────────────────────────────────

Note: You didn't use the -out option to save this plan, so Terraform can't
guarantee to take exactly these actions if you run "terraform apply" now.
```

## Confirmación explícita: no se ha aplicado nada de `infra/terraform/main.tf`

Ni los 3 buckets S3 del lakehouse (`madrono-tfm-dev-bronze-222234418587`,
`madrono-tfm-dev-silver-222234418587`, `madrono-tfm-dev-gold-222234418587`)
ni el rol IAM `madrono-tfm-dev-ingestion-role` ni la policy
`madrono-tfm-dev-ingestion-bronze-write` existen en la cuenta AWS. Todo lo que
aparece arriba es la salida de un `terraform plan` de solo lectura frente a la
infraestructura del lakehouse — el único efecto real en AWS de esta tarea es
el bucket de estado y la tabla de locking descritos en la sección anterior.

## Decisiones y notas para la tarea 015 (aplicar la infraestructura)

- Los nombres de `backend.hcl`/`terraform.tfvars` coinciden exactamente con
  los `.example` del repo — la tarea 015 puede regenerarlos con un simple
  `cp *.example <nombre>` sin necesitar releer este documento para los
  valores, aunque el nombre final del bucket/tabla de estado sí queda
  documentado aquí de forma explícita por si acaso.
- El warning de `dynamodb_table` deprecado (provider AWS `~> 5.0`, instalado
  `5.100.0`) es un aviso de migración hacia `use_lockfile` (locking nativo de
  S3, sin DynamoDB), no un error — no bloquea `init`/`plan`/`apply`. No se ha
  tocado `versions.tf` en esta tarea porque no había ningún cambio de código
  en su alcance; si la tarea 015 (u otra futura) quisiera migrar a
  `use_lockfile`, la tabla DynamoDB creada aquí quedaría sin uso, pero no hay
  ninguna prisa por decidirlo ahora.
- El `.terraform.lock.hcl` generado por `terraform init` (fija
  `hashicorp/aws` en `5.100.0`) queda en el directorio de trabajo pero
  **no se ha commiteado** en esta tarea, ya que `infra/terraform/.gitignore`
  lo excluye explícitamente (`.terraform.lock.hcl`) — coherente con no dejar
  cambios de código sin commitear pedidos por el alcance de esta tarea. Si la
  tarea 015 ejecuta su propio `terraform init`, generará el suyo con la misma
  versión (restricción `~> 5.0` en `versions.tf`), sin diferencia práctica.
- Ninguna de las variables de `terraform.tfvars.example` necesitó ajuste: los
  defaults de `variables.tf` (región `eu-west-1`, `project_name=madrono-tfm`,
  `environment=dev`) ya eran razonables para este bootstrap, tal como
  anticipaba el propio enunciado de la tarea.
