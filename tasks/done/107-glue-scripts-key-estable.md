---
id: 107
slug: glue-scripts-key-estable
title: "Extender la key estable de procesamiento_source (FIL_09) a los 48 glue_script_*"
status: done
force: false
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-29T22:20:00+00:00"
updated_at: "2026-08-29T22:35:00+00:00"
started_at: "2026-08-29T22:20:00+00:00"
submitted_at: null
merged_at: null
---

## Contexto

Follow-up explícito de `FIL_09`/PR #175 (incidente de la tarea 106: 37/48
jobs de Glue rotos por una key con hash borrada). Esa tarea dejó anotados
dos *follow-ups* del mismo anti-patrón: `layer_build_source` y los 48
`glue_script_*`.

## Qué se hizo

Investigado primero si `layer_build_source` tiene el mismo riesgo real de
huérfanos — **no lo tiene** (sus dos consumidores derivan la key de la
misma expresión `local.layer_source_key`, siempre recalculada, nunca
congelada en el estado de otro recurso; además su diseño con hash es
deliberado, con una política de expiración de S3 que depende de ello). No
se toca.

Los 48 `aws_s3_object.glue_script_*` sí tienen el mismo riesgo estructural
que `procesamiento_source` (cada uno con exactamente un consumidor —su
`aws_glue_job` correspondiente— que congela la key resuelta en su propio
estado), solo que acotado a 1 job por incidente en vez de 37. Cambiados
los 48 a key estable (`glue-scripts/<nombre>.py`, sin hash; `etag` sigue
disparando la reescritura in situ) + `lifecycle { create_before_destroy =
true }` para la migración one-shot sin ventana de hueco.

Detalle completo, incluido el análisis de por qué `layer_build_source`
queda fuera, en
[`doc/107-glue-scripts-key-estable.md`](../doc/107-glue-scripts-key-estable.md).

## Verificación

- `terraform fmt -check -recursive` y `terraform validate`: limpios.
- Plan (solo lectura, Kafka excluido igual que `FIL_09`):
  `48 to add, 67 to change, 48 to destroy` — verificado con `grep` que no
  hay ninguna destrucción suelta (los 48 `destroy` son la mitad-baja de
  los 48 `must be replaced`, todos con `create_before_destroy` en efecto,
  símbolo `+/-`). `aws_s3_object.procesamiento_source` aparece como
  `updated in-place` (no *replace*), confirmando que el fix de `FIL_09`
  sigue vigente.

## Restricciones respetadas

- No se ha ejecutado ningún `terraform apply` — solo código, validado y
  planificado en modo lectura (`allow_infra_apply: false`).
- No se ha tocado `layer_build_source`, Kafka, ni ningún otro recurso.

## Pendiente

El `apply` de este cambio queda como paso aparte, a aprobar por un humano
(mismo criterio que `FIL_09`/tareas 098/100) — no es urgente, es una
mejora preventiva, no hay ningún job roto hoy.
