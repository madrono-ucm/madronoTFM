# Infraestructura AWS del lakehouse (Terraform)

Andamiaje base de infraestructura AWS para la Fase 1 (Ingesta) del TFM «Madroño»:
un lakehouse medallón (Bronze/Silver/Gold) sobre S3, con coste mínimo como
principio de diseño (apartado 5.4 de la memoria).

**Este código no se ha aplicado.** Escribirlo y documentarlo es el alcance de
esta tarea; `terraform apply` es una decisión y un paso manual posterior de un
humano con las credenciales adecuadas.

## Estructura

| Fichero | Contenido |
|---|---|
| `versions.tf` | Versión mínima de Terraform y de los providers `aws`/`archive`, declaración del backend remoto. |
| `variables.tf` | Todas las variables de entrada (región, nombre de proyecto, ciclo de vida, principals de ingesta, runtime/timeout/memoria de Lambda, placeholder de secretos...). |
| `main.tf` | Provider, buckets S3 del lakehouse, y el rol/policy IAM de ingesta. |
| `lambda.tf` | Tarea 029: una función Lambda + un schedule de EventBridge Scheduler por productor de `ingesta/capturas/`, parámetros SSM placeholder para sus credenciales, y el rol IAM que EventBridge Scheduler usa para invocarlas. |
| `outputs.tf` | Nombres/ARNs de los buckets, del rol de ingesta, de las funciones Lambda de productor y de sus schedules. |
| `backend.hcl.example` | Plantilla de configuración del backend S3 (bucket de estado, tabla de lock). |
| `terraform.tfvars.example` | Plantilla de valores de variables. |

## Lambda + EventBridge Scheduler de los productores (tarea 029, plan sin aplicar)

`lambda.tf` despliega los 14 productores de `ingesta/capturas/` que ya tienen
`lambda_handler` (tareas 026/027/028) como funciones Lambda con su propio
schedule real de EventBridge Scheduler, vía `for_each` sobre dos mapas
(`local.producers`, 14 entradas; `local.schedules`, 20 entradas — más
schedules que productores porque `aemet_prevision_avisos` reparte 6 schedules
sobre una única función y `cams_calidad_aire` reparte 2). Detalle completo de
cadencias, empaquetado, secretos vía SSM Parameter Store y el `plan` real
generado (58 recursos a añadir, 0 a cambiar, 0 a destruir) en
`doc/029-terraform-lambda-eventbridge-plan.md`. **No se ha aplicado**: es
plan-only, igual que el resto de `infra/terraform/` a fecha de esta tarea
(salvo el propio lakehouse, aplicado en la tarea 015).

Dos cosas quedan pendientes, documentadas allí, antes de que un futuro
`terraform apply` (tarea 030) despliegue algo realmente funcional: construir
una Lambda Layer real con las dependencias de `ingesta/requirements.txt`
(`var.lambda_dependencies_layer_arn`, `null` por ahora) y fijar a mano el
valor real de los 5 parámetros SSM placeholder que hoy solo tienen
`"CHANGEME-SET-MANUALLY-OUTSIDE-TERRAFORM"`.

## Recursos que crea

- **3 buckets S3** (`aws_s3_bucket.lakehouse`, `for_each` sobre `var.medallion_layers`,
  por defecto `bronze`/`silver`/`gold`), uno por capa del lakehouse medallón —
  ver la justificación de "un bucket por capa" (en vez de un único bucket con
  prefijos `bronze/`, `silver/`, `gold/`) como comentario en `main.tf`: en
  resumen, así el rol de ingesta puede acotarse al ARN completo del bucket
  Bronze sin depender de que una `Condition` de prefijo esté bien escrita, y
  cada capa puede evolucionar su ciclo de vida/cifrado de forma independiente.
  El nombre de cada bucket es `${project_name}-${environment}-${layer}-${account_id}`
  (el account id al final evita colisiones de nombre, que en S3 son globales).
- **Versionado** habilitado en los 3 buckets (protege de sobrescrituras/borrados
  accidentales de la ingesta).
- **Cifrado en reposo** (SSE-S3/AES256) por defecto en los 3 buckets.
- **Bloqueo de acceso público** (`aws_s3_bucket_public_access_block`) en los 3 buckets.
- **Política de ciclo de vida** en los 3 buckets, pensada para minimizar coste sin
  penalizar la latencia de consulta de los datos vivos:
  - La versión actual de cada objeto pasa a `STANDARD_IA` a los
    `var.standard_ia_transition_days` días (30 por defecto) — sigue siendo
    consultable al instante, pero más barata en storage.
  - Deliberadamente **no** se transiciona la versión actual a Glacier: Gold en
    particular se espera consultar bajo demanda (Athena/BI), y Glacier añade
    minutos/horas de latencia de recuperación.
  - Las versiones no-actuales (sobrescritas/borradas) sí pasan a `GLACIER` a
    los `var.noncurrent_version_glacier_days` días y se expiran del todo a los
    `var.noncurrent_version_expiration_days` días: es historial de
    versionado, no datos que se vayan a consultar.
  - Se abortan multipart uploads incompletos pasados 7 días.
