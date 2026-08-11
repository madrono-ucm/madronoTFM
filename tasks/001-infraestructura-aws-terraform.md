---
id: 1
slug: infraestructura-aws-terraform
title: Infraestructura base en AWS (Terraform)
status: in_progress
force: true
branch: task/001-infraestructura-aws-terraform
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-11T23:03:46+00:00'
updated_at: '2026-08-11T23:40:18.849929+00:00'
started_at: '2026-08-11T23:04:53.485162+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Este proyecto (TFM «Madroño», ver `documents/Memoria_TFM FV.docx`) necesita una
infraestructura AWS mínima para arrancar la Fase 1 del plan del proyecto (Ingesta,
Tabla 1 de la memoria): un lakehouse medallón (Bronze/Silver/Gold) sobre AWS. El coste
cero/mínimo es una premisa explícita del proyecto (apartado 5.4 de la memoria).

## Objetivo

Define y escribe (sin aplicar) el código Terraform del andamiaje base de
infraestructura para el lakehouse.

## Alcance concreto

1. Crea `infra/terraform/` como nuevo directorio en la raíz del repo (junto a
   `tasks/`, `documents/`, `doc/`) con una estructura Terraform estándar: `main.tf`,
   `variables.tf`, `outputs.tf`, `versions.tf` (fija la versión de Terraform y del
   provider `aws`).
2. Backend de estado remoto (S3 + tabla DynamoDB de locking). Como el propio bucket
   de estado no puede crearse con el mismo Terraform que lo usa, documenta en el
   README el paso 0 manual (crear ese bucket/tabla a mano, una vez, antes del primer
   `terraform init`) — no lo automatices dentro de este mismo proyecto.
3. Define los buckets S3 del lakehouse medallón (Bronze/Silver/Gold) — decide si
   usas un bucket por capa o uno solo con prefijos, y documenta por qué. Activa
   versionado y una política de ciclo de vida razonable para minimizar coste
   (transición a clase de almacenamiento más barata o expiración de versiones
   antiguas).
4. Define un rol IAM (con su policy) pensado para que lo asuman los futuros
   servicios de ingesta (productores de datos) con permisos mínimos de escritura
   sobre el bucket/prefijo Bronze — nada de permisos amplios.
5. Usa variables para la región (España/UE — valora `eu-west-1` o `eu-south-2`,
   decide y documenta por qué) y para el nombre/prefijo del proyecto; no
   hardcodees nombres de recursos.
6. Escribe `infra/terraform/README.md` explicando: qué hace cada recurso, cómo se
   ejecutaría `terraform init/plan/apply` manualmente (pero NO lo ejecutes tú), y
   — esto es lo más importante de esta tarea — **qué permisos de IAM necesitaría la
   identidad (usuario o rol) que vaya a ejecutar `terraform apply`** para crear
   estos recursos. Lista las acciones IAM concretas necesarias (S3, IAM, DynamoDB,
   STS...); no te limites a decir "AdministratorAccess".
7. Añade un `.gitignore` (o amplía el de la raíz) para `*.tfstate`,
   `*.tfstate.backup`, `.terraform/`, `*.tfvars`.

## Restricciones

- NO ejecutes `terraform init`/`plan`/`apply` ni ningún comando `aws` con efectos
  reales. Solo escribe y documenta el código — aplicarlo es una decisión y un paso
  manual posterior de un humano. (No hace falta que ejecutes `terraform validate`
  tampoco: es posible que el binario ni siquiera esté instalado en este entorno;
  basta con que el HCL sea correcto a tu buen juicio.)
- No metas secretos ni credenciales en ningún archivo.
- Mantén el coste mínimo como principio de diseño: evita en esta tarea recursos
  gestionados caros (p.ej. no crees un clúster MSK completo — eso, si hace falta,
  es una decisión para una tarea posterior una vez validado el resto).

## Criterios de aceptación

- `infra/terraform/` contiene un proyecto Terraform completo y sintácticamente
  correcto para los recursos descritos arriba.
- El README documenta con claridad los permisos IAM necesarios para aplicar la
  infraestructura y dónde queda pendiente el paso manual.
- No se ha ejecutado ningún comando con efectos reales en AWS.
