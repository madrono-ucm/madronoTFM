---
kind: fil
title: "URGENTE — Reparar 37/48 jobs de Glue rotos: librería compartida procesamiento.zip inexistente en S3"
owner: Filippos (interactive)
status: pending
allow_infra_apply: true
created_at: "2026-08-29"
---

> **Contexto**: encontrado durante una ronda de QA (sesión del 29/8) al revisar
> la factura real de AWS con `herramientas/costes/desglose_glue.py`. El plan
> completo, la causa raíz y el paso a paso de verificación ya están preparados
> en [`doc/FIL-09-terraform-plan-glue-libreria-compartida.md`](../doc/FIL-09-terraform-plan-glue-libreria-compartida.md)
> — **léelo primero**, este ticket resume lo mínimo para decidir y ejecutar.
>
> **Actualización (29/8, tarde)**: otra sesión ya aplicó un fix de código
> mejor que el plan original (`glue.tf`, commit `89f0665`, PR #175): key
> **estable** para `procesamiento.zip` en vez de resincronizar a otro hash
> — un futuro `apply` parcial ya no puede volver a romper esto. Sigue sin
> aplicarse. Plan **regenerado** sobre ese commit al final del documento
> (misma magnitud, `49 add / 66 change / 49 destroy`, sigue sin
> destrucciones sueltas) — **usa esa versión del plan, no la de arriba**.

## Qué está roto (verificado en vivo, no es una sospecha)

**37 de 48 jobs de Glue (77 %) fallan en `LAUNCH ERROR`** desde al menos el
2026-08-28 15:13 (>28 horas a fecha de este ticket) porque su
`--extra-py-files` apunta a un `procesamiento-<hash>.zip` en S3 que no existe:

- 27 jobs → hash A (no existe)
- 10 jobs → hash B, distinto (tampoco existe)
- 1 job → hash C, el único objeto real en el bucket
- `main` actual del repo ya calcula un hash D, ni siquiera desplegado

Terraform `state` coincide con el hash C (el real) — confirma que el problema
no es de Terraform en sí, sino de **aplicaciones parciales previas**
(`-target=...` sobre subconjuntos de recursos) que dejaron distintos jobs
anclados a generaciones ya borradas del fichero compartido. Mismo patrón de
fondo que el incidente de finales de línea de la tarea 100.

**Impacto real, ya ocurriendo**: Bronze→Silver roto para `trafico`,
`bicimad`, `transporte_publico_emt`, `meteorologia`, `calidad_aire` y
`aparcamientos` — 6 de los 16 "productores en producción continua" de la
memoria. Confirmado de forma independiente: `calidad_aire_prevista` (tool del
asistente, verificada en vivo la misma sesión) no encuentra ninguna fila de
Gold posterior a 2026-08-28 15:00.

## El plan ya está generado y es seguro

Ver el documento completo para el plan íntegro y cómo se generó. Resumen:
**49 to add, 66 to change, 49 to destroy** (Kafka excluido a propósito, nunca
aplicado). Verificado con `grep` que **ninguna destrucción es "suelta"** —
cada `destroy` es la mitad de un par `must be replaced` (reemplaza un objeto
S3 obsoleto por el real de `main`, no borra nada sin reponerlo).

## Qué hacer

1. Lee [`doc/FIL-09-...md`](../doc/FIL-09-terraform-plan-glue-libreria-compartida.md)
   completo (o al menos el resumen ejecutivo y el desglose por tipo de
   recurso).
2. **Pide/confirma aprobación humana explícita antes de aplicar** — es
   `terraform apply` real sobre infraestructura de producción (mismo criterio
   que las tareas 098/100), aunque la urgencia sea alta.
3. `git pull` primero (puede haber más drift acumulado desde que se generó
   el plan de este documento).
4. Regenera el plan tú mismo antes de aplicar (no confíes en el de ayer sin
   refrescarlo — sigue los comandos exactos de la sección "Cómo se generó
   este plan" del documento) y compáralo contra el ya documentado: si el
   número total cambió mucho, algo más se movió mientras tanto — investiga
   por qué antes de aplicar.
5. Aplica sobre el mismo conjunto de `-target` (excluyendo Kafka) que usa el
   plan documentado.
6. Verifica en vivo, no solo el código de salida de `apply`:
   - `aws glue get-jobs` — todos los `--extra-py-files` en el mismo hash, y
     ese objeto existe en S3.
   - Lanza o espera al siguiente disparo programado de al menos uno de los 6
     jobs que fallaban, confirma `SUCCEEDED`.
   - Athena: filas nuevas (posteriores a 2026-08-28 15:00) para los 6
     datasets afectados.
7. Añade el resultado como una sección nueva al final de
   `doc/FIL-09-...md` (no crees un `doc/` nuevo).
8. Actualiza `PLAN.md` (quita el bloqueador 0) y `NEXT_STEPS.md`.
9. Si sigues el patrón de la tarea 106 (tarea numerada equivalente, creada
   antes de decidir moverlo a `FIL_*`): márcala como redirigida a este
   ticket, no la dejes como un trabajo pendiente duplicado para el demonio.

## Restricciones

- No toques la infraestructura de Kafka (tarea 042) — sigue excluida a
  propósito de cualquier `apply`.
- No apliques sin aprobación humana explícita, por urgente que sea.
- Si el `apply` no cierra el problema del todo (siguen quedando jobs con
  hashes distintos entre sí), no lo des por bueno — investiga la causa en
  vez de reintentar a ciegas.

## Criterios de aceptación

- 0 de 48 jobs de Glue con `--extra-py-files` apuntando a un objeto S3
  inexistente.
- Al menos una ejecución real `SUCCEEDED` de cada uno de los 6 jobs que
  estaban fallando, verificada tras el `apply`.
- Datos frescos en Athena (posteriores a 2026-08-28 15:00) para los 6
  datasets afectados.
- `doc/FIL-09-...md` ampliado con el resultado real de la ejecución.