- **Bucket policy** que deniega cualquier petición sin TLS (`aws:SecureTransport`).
- **Rol IAM `ingestion`** (`aws_iam_role.ingestion`) pensado para que lo asuman
  los futuros servicios de ingesta (por defecto, cualquier función Lambda de la
  cuenta — ver `var.ingestion_trusted_services`/`var.ingestion_trusted_arns`
  para ampliarlo a otros servicios o a roles/usuarios concretos).
- **Policy `ingestion_bronze_write`** adjunta a ese rol, con permisos
  **exclusivamente de escritura sobre el bucket Bronze**: `s3:PutObject`,
  `s3:PutObjectTagging`, `s3:AbortMultipartUpload`, `s3:ListMultipartUploadParts`
  y `s3:ListBucket`. Sin `s3:GetObject` ni `s3:DeleteObject`, y sin ningún
  permiso sobre Silver/Gold.

## Paso 0 (manual, una sola vez, antes del primer `terraform init`)

El backend remoto (S3 + DynamoDB) no puede crearse con el mismo Terraform que
lo usa como backend (problema del huevo y la gallina), así que este paso se
hace **a mano, una vez**, con la CLI de `aws` o la consola — **no lo ejecuta
este proyecto ni se ha ejecutado como parte de esta tarea**:

```bash
# Bucket de estado (nombres de ejemplo — ajusta al valor real que uses en backend.hcl)
aws s3api create-bucket \
  --bucket madrono-tfm-terraform-state \
  --region eu-west-1 \
  --create-bucket-configuration LocationConstraint=eu-west-1

aws s3api put-bucket-versioning \
  --bucket madrono-tfm-terraform-state \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket madrono-tfm-terraform-state \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3api put-public-access-block \
  --bucket madrono-tfm-terraform-state \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Tabla DynamoDB de locking (clave de partición "LockID", tipo String)
aws dynamodb create-table \
  --table-name madrono-tfm-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region eu-west-1
```

`PAY_PER_REQUEST` (on-demand) evita pagar capacidad reservada por una tabla que
apenas recibe tráfico (un `apply` ocasional): coste prácticamente cero en reposo.

## Cómo se ejecutaría (no ejecutado en esta tarea)

