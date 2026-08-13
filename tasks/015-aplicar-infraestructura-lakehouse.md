---
id: 15
slug: aplicar-infraestructura-lakehouse
title: Aplicar la infraestructura AWS del lakehouse (terraform apply)
status: in_review
force: true
allow_infra_apply: true
branch: task/015-aplicar-infraestructura-lakehouse
pr_number: 62
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/62
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-13T15:56:54+00:00'
updated_at: '2026-08-13T16:04:21.072395+00:00'
started_at: '2026-08-13T16:00:58.505346+00:00'
submitted_at: '2026-08-13T16:04:21.072250+00:00'
merged_at: null
---

## Contexto

La tarea 014 preparó el backend remoto de Terraform (bucket de estado
`madrono-tfm-terraform-state` + tabla de locking `madrono-tfm-terraform-locks`,
región `eu-west-1`) y generó el plan de la infraestructura del lakehouse — revisado
por un humano en `doc/014-bootstrap-terraform-state-y-plan.md` antes de crear esta
tarea: **21 recursos a crear, 0 a cambiar, 0 a destruir** (3 buckets S3 del lakehouse
—Bronze/Silver/Gold— con versionado/cifrado/bloqueo de acceso público/ciclo de
vida/política, más el rol IAM de ingesta y su policy). El plan ha sido aprobado; esta
tarea lo aplica.

**Excepción explícita de alcance** (`allow_infra_apply: true`): tienes permiso para
ejecutar `terraform apply` sobre `infra/terraform/`, estrictamente limitado a lo que
ya está escrito en `infra/terraform/*.tf` (no añadas ni quites recursos, no cambies
el código Terraform en esta tarea) y a los comandos descritos a continuación. Nada de
`terraform destroy`.

## Objetivo

Aplicar la infraestructura del lakehouse tal como está definida en
`infra/terraform/` y dejar constancia auditable de lo creado.

## Alcance concreto

1. Dentro de `infra/terraform/`, recrea `backend.hcl` y `terraform.tfvars`
   (gitignored, no se commitean) a partir de sus `.example` — los valores por
   defecto coinciden exactamente con lo que ya existe en AWS (ver
   `doc/014-bootstrap-terraform-state-y-plan.md`), no hace falta ajustar nada.
2. `terraform init -backend-config=backend.hcl`.
3. `terraform plan -var-file=terraform.tfvars` de nuevo, como comprobación de que
   nada ha cambiado desde la tarea 014 (debería seguir mostrando 21 to add, 0 to
   change, 0 to destroy). Si el plan difiere de lo esperado, **detente y documenta
   la diferencia en `doc/015-aplicar-infraestructura-lakehouse.md` en vez de aplicar** — no apliques un plan
   que no coincide con lo ya revisado.
4. Si el plan coincide: `terraform apply -var-file=terraform.tfvars -auto-approve`.
5. Verifica lo creado con `aws` CLI directo (no solo confiando en la salida de
   Terraform): existencia de los 3 buckets, su versionado/cifrado/bloqueo de acceso
   público, y el rol IAM de ingesta con su policy adjunta.
6. Ejecuta `terraform output` y copia su resultado completo (nombres/ARNs de los 3
   buckets, ARN del rol y la policy de ingesta, account id) en el resumen de
   `doc/015-aplicar-infraestructura-lakehouse.md` — las próximas tareas de ingesta (capturas que ya existen:
   002-013) lo necesitarán para dejar de escribir muestras solo en local y empezar a
   escribir en el bucket Bronze real.
7. Como no hay cambios de código (`infra/terraform/*.tf` no se toca), el commit de
   esta tarea puede limitarse a `doc/015-aplicar-infraestructura-lakehouse.md`.

## Restricciones

- NO modifiques ningún fichero `.tf` de `infra/terraform/`. Si el plan no coincide
  con el ya revisado en la tarea 014, para y documenta — no apliques igualmente ni
  cambies código para que cuadre.
- NO ejecutes `terraform destroy` bajo ninguna circunstancia.
- No crees, modifiques ni borres ningún otro recurso de AWS fuera de lo que
  `infra/terraform/main.tf` ya describe.
- Si `terraform apply` falla a medio camino, documenta exactamente qué se llegó a
  crear (usando `aws` CLI para comprobar el estado real, no solo el mensaje de
  error) y qué falló — no reintentes borrando/recreando manualmente.

## Criterios de aceptación

- Los 3 buckets S3 (`madrono-tfm-dev-bronze-222234418587`,
  `-silver-...`, `-gold-...`) existen en AWS con versionado, cifrado y bloqueo de
  acceso público activos, verificado con `aws` CLI.
- El rol `madrono-tfm-dev-ingestion-role` existe con la policy
  `madrono-tfm-dev-ingestion-bronze-write` adjunta.
- `doc/015-aplicar-infraestructura-lakehouse.md` contiene la salida completa de `terraform output` y confirma
  explícitamente que el apply terminó sin error y coincidió con el plan ya revisado.
