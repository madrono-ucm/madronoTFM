# 015 — Aplicar la infraestructura AWS del lakehouse (`terraform apply`)

## Qué se implementó

Esta tarea aplica en AWS la infraestructura del lakehouse que la tarea 001
dejó escrita en `infra/terraform/` y que la tarea 014 dejó planificada y
revisada (backend remoto ya creado, plan de 21 recursos a crear aprobado por
un humano en `doc/014-bootstrap-terraform-state-y-plan.md`). No hay cambios
de código: ningún fichero `.tf` de `infra/terraform/` se ha tocado en esta
tarea. El único entregable de código es este propio documento; `backend.hcl`
y `terraform.tfvars` se regeneraron a partir de sus `.example` (gitignored,
no commiteados), sin ajustar ningún valor — coincidían exactamente con lo ya
documentado en la tarea 014.

## Pasos ejecutados

```bash
cd infra/terraform
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan -var-file=terraform.tfvars   # comprobación: ¿sigue igual que en la tarea 014?
terraform apply -var-file=terraform.tfvars -auto-approve
```

`terraform init` se completó sin error (mismo warning no bloqueante de
`dynamodb_table` deprecado que en la tarea 014, sin relevancia). El `plan` de
comprobación dio exactamente **`Plan: 21 to add, 0 to change, 0 to destroy`**,
idéntico al ya revisado en `doc/014-bootstrap-terraform-state-y-plan.md`, así
que se procedió a aplicar sin modificar nada.

## Resultado del `apply`

**`Apply complete! Resources: 21 added, 0 changed, 0 destroyed.`** Sin
errores, sin recursos a medio crear. Se aplicó de una sola pasada, sin
reintentos ni intervención manual.

## Recursos reales creados en AWS (auditoría)

Región: **`eu-west-1`**. Cuenta AWS: **`222234418587`**.

| Recurso | Nombre / ARN |
|---|---|
| Bucket S3 Bronze | `madrono-tfm-dev-bronze-222234418587` (`arn:aws:s3:::madrono-tfm-dev-bronze-222234418587`) |
| Bucket S3 Silver | `madrono-tfm-dev-silver-222234418587` (`arn:aws:s3:::madrono-tfm-dev-silver-222234418587`) |
| Bucket S3 Gold | `madrono-tfm-dev-gold-222234418587` (`arn:aws:s3:::madrono-tfm-dev-gold-222234418587`) |
| Rol IAM de ingesta | `madrono-tfm-dev-ingestion-role` (`arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role`) |
| Policy IAM de ingesta | `madrono-tfm-dev-ingestion-bronze-write` (`arn:aws:iam::222234418587:policy/madrono-tfm-dev-ingestion-bronze-write`) |

Cada uno de los 3 buckets lleva además (por recurso, 6 recursos Terraform
cada uno: bucket, versionado, cifrado, bloqueo de acceso público, política de
bucket, ciclo de vida) — total 18 recursos de buckets + rol + policy +
attachment = 21, tal como anticipaba el plan de la tarea 014.

## Verificación con `aws` CLI directo (no solo la salida de Terraform)

Ejecutado tras el apply, contra los 3 buckets y el rol/policy reales:

- **`aws s3api head-bucket`** en los 3 buckets → los 3 existen y responden en
  `eu-west-1`.
- **`aws s3api get-bucket-versioning`** en los 3 → `"Status": "Enabled"` en
  los 3.
- **`aws s3api get-bucket-encryption`** en los 3 → SSE-S3 (`AES256`) con
  `BucketKeyEnabled: true` en los 3.
- **`aws s3api get-public-access-block`** en los 3 → las 4 protecciones
  (`BlockPublicAcls`, `IgnorePublicAcls`, `BlockPublicPolicy`,
  `RestrictPublicBuckets`) en `true` en los 3.
- **`aws iam get-role --role-name madrono-tfm-dev-ingestion-role`** → existe,
  `AssumeRolePolicyDocument` confía en `lambda.amazonaws.com`, tal como
  definía `variables.tf`/`terraform.tfvars`.
- **`aws iam list-attached-role-policies --role-name madrono-tfm-dev-ingestion-role`**
  → tiene adjunta exactamente `madrono-tfm-dev-ingestion-bronze-write`
  (`AttachmentCount: 1`).
