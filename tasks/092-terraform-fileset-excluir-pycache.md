---
id: 92
slug: terraform-fileset-excluir-pycache
title: 'QA: terraform plan/apply crashea si existe __pycache__ local en ingesta/ (fileset
  sin excluir bytecode)'
status: in_progress
force: false
allow_infra_apply: false
branch: task/092-terraform-fileset-excluir-pycache
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-26T10:45:00+00:00'
updated_at: '2026-08-26T10:37:18.521264+00:00'
started_at: '2026-08-26T10:37:18.521241+00:00'
submitted_at: null
merged_at: null
---

## Hallazgo de QA (verificado en vivo, no especulativo)

Ticket de QA — código real, no hipotético. Reproducido en esta misma sesión:
tras ejecutar la suite de tests de `ingesta/` localmente (lo cual genera
`__pycache__/` con ficheros `.pyc`, algo que cualquier desarrollador hace de
forma rutinaria antes de tocar Terraform), `terraform plan` en
`infra/terraform/` **falla por completo** con errores como:

```
Call to function "file" failed: contents of
"./../../ingesta/capturas/__pycache__/ser_calles_madrid.cpython-314.pyc" are
not valid UTF-8; use the filebase64 function...
```

## Causa raíz

En `infra/terraform/lambda.tf`, el local `ingesta_source_files` (línea ~333)
construye la lista de ficheros a empaquetar con:

```hcl
ingesta_source_files = [
  for f in fileset(local.ingesta_source_root, "**") :
  f
  if !startswith(f, "tests/") && !startswith(f, "capturas/samples/")
]
```

Solo excluye `tests/` y `capturas/samples/` — no excluye `__pycache__/` ni
`*.pyc`/`*.pyo`. `__pycache__/` está en `.gitignore` (no se commitea nunca),
así que un checkout limpio nunca lo tiene, pero **cualquier sesión que haya
corrido `python3 -m unittest` sobre `ingesta/` antes de ejecutar
`terraform plan`/`apply` lo revienta** — y eso incluye, potencialmente, a
quien ejecute la futura tarea de "apply" del drift de Terraform (Prioridad 1
de `NEXT_STEPS.md`), si antes ha corrido los tests como parte de su
verificación (patrón habitual y recomendado en este proyecto).

## Objetivo

Excluir `__pycache__/` y cualquier `.pyc`/`.pyo` del fileset, para que
`terraform plan`/`apply` sea reproducible sin depender de si el entorno
local tiene bytecode cacheado o no.

## Alcance concreto

1. En `infra/terraform/lambda.tf`, añade una condición al filtro de
   `ingesta_source_files` para excluir cualquier ruta que contenga
   `__pycache__/` o termine en `.pyc`/`.pyo` (p. ej.
   `!strcontains(f, "__pycache__/") && !endswith(f, ".pyc") && !endswith(f, ".pyo")`
   — usa las funciones de Terraform que correspondan a la versión instalada,
   verifícalo).
2. Reproduce el bug primero (genera `__pycache__` corriendo los tests de
   `ingesta/`, confirma que `terraform plan` falla tal cual se describe
   arriba), aplica el fix, y confirma que `terraform plan` ya no falla por
   este motivo con `__pycache__` presente.
3. Verifica que el fix no cambia el contenido real del paquete Lambda para
   un checkout limpio (sin `__pycache__`) — el `plan` no debería mostrar
   ningún cambio adicional en `aws_s3_object.procesamiento_source` ni en las
   funciones Lambda por este cambio en un checkout limpio.

## Restricciones

- Solo toca `infra/terraform/lambda.tf` (el filtro del fileset). No apliques
  nada (`allow_infra_apply: false`) — esto es una tarea de "plan", no de
  "apply", igual que la tarea 088.
- No toques la lógica del drift ya documentado en
  [`doc/088-terraform-drift-plan-sin-aplicar.md`](../doc/088-terraform-drift-plan-sin-aplicar.md)
  — ese plan sigue necesitando una recaptura aparte (ver ticket de
  seguimiento en `PLAN.md`), este ticket es solo sobre la fiabilidad del
  propio comando `terraform plan`.
- Documenta en `doc/092-...md` el antes/después (el error reproducido, el
  fix, y la confirmación de que un `terraform plan` limpio no cambia).

## Criterios de aceptación

- `terraform plan` no falla aunque exista `__pycache__/` real bajo
  `ingesta/`.
- `doc/092-...md` documenta el hallazgo y la verificación.
- Hay un commit real.
