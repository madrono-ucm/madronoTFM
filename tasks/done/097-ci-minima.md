---
id: 97
slug: ci-minima
title: 'CI mínima (Prioridad 5): tests + terraform fmt/validate en cada PR'
status: done
force: false
allow_infra_apply: false
branch: task/097-ci-minima
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: null
updated_at: '2026-08-26T14:15:00Z'
started_at: '2026-08-26T14:00:00Z'
submitted_at: '2026-08-26T14:15:00Z'
merged_at: null
---

## Contexto

Con la Prioridad 4 (tools del asistente) completa, siguiente ítem de
`NEXT_STEPS.md`: no existía ningún `.github/workflows/` — nada corría los
841 tests reales del proyecto automáticamente en cada PR.

## Qué se hizo

`.github/workflows/ci.yml`, dos jobs: `tests` (pytest real sobre
`ingesta`/`procesamiento`/`grafo`/`asistente`/`herramientas`, sin
credenciales) y `terraform` (`fmt -check` + `validate` con
`init -backend=false`, deliberadamente sin credenciales AWS ni
`terraform plan` — esa parte necesita que quien administra el repositorio
configure un secreto, no es una decisión de esta tarea).

Montando la CI se encontraron y corrigieron 2 bugs reales preexistentes:
un nit de formato en `infra/terraform/lambda.tf` (de la tarea 092, PR
#136) que bloqueaba `terraform fmt -check`, y 3 tests con
`Path.read_text()` sin `encoding="utf-8"` explícito que fallaban en
Windows (nunca en Linux/CI) — varias sesiones los habían visto y
descartado como "fallo preexistente no relacionado" sin arreglarlos. La
suite completa queda en verde: 841 passed, 1 skipped, 0 fallos.

Detalle completo en `doc/097-ci-minima.md`.

## Restricciones respetadas

- Ningún `terraform apply`/`plan` real ni credenciales AWS añadidas a
  ningún sitio.
- No se ha tocado el drift de Terraform de la Prioridad 1 (en curso por
  `madrono-agent`).
