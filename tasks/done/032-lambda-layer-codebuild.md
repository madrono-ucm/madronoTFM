---
id: 32
slug: lambda-layer-codebuild
title: Lambda Layer de dependencias de terceros vía AWS CodeBuild
status: done
force: true
allow_infra_apply: true
branch: task/032-lambda-layer-codebuild
pr_number: 79
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/79
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-14T21:41:18+00:00'
updated_at: '2026-08-14T22:05:28.980204+00:00'
started_at: '2026-08-14T21:50:46.842325+00:00'
submitted_at: '2026-08-14T22:04:22.498092+00:00'
merged_at: '2026-08-14T22:04:25Z'
---

## Contexto

Las 14 Lambdas de producción (tareas 029-031) todavía no tienen las dependencias de
terceros de `ingesta/requirements.txt` (`requests`, `beautifulsoup4`, `cdsapi`,
`netCDF4`, `populartimes`) — se dejaron fuera deliberadamente (tarea 029) porque
esta EC2 no puede construir una Lambda Layer con extensiones compiladas
(`netCDF4` en particular) sin una herramienta de build compatible con el runtime
de Lambda. La decisión ya tomada es usar **AWS CodeBuild** para eso: gestionado
por AWS, sin instalar nada en esta EC2 ni gastar su disco.

`infra/terraform/lambda.tf` ya tiene preparado el enganche:
`variable "lambda_dependencies_layer_arn"` (default `null`) — cuando exista una
Layer, basta con fijar su ARN para que las 14 funciones la usen (eso es la tarea
033, no esta).

## Objetivo

Construir, vía Terraform + AWS CodeBuild, una Lambda Layer de Python 3.13 con las
dependencias de `ingesta/requirements.txt`, y dejarla publicada en AWS (no hace
falta conectarla a las funciones todavía).

## Alcance concreto

1. Añade a `infra/terraform/` (nuevo fichero, p.ej. `lambda_layer_build.tf`):
   - Un `aws_codebuild_project` que use una imagen compatible con el runtime de
     Lambda (imagen pública de AWS SAM/Lambda para build, p.ej.
     `public.ecr.aws/sam/build-python3.13`, verifica el nombre exacto vigente) y
     un `buildspec` (inline o `buildspec.yml` versionado en el repo, decide y
     documenta) que: instale `ingesta/requirements.txt` en un directorio
     `python/` (convención de Lambda Layers: lo que cuelga de `python/` queda en
     el `sys.path` del runtime), lo comprima, y lo suba a un bucket S3 (puede ser
     un prefijo nuevo dentro del propio bucket Bronze, o un bucket nuevo pequeño
     para artefactos de build — decide y documenta el criterio).
   - Rol IAM para CodeBuild (permisos mínimos: logs, leer el código fuente,
     escribir el artefacto en S3).
   - Un `aws_lambda_layer_version` que referencie ese artefacto S3, con
     `compatible_runtimes = ["python3.13"]` (o la versión real que usen las 14
     funciones — verifícalo).
2. Dispara el build (`aws codebuild start-build`) y espera a que termine.
   Verifica con `aws lambda list-layer-versions` que la Layer quedó publicada.
3. NO conectes todavía la Layer a las 14 funciones (`lambda_dependencies_layer_arn`
   sigue en `null` en `terraform.tfvars` tras esta tarea) — eso es la 033.
4. Documenta en `doc/032-lambda-layer-codebuild.md` el ARN de la Layer publicada
   (la 033 lo necesitará como contexto).

## Restricciones

- NO modifiques `terraform.tfvars` para fijar `lambda_dependencies_layer_arn` —
  esta tarea solo construye y publica la Layer, no la conecta.
- NO toques las 14 `aws_lambda_function` existentes.
- Si `netCDF4`/`cdsapi` complican el build (extensiones nativas, tiempo de build
  largo) más de lo razonable, documenta el problema concreto en
  `doc/032-lambda-layer-codebuild.md` — no se descarta de antemano incluirlas
  (el humano ya decidió ir por CodeBuild precisamente para poder incluirlas), pero
  si el build falla repetidamente por esto, es información valiosa a reportar,
  no algo que forzar a cualquier precio.

## Criterios de aceptación

- Una Lambda Layer de Python 3.13 con las dependencias de `ingesta/requirements.txt`
  existe y está publicada en AWS (verificado con `aws lambda list-layer-versions`).
- `doc/032-lambda-layer-codebuild.md` documenta el ARN de la Layer y cualquier
  dependencia que haya quedado fuera, con el motivo.
