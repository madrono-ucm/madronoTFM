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

## Adenda QA (`VIC_33`, 2026-09-01) — la causa raíz es más profunda de lo que dice el contexto de arriba, y hay un riesgo destructivo real

Verificado en vivo (`terraform plan` completo, sin `-target`, contra el
estado real de AWS) que el problema **no es solo** "la layer desplegada
no tiene `defusedxml` todavía" — es que **`var.lambda_dependencies_layer_arn`
sigue en `null` en `terraform.tfvars`** (confirmado: no aparece en
`terraform.tfvars` ni `.tfvars.example`; `lambda_layer_build.tf:29` ya lo
documentaba como pendiente de la tarea 033). Como
`lambda.tf:546` es `layers = var.lambda_dependencies_layer_arn == null ? []
: [...]`, el **estado deseado real hoy es "sin layer en absoluto"**, no
solo "layer desactualizada".

**Consecuencia verificada**: el `terraform plan` completo de hoy muestra,
para las **16** `aws_lambda_function.producer[*]`, un diff
`~ layers = [ - "arn:...:layer:madrono-tfm-dev-ingesta-dependencies:1" ]`
**sin ningún `+`** — es decir, un `terraform apply` sin `-target` hoy
**quitaría la layer de las 16 Lambdas por completo** (no la actualizaría a
una versión nueva), lo que rompería el `import` de cualquier dependencia
de terceros que vaya en la layer y no en el `.zip` de código propio
(`netCDF4` y similares, ver el motivo original de usar CodeBuild en
`lambda_layer_build.tf`). Con el pipeline congelado no se ejecuta, así
que no ha roto nada todavía, pero es un `apply` sin `-target` de distancia
de un incidente real.

**Efecto colateral encontrado**: ese mismo drift hace que
`aws_iam_policy.scheduler_invoke_lambda` (cuya `data
"aws_iam_policy_document"` itera `[for fn in aws_lambda_function.producer :
fn.arn]`) aparezca en el plan como `policy = ... -> (known after apply)`
con el `Statement` completo marcado `-` sin reemplazo — el mismo síntoma
transitorio que `VIC_33` esperaba que **ya hubiera quedado estable** tras
el `apply` del 2026-09-01, y que sigue sin estabilizar porque la causa
(Lambdas con cambio pendiente) sigue viva.

**Implicación para la opción A de arriba**: al reconstruir la layer, hace
falta **además** fijar `lambda_dependencies_layer_arn` en
`terraform.tfvars` al ARN real de la nueva versión — reconstruir solo el
`.zip`/CodeBuild sin fijar la variable deja el mismo problema (`layers=[]`
deseado) intacto.

Los ~35 `aws_s3_object.glue_script_*` que también aparecen en el plan
completo son ruido benigno de fin de línea/espacios (contenido idéntico
carácter a carácter salvo esa normalización) — verificado, no relacionado
con este drift.
