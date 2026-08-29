---
kind: vic-eval
title: "Evaluación técnica — infra/terraform/ (drift real tras FIL_09/FIL_10)"
owner: Claude (QA)
status: done
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

## Hecho (29/8)

- `terraform fmt -check -recursive` y `terraform validate`: limpios.
- `terraform plan` real (Kafka excluido): **`0 to add, 66 to change, 0 to
  destroy`** — **cero reemplazos**. Los 48 `glue_script_*` y
  `procesamiento_source` aparecen todos como `updated in-place` (no `must
  be replaced`), confirmando que la key estable de `FIL_09`/`FIL_10` sigue
  funcionando exactamente como se diseñó, incluso tras nuevos cambios de
  código reales (p. ej. `modelado/features/exogenas.py`, ver `VIC_12`). Los
  66 `change` son actualizaciones legítimas de contenido (`etag`/hash de
  Lambda) por trabajo real de otras sesiones, no drift estructural.
- No se ha encontrado ningún otro recurso con el mismo anti-patrón de key
  con hash aparte de `layer_build_source` (ya investigado y descartado a
  propósito en `doc/107`).
- Sin hallazgos que requieran un ticket `FIL_*`.
