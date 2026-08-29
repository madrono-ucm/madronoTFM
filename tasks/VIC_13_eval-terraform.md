---
kind: vic-eval
title: "Evaluación técnica — infra/terraform/ (drift real tras FIL_09/FIL_10)"
owner: Claude (QA)
status: pending
created_at: "2026-08-29"
---

Parte de [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md).
Solo lectura — ningún `apply`, ni siquiera si el drift pareciera trivial.

## Alcance

- `terraform fmt -check -recursive` + `terraform validate`.
- `terraform plan` real (con el método `-target` ya usado en `FIL_09`/`FIL_10`
  para excluir Kafka) — debería salir limpio o casi limpio tras los dos
  `apply` recientes.
- Revisar si queda algún otro recurso con el mismo anti-patrón de key con
  hash que `procesamiento_source`/`glue_script_*` tenían antes de
  `FIL_09`/`FIL_10` (aparte de `layer_build_source`, ya investigado y
  descartado a propósito en `doc/107`).

## Criterios de aceptación

- Resultado real de `plan`/`validate`/`fmt`.
- Confirmación de que Kafka sigue siendo el único drift real (o
  documentación de lo que aparezca).
- Cualquier hallazgo que implique un cambio de código, empaquetado como
  ticket `FIL_*` (nunca aplicado aquí).