```bash
cd infra/terraform

cp backend.hcl.example backend.hcl        # y edítalo con el bucket/tabla reales del paso 0
cp terraform.tfvars.example terraform.tfvars  # opcional, los defaults ya son razonables

terraform init -backend-config=backend.hcl
terraform plan  -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

`backend.hcl` y `terraform.tfvars` están en `.gitignore`: no se commitean
porque pueden variar por persona/entorno (y el bucket de estado no debería
ser público conocimiento más allá de quien opera la infra).

## Permisos IAM necesarios para ejecutar `terraform apply`

La identidad (usuario o rol IAM) que ejecute `terraform init/plan/apply` sobre
este proyecto necesita, como mínimo, las siguientes acciones. Se listan
explícitamente en vez de recurrir a `AdministratorAccess`, agrupadas por a qué
usan cada bloque de acciones:

**Backend remoto (leer/escribir el fichero de estado y el lock)**

- Sobre el bucket de estado (`arn:aws:s3:::madrono-tfm-terraform-state` y
  `.../*`): `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket`.
- Sobre la tabla de locking (`arn:aws:dynamodb:eu-west-1:<account_id>:table/madrono-tfm-terraform-locks`):
  `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:DeleteItem`, `dynamodb:DescribeTable`.

**Identidad de la cuenta (usada por `data "aws_caller_identity"` para componer nombres de bucket)**

- `sts:GetCallerIdentity` (acción a nivel de cuenta, sin `Resource` restringible).

**Buckets S3 del lakehouse** (sobre `arn:aws:s3:::madrono-tfm-*` y `.../*`, o
acotado a los 3 nombres finales una vez conocidos):

- `s3:CreateBucket`, `s3:DeleteBucket`
- `s3:PutBucketVersioning`, `s3:GetBucketVersioning`
- `s3:PutEncryptionConfiguration`, `s3:GetEncryptionConfiguration`
- `s3:PutBucketPublicAccessBlock`, `s3:GetBucketPublicAccessBlock`
- `s3:PutLifecycleConfiguration`, `s3:GetLifecycleConfiguration`
- `s3:PutBucketPolicy`, `s3:GetBucketPolicy`, `s3:DeleteBucketPolicy`
- `s3:PutBucketTagging`, `s3:GetBucketTagging`
- `s3:ListBucket`, `s3:GetBucketLocation`, `s3:GetBucketAcl`

**Rol y policy IAM de ingesta** (sobre
`arn:aws:iam::<account_id>:role/madrono-tfm-*` y
`arn:aws:iam::<account_id>:policy/madrono-tfm-*`):

- `iam:CreateRole`, `iam:DeleteRole`, `iam:GetRole`, `iam:UpdateAssumeRolePolicy`
- `iam:CreatePolicy`, `iam:DeletePolicy`, `iam:GetPolicy`, `iam:GetPolicyVersion`,
  `iam:ListPolicyVersions`, `iam:CreatePolicyVersion`, `iam:DeletePolicyVersion`
- `iam:AttachRolePolicy`, `iam:DetachRolePolicy`, `iam:ListAttachedRolePolicies`
- `iam:TagRole`, `iam:UntagRole`, `iam:TagPolicy`, `iam:UntagPolicy`

Ejemplo de policy IAM (documental — no se ha aplicado ni se aplica automáticamente),
para adjuntar a la identidad que vaya a ejecutar `terraform apply`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TerraformStateBackend",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::madrono-tfm-terraform-state",
        "arn:aws:s3:::madrono-tfm-terraform-state/*"
      ]
    },
    {
      "Sid": "TerraformLockTable",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:DescribeTable"],
      "Resource": "arn:aws:dynamodb:eu-west-1:*:table/madrono-tfm-terraform-locks"
    },
    {
      "Sid": "CallerIdentity",
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    },
    {
      "Sid": "LakehouseBuckets",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket", "s3:DeleteBucket",
        "s3:PutBucketVersioning", "s3:GetBucketVersioning",
        "s3:PutEncryptionConfiguration", "s3:GetEncryptionConfiguration",
        "s3:PutBucketPublicAccessBlock", "s3:GetBucketPublicAccessBlock",
        "s3:PutLifecycleConfiguration", "s3:GetLifecycleConfiguration",
        "s3:PutBucketPolicy", "s3:GetBucketPolicy", "s3:DeleteBucketPolicy",
        "s3:PutBucketTagging", "s3:GetBucketTagging",
        "s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketAcl"
      ],
      "Resource": ["arn:aws:s3:::madrono-tfm-*", "arn:aws:s3:::madrono-tfm-*/*"]
    },
    {
      "Sid": "IngestionRoleAndPolicy",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:UpdateAssumeRolePolicy",
        "iam:CreatePolicy", "iam:DeletePolicy", "iam:GetPolicy", "iam:GetPolicyVersion",
        "iam:ListPolicyVersions", "iam:CreatePolicyVersion", "iam:DeletePolicyVersion",
        "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:ListAttachedRolePolicies",
        "iam:TagRole", "iam:UntagRole", "iam:TagPolicy", "iam:UntagPolicy"
      ],
      "Resource": [
        "arn:aws:iam::*:role/madrono-tfm-*",
        "arn:aws:iam::*:policy/madrono-tfm-*"
      ]
    }
  ]
}
```

Nótese que esto sigue sin incluir permisos para crear el propio bucket de
estado ni la tabla DynamoDB de locking (eso es el "paso 0" anterior, que
requiere además `s3:CreateBucket`/`s3:PutBucketVersioning`/etc. sobre el
bucket de estado y `dynamodb:CreateTable` — permisos de un momento puntual,
no de uso recurrente, por lo que no se piden aquí como parte del acceso
habitual de `apply`).

## Decisiones de diseño

- **Región `eu-west-1` (Irlanda) por defecto** en vez de `eu-south-2` (España):
  es la región de la UE con más madurez de servicios y, en general, precios de
  S3/DynamoDB más bajos, lo cual pesa más que la residencia estricta en España
  dado que el proyecto no tiene (por ahora) un requisito legal de mantener los
  datos dentro de España — ver `variable "aws_region"` en `variables.tf`. Es
  una variable, así que cambiar a `eu-south-2` si ese requisito aparece es
  trivial y no requiere tocar el resto del código.
- **Un bucket por capa** (Bronze/Silver/Gold) en vez de un bucket único con
  prefijos: simplifica y hace más seguras las políticas IAM de mínimo
  privilegio (ver más arriba).
- **Backend S3 + DynamoDB** para el estado, con el bucket/tabla creados a mano
  como paso 0 (no se pueden crear con el mismo Terraform que los usa).
- **Nada de MSK/Kafka ni otros servicios gestionados caros** en esta tarea:
  fuera de alcance, se evalúa en una tarea posterior una vez validado el resto
  del andamiaje (principio de coste mínimo, apartado 5.4 de la memoria).
- **Rol de ingesta confiado por defecto a `lambda.amazonaws.com`**: encaja con
  el principio de coste mínimo (sin servidores que pagar en reposo) como
  patrón por defecto para los futuros productores de datos; es una variable
  (`ingestion_trusted_services`/`ingestion_trusted_arns`) por si el servicio
  de ingesta termina siendo otra cosa (ECS, un rol de EC2, etc.).