- **`aws iam get-policy`** sobre esa policy → existe, `IsAttachable: true`,
  descripción "Permite escribir objetos en el bucket Bronze del lakehouse
  (sin lectura ni borrado, y sin acceso a Silver/Gold)".

Todo lo anterior confirma que el estado real en AWS coincide con lo que
Terraform reporta — no se confía únicamente en la salida de `apply`.

## Salida completa de `terraform output`

```
aws_account_id = "222234418587"
ingestion_policy_arn = "arn:aws:iam::222234418587:policy/madrono-tfm-dev-ingestion-bronze-write"
ingestion_role_arn = "arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role"
lakehouse_bucket_arns = {
  "bronze" = "arn:aws:s3:::madrono-tfm-dev-bronze-222234418587"
  "gold" = "arn:aws:s3:::madrono-tfm-dev-gold-222234418587"
  "silver" = "arn:aws:s3:::madrono-tfm-dev-silver-222234418587"
}
lakehouse_bucket_names = {
  "bronze" = "madrono-tfm-dev-bronze-222234418587"
  "gold" = "madrono-tfm-dev-gold-222234418587"
  "silver" = "madrono-tfm-dev-silver-222234418587"
}
```

## Confirmación explícita

El `apply` terminó **sin error** y coincidió exactamente con el plan ya
revisado en la tarea 014 (21 to add, 0 to change, 0 to destroy; los mismos
21 recursos, sin ninguna diferencia). No se ejecutó `terraform destroy` en
ningún momento. No se creó, modificó ni borró ningún otro recurso de AWS
fuera de lo que `infra/terraform/main.tf` ya describía. No se modificó
ningún fichero `.tf`.

## Relevante para tareas futuras

- **El bucket Bronze real ya existe y tiene su rol/policy de escritura
  listos**: `madrono-tfm-dev-bronze-222234418587`,
  `arn:aws:iam::222234418587:role/madrono-tfm-dev-ingestion-role`. Las
  tareas de ingesta ya escritas (002-013) pueden empezar a conectarse a S3
  real en lugar de solo dejar muestras en local/fixtures — este era
  precisamente el bloqueo que documentaban como pendiente ("tras aplicar la
  infraestructura de la tarea 001").
- El rol de ingesta confía en `lambda.amazonaws.com` (valor por defecto de
  `ingestion_trusted_services` en `terraform.tfvars.example`, sin cambiar).
  Si el mecanismo de ingesta real termina no siendo una Lambda (p. ej. una
  tarea ECS/Fargate, un cron en EC2, un Glue job), una tarea futura deberá
  ajustar esa variable y volver a aplicar (`terraform apply` de nuevo, sin
  destruir nada) para que el `assume role policy` del rol confíe en el
  servicio correcto — de lo contrario ese servicio no podrá asumir el rol.
- La policy adjunta (`madrono-tfm-dev-ingestion-bronze-write`) solo permite
  `PutObject`/`PutObjectTagging`/`AbortMultipartUpload`/`ListMultipartUploadParts`
  + `ListBucket` sobre el bucket Bronze — sin lectura de objetos ni acceso a
  Silver/Gold. Cualquier tarea futura que necesite leer de Bronze (p. ej. un
  job de transformación Bronze→Silver) necesitará una policy/rol adicional;
  no se debe ampliar esta policy de ingesta para ese caso, ya que su alcance
  deliberado es solo escritura desde productores.
- Backend remoto de Terraform ya operativo end-to-end: dos aplicaciones
  consecutivas (`init`+`plan` en la 014, `init`+`plan`+`apply` en esta) han
  usado el mismo bucket de estado/tabla de locking sin conflicto ni
  necesidad de ajuste — confirma que el bootstrap de la tarea 014 es
  reutilizable sin cambios para el ciclo de vida normal del proyecto
  (añadir/cambiar recursos en `main.tf` y volver a aplicar).
- El warning de `dynamodb_table` deprecado sigue presente (provider AWS
  `~> 5.0`, instalado `5.100.0`, sugiere migrar a `use_lockfile`). Sigue sin
  ser bloqueante y sigue fuera del alcance de esta tarea (no se tocó
  `versions.tf`); se mantiene como nota para quien decida abordar esa
  migración en el futuro.
