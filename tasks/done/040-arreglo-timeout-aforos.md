---
id: 40
slug: arreglo-timeout-aforos
title: Arreglar el timeout de la Lambda de aforos de peatones y bicicletas
status: done
force: true
allow_infra_apply: true
branch: task/040-arreglo-timeout-aforos
pr_number: 87
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/87
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-15T09:49:55+00:00'
updated_at: '2026-08-15T17:50:05.135106+00:00'
started_at: '2026-08-15T17:39:48.945183+00:00'
submitted_at: '2026-08-15T17:48:58.672799+00:00'
merged_at: '2026-08-15T17:49:02Z'
---

## Contexto

La tarea 033 invocó manualmente `madrono-tfm-dev-aforos_peatones_bicicletas` dos
veces (con `--cli-read-timeout 120` y luego `300`) y ambas terminaron en
`Sandbox.Timedout` a los 120.00s exactos (el `timeout` configurado en
`local.producers.aforos_peatones_bicicletas`, `infra/terraform/lambda.tf`). El log
solo muestra un `WARNING` inicial ("hay un recurso más reciente disponible que el
configurado") y nada más hasta el timeout — se cuelga en algún punto posterior,
muy probablemente una descarga de red sin `timeout=` explícito en la llamada a
`requests` contra el CSV real de datos.madrid.es (que en local, con datos de
prueba más pequeños, nunca se manifestó).

No es urgente por la cadencia (mensual, día 1), pero conviene resolverlo antes del
próximo disparo real.

**Excepción de alcance** (`allow_infra_apply: true`): permiso para invocar la
Lambda manualmente y, si hace falta subir el `timeout`/`memory_mb` en
`infra/terraform/lambda.tf`, para `terraform apply` ese cambio concreto (in-place).

## Objetivo

Diagnosticar y corregir la causa real del colgado, y confirmar con una invocación
real que la función completa sin timeout.

## Alcance concreto

1. Investiga `ingesta/capturas/aforos_peatones_bicicletas_madrid.py`: busca
   llamadas a `requests` (u otra librería HTTP) sin `timeout=` explícito,
   especialmente en la descarga de los CSV completos (~17-34 MB según documentó la
   tarea 013). Añade un timeout explícito razonable y manejo del error
   correspondiente (mismo patrón de reintentos con backoff que ya usan el resto de
   productores).
2. Si tras el arreglo de código el timeout de 120s de la Lambda sigue siendo
   insuficiente para descargar y procesar ambos CSV completos en el entorno real
   de Lambda, sube `timeout`/`memory_mb` en `local.producers.aforos_peatones_bicicletas`
   (`infra/terraform/lambda.tf`) a un valor razonable — documenta por qué el valor
   elegido.
3. Actualiza/añade tests si el cambio de código lo justifica.
4. Reconstruye el `.zip` (mismo mecanismo que la tarea 031/039) si hiciste cambios
   de código, y aplica cualquier cambio de Terraform.
5. Invoca manualmente la función (con un `--cli-read-timeout` generoso) y confirma
   que completa y escribe en Bronze, o que falla con un error explícito distinto
   de un timeout silencioso (p.ej. un error de red real, aceptable si está bien
   manejado).

## Restricciones

- NO ejecutes `terraform destroy`.
- No cambies la cadencia (mensual) de esta función salvo que tengas una razón de
  peso — no es el objetivo de esta tarea.

## Criterios de aceptación

- La causa raíz del colgado queda identificada y corregida (código, configuración
  de Lambda, o ambos).
- Una invocación manual real completa sin `Sandbox.Timedout`.
- `doc/040-arreglo-timeout-aforos.md` documenta el diagnóstico y el arreglo.
