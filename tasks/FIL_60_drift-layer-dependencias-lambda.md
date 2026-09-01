---
kind: fil
title: "Resolver el drift de la layer de dependencias Lambda (defusedxml de FIL_41 no está desplegado)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: true
depends_on: [FIL_41]
---

## Contexto

Un `terraform plan` completo hoy incluye, aparte de Kafka (excluido a
propósito) y del sink SNS de `FIL_16` (bloqueado por IAM), esto:

```
aws_s3_object.layer_build_source          must be replaced
aws_codebuild_project.lambda_dependencies_layer   update in-place
```

Es el flujo de dos aplicaciones de la layer de dependencias
(`infra/terraform/lambda_layer_build.tf`, `doc/032`): `ingesta/requirements.txt`
cambió (`defusedxml`, `FIL_41`) y la layer desplegada **no lo tiene**. Con
el pipeline congelado no se nota (las Lambda no corren), pero es una
inconsistencia real entre el repo y lo desplegado.

## Objetivo

Una de dos, decidir cuál:

**A — Aplicarlo** (si se va a reanudar la ingesta pronto):
1. `terraform apply -target=aws_s3_object.layer_build_source
   -target=aws_codebuild_project.lambda_dependencies_layer` (primera
   pasada: sube el nuevo `.zip` de fuente + actualiza el proyecto
   CodeBuild).
2. Lanzar el build de CodeBuild y esperar (`doc/032` tiene el flujo).
3. Segunda pasada: `terraform apply -target=aws_lambda_layer_version...`
   (+ re-`apply` de `aws_lambda_function.producer` para que apunten a la
   nueva versión de la layer).
4. Verificar que un productor que use XML (`aemet_prevision_avisos`,
   `agenda_eventos`, …) importa `defusedxml` sin error
   (`aws lambda invoke`).

**B — Documentar el aplazamiento** (si la ingesta sigue congelada hasta
la entrega): nota en `doc/032` / `infra/OPERACION.md` de que la layer
tiene drift conocido y benigno (pipeline congelado), y de que
`FIL_40`/`FIL_41` viven en el `.zip` de código de las funciones (ya
desplegado por el `apply` de `FIL_17`) pero **no** en la layer de
dependencias; hay que reconstruir la layer antes de reanudar.

## Criterios de aceptación

- Opción A: `terraform plan` deja de mostrar los dos recursos de la
  layer; un productor con XML invoca sin error de import.
- Opción B: el drift queda documentado donde un futuro "reanudar el
  pipeline" lo encuentre (OPERACION.md + doc/032), y este ticket → `done`
  con la decisión registrada.

## Restricciones

- `allow_infra_apply: true` pero **solo** para los recursos de la layer;
  cualquier `apply` sigue el patrón `-target` para no arrastrar Kafka.
- No reanudar el pipeline (`pipeline_enabled`) como efecto colateral.
