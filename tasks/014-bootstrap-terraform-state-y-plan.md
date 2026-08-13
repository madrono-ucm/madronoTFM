---
id: 14
slug: bootstrap-terraform-state-y-plan
title: Bootstrap del backend de Terraform y plan de la infraestructura AWS
status: in_review
force: true
allow_infra_apply: true
branch: task/014-bootstrap-terraform-state-y-plan
pr_number: 61
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/61
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-13T15:38:51+00:00'
updated_at: '2026-08-13T15:53:46.219963+00:00'
started_at: '2026-08-13T15:50:28.878255+00:00'
submitted_at: '2026-08-13T15:53:46.219804+00:00'
merged_at: null
---

## Contexto

La tarea 001 dejó escrito (sin aplicar) el código Terraform del lakehouse en
`infra/terraform/` — ver `infra/terraform/README.md` para el detalle completo de
qué crea y por qué. Esta tarea da el siguiente paso: preparar el backend remoto de
Terraform y generar el plan, **sin aplicar la infraestructura del lakehouse
todavía**. Aplicarla es el trabajo de una tarea posterior (015), que se creará
aparte, solo después de que un humano revise el plan que produce esta tarea.

Esta EC2 ya tiene un rol de IAM (`madrono-terraform-deployerEC2`) asociado como
instance profile, con permisos de sobra (S3, DynamoDB, IAM, EC2, Lambda,
EventBridge, Glue, Athena, CloudWatch, SSM en modo FullAccess) para todo lo que
pide esta tarea — no necesitas configurar ninguna credencial, `aws`/`terraform` ya
funcionan directamente en esta máquina.

**Excepción explícita de alcance** (`allow_infra_apply: true` en el front-matter de
esta tarea): tienes permiso para ejecutar comandos `aws`/`terraform` con efectos
reales, pero **estrictamente limitado a lo que se describe a continuación** — nada
de `terraform apply` sobre `infra/terraform/` (eso es la tarea 015), nada de
`terraform destroy`, nada fuera de esta lista.

## Objetivo

1. Ejecutar el "paso 0" documentado en `infra/terraform/README.md` (bucket S3 +
   tabla DynamoDB para el estado de Terraform), con `aws` CLI directo.
2. `terraform init` con ese backend real.
3. `terraform plan` (con `terraform.tfvars` a partir del `.example`, los valores por
   defecto son razonables) — **sin `terraform apply`**.
4. Dejar constancia completa y legible del plan para que un humano lo revise.

## Alcance concreto

1. Comprueba primero si el bucket de estado ya existe (`aws s3api head-bucket
   --bucket madrono-tfm-terraform-state --region eu-west-1`): si no existe (lo
   normal, es la primera vez), créalo siguiendo exactamente los comandos de la
   sección "Paso 0" de `infra/terraform/README.md` (bucket + versionado + cifrado +
   bloqueo de acceso público + tabla DynamoDB `PAY_PER_REQUEST`). Los nombres de
   ejemplo del README (`madrono-tfm-terraform-state` /
   `madrono-tfm-terraform-locks`) están libres a fecha de creación de esta tarea —
   compruébalo tú igualmente por si ha cambiado, y si el nombre del bucket
   colisionara (los nombres de bucket S3 son únicos globalmente, no solo por
   cuenta), añade el account id como sufijo, igual que ya hace `main.tf` para los
   buckets del lakehouse, y documenta el nombre final elegido de forma muy visible
   en el resumen de `doc/014-bootstrap-terraform-state-y-plan.md` — la tarea 015 lo necesitará y lo leerá
   como contexto acumulado.
2. Crea `infra/terraform/backend.hcl` (gitignored, no lo commitees) a partir de
   `backend.hcl.example`, con los valores reales del paso anterior.
3. Crea `infra/terraform/terraform.tfvars` (gitignored, no lo commitees) a partir de
   `terraform.tfvars.example` si hace falta ajustar algo; los valores por defecto de
   `variables.tf` ya son razonables y probablemente no haga falta tocar nada.
4. Ejecuta `terraform init -backend-config=backend.hcl` y luego
   `terraform plan -var-file=terraform.tfvars` dentro de `infra/terraform/`.
5. Copia la salida **completa** de `terraform plan` (qué se crearía: los 3 buckets,
   sus configuraciones, el rol y la policy de ingesta) en el resumen de
   `doc/014-bootstrap-terraform-state-y-plan.md`, dentro de un bloque de código, para que quede como
   referencia legible sin que nadie tenga que volver a ejecutar `plan`.
6. NO ejecutes `terraform apply`. NO crees ni modifiques ningún recurso de
   `infra/terraform/main.tf` (los buckets del lakehouse, el rol de ingesta) — el
   único efecto real permitido en esta tarea es el bootstrap del paso 0 (bucket de
   estado + tabla de locking).
7. Como no hay código de aplicación que cambie (`infra/terraform/*.tf` no se toca),
   el commit de esta tarea puede limitarse a `doc/014-bootstrap-terraform-state-y-plan.md` — sigue estando
   obligado a existir aunque no haya cambios de código, es el entregable principal
   de esta tarea.

## Restricciones

- El único efecto real en AWS permitido es el paso 0 (bucket de estado + tabla de
  locking). `terraform init`/`plan` son de solo lectura respecto a la
  infraestructura del lakehouse (no crean nada de `main.tf`).
- NO ejecutes `terraform apply` sobre `infra/terraform/`. NO ejecutes
  `terraform destroy` bajo ninguna circunstancia.
- Si algún comando falla por permisos, documenta el error exacto en el resumen de
  `doc/` — no intentes ampliar permisos ni crear nuevos usuarios/roles IAM para
  sortearlo.

## Criterios de aceptación

- El bucket de estado y la tabla de locking existen en AWS (verificable con
  `aws s3api head-bucket` / `aws dynamodb describe-table`).
- `terraform init` con el backend real se completa sin error.
- El resumen de `doc/014-bootstrap-terraform-state-y-plan.md` contiene la salida completa de
  `terraform plan`, el nombre final del bucket/tabla de estado usados, y dice
  explícitamente que no se ha aplicado nada de `infra/terraform/main.tf`.
