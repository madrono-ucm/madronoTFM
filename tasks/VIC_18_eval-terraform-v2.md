---
kind: vic-eval
title: "Evaluación técnica ronda 2 — Terraform, plan completo (no por PR)"
owner: Claude (QA)
status: pending
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
