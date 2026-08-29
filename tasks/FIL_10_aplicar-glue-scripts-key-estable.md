---
kind: fil
title: "Aplicar la key estable de los 48 glue_script_* (código de la tarea 107, sin aplicar)"
owner: Filippos (interactive)
status: done
allow_infra_apply: true
created_at: "2026-08-29"
---

> **✅ RESUELTO 29/8** (sesión interactiva, `apply` aprobado por el usuario).
> Plan regenerado sobre `main`: `48 add / 48 change / 48 destroy` (no el
> `48/67/48` del doc — el `67→48` es porque los `apply` del fix de Bluesky,
> PR #177, ya habían reconciliado las 16 Lambdas + policy + codebuild).
> `terraform apply` limpio, Kafka excluido, sin destrucciones sueltas.
> Verificado en vivo: 48/48 `script_location` en `glue-scripts/<nombre>.py`
> sin hash, 0 huérfanos, `trafico_bronze_to_silver` → `SUCCEEDED` sobre la
> key nueva. `layer_build_source` sin tocar (descartado a propósito, ver
> `doc/107`). Detalle en `doc/107-...md` § "Resultado de la ejecución".

> **Contexto**: el código ya está mergeado en `main` (tarea 107, commit
> `7a97133`, `infra/terraform/glue.tf`) — extiende a los 48
> `aws_s3_object.glue_script_*` la key estable que `FIL_09`/PR #175 aplicó a
> `procesamiento_source`. Validado (`terraform fmt`/`validate` limpios) y
> planificado en modo lectura, pero **nunca aplicado**. El plan completo, la
> causa/razonamiento y el paso a paso de verificación ya están preparados en
> [`doc/FIL-10-terraform-plan-glue-scripts-key-estable.md`](../doc/FIL-10-terraform-plan-glue-scripts-key-estable.md)
> y en [`doc/107-glue-scripts-key-estable.md`](../doc/107-glue-scripts-key-estable.md)
> (el análisis completo, incluido por qué `layer_build_source` se descarta a
> propósito) — **léelos primero**, este ticket resume lo mínimo para
> decidir y ejecutar.

## Qué hace este cambio (ya en `main`, sin aplicar)

Cada uno de los 48 `aws_s3_object.glue_script_*` tiene exactamente **un**
consumidor (su `aws_glue_job` correspondiente, vía `script_location`), que
congela la key resuelta en su propio estado — el mismo riesgo estructural
que rompió 37/48 jobs durante >28h en la tarea 106 (`procesamiento_source`,
compartido por 37 jobs a la vez), aquí acotado a 1 job por incidente en vez
de 37, pero repetido 48 veces. El fix cambia la key de
`glue-scripts/<nombre>-<hash>.py` a `glue-scripts/<nombre>.py` (estable,
sin hash; `etag` sigue disparando la reescritura in situ) +
`lifecycle { create_before_destroy = true }` para la migración one-shot sin
ventana de hueco.

**No es urgente**: a diferencia de `FIL_09`, hoy no hay ningún job roto. Es
una mejora preventiva.

## El plan ya está generado y es seguro

Ver `doc/FIL-10-...md` para el plan íntegro. Resumen: **48 to add, 67 to
change, 48 to destroy** (Kafka excluido a propósito, nunca aplicado).
Verificado con `grep` que **ninguna destrucción es "suelta"** — cada
`destroy` es la mitad-baja de un par `must be replaced` con
`create_before_destroy` en efecto.

## Qué hacer

1. Lee `doc/FIL-10-...md` (resumen ejecutivo) y `doc/107-...md` (análisis
   completo, incluido por qué `layer_build_source` no se toca).
2. **Pide/confirma aprobación humana explícita antes de aplicar** — es
   `terraform apply` real sobre infraestructura de producción (mismo
   criterio que `FIL_09`/tareas 098/100), aunque no sea urgente.
3. `git pull` primero (puede haber más drift acumulado desde que se generó
   el plan de este documento).
4. Regenera el plan tú mismo antes de aplicar (sigue los comandos exactos
   de la sección "Cómo se generó este plan" de `doc/FIL-10-...md`) y
   compáralo contra el ya documentado: si el número total cambió mucho,
   investiga por qué antes de aplicar.
5. Aplica sobre el mismo conjunto de `-target` (excluyendo Kafka) que usa
   el plan documentado.
6. Verifica en vivo, no solo el código de salida de `apply`:
   - `aws glue get-jobs` — los `script_location`/`--extra-py-files`
     relevantes ya no llevan hash en la key.
   - Lanza o espera al siguiente disparo programado de un par de jobs al
     azar, confirma `SUCCEEDED`.
7. Añade el resultado como una sección nueva al final de
   `doc/107-glue-scripts-key-estable.md` (no crees un `doc/` nuevo) y
   marca esta ficha como resuelta.
8. Actualiza `PLAN.md`/`FIL_00_README.md` si corresponde.

## Restricciones

- No toques la infraestructura de Kafka (tarea 042) — sigue excluida a
  propósito de cualquier `apply`.
- No apliques sin aprobación humana explícita.
- No toques `layer_build_source` — investigado y descartado a propósito
  (ver `doc/107-...md`), no es un bug.
- Si el `apply` no cierra el problema del todo, no lo des por bueno —
  investiga la causa en vez de reintentar a ciegas.

## Criterios de aceptación

- Los 48 `glue_script_*` en S3 con key estable, sin hash.
- Al menos una ejecución real `SUCCEEDED` verificada tras el `apply`.
- `doc/107-...md` ampliado con el resultado real de la ejecución.
