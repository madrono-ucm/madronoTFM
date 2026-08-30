---
kind: vic-eval
title: "Evaluación técnica ronda 2 — Terraform, plan completo (no por PR)"
owner: Claude (QA)
status: done
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-2.md`](../doc/PLAN-EVALUACION-TECNICA-2.md).
Ningún cambio de infraestructura en este ticket (`terraform apply`
explícitamente fuera de alcance).

## Alcance

Cada `FIL_16`/`17` se verificó con un plan acotado a sus recursos nuevos
en el momento de aterrizar. Esta pasada mira el estado **agregado** tras
todos esos cambios juntos:

- `terraform validate` + `terraform fmt -check` sobre el árbol completo.
- `terraform plan` con `-target` construido desde `terraform state list`
  (excluyendo Kafka, nunca aplicado — mismo criterio que `VIC_13`), un
  solo plan que cubra `observabilidad.tf`, las políticas de secretos de
  `FIL_17`, y el resto — confirmar que no hay ninguna interacción
  inesperada entre los cambios de distintos PRs.
- Repasar `infra/terraform/variables.tf` — ¿queda alguna variable sin usar
  o duplicada tras tantos cambios?
- Confirmar que los recursos de `observabilidad.tf` (`FIL_16`) siguen sin
  aplicar (esperado, pipeline congelado) y que eso no deja el `plan` con
  ningún error o advertencia.

## Criterios de aceptación

- Un único `terraform plan` completo (no fragmentado por PR) documentado
  con su resultado exacto (to add/change/destroy).
- Sin errores de `validate`/`fmt`.
- Cualquier hallazgo (variable muerta, drift inesperado, interacción entre
  cambios) → ticket `FIL_*` nuevo.

## Restricciones

- Solo `plan`, nunca `apply`, en este ticket.

## Hecho (30/8)

Ver [`doc/VIC-18-eval-terraform-v2.md`](../doc/VIC-18-eval-terraform-v2.md).
`validate`/`fmt` limpios, plan agregado (335 recursos, Kafka excluido)
→ `2 to add, 54 to change, 0 to destroy`, sin errores. Sin
`Resource: "*"` en ninguna política IAM.

**Hallazgo de prioridad alta**: `FIL_17` (secretos SSM) sigue sin
`apply` real — a diferencia de `FIL_16`, esto es un fix de seguridad
activo (las 16 Lambda de producción siguen exponiendo credenciales en
claro ahora mismo). Nota añadida directamente al ticket `FIL_17`
existente, no se duplica.

**Hallazgo menor, ticket nuevo**: `lambda_default_timeout_seconds`/
`lambda_default_memory_mb` en `variables.tf` están completamente sin usar
— `local.producers` hardcodea cada timeout/memoria por productor, nunca
referencia estas variables pese a que su descripción dice lo contrario.
→ [`FIL_26`](FIL_26_terraform-variables-lambda-default-sin-usar.md).
