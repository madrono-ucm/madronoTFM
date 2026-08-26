---
id: 93
slug: recapturar-plan-drift-terraform-real
title: 'QA: el plan de drift de doc/088 está obsoleto (55 cambios reales frente a
  los 15 documentados)'
status: in_progress
force: false
allow_infra_apply: false
branch: task/093-recapturar-plan-drift-terraform-real
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-26T10:50:00+00:00'
updated_at: '2026-08-26T10:56:15.199649+00:00'
started_at: '2026-08-26T10:56:15.199625+00:00'
submitted_at: null
merged_at: null
---

## Hallazgo de QA (verificado en vivo, no especulativo)

`doc/088-terraform-drift-plan-sin-aplicar.md` (25/8) documentó el drift real
de Terraform como **`5 to add, 15 to change, 0 to destroy`**, y
`NEXT_STEPS.md` (Prioridad 1, punto 3) lo describe como el plan pendiente de
revisión humana antes de crear la tarea de "apply".

Ejecutado de nuevo hoy (26/8), tras arreglar primero el bloqueador de
`__pycache__` (ver tarea 092 — **hazla primero, o tu `terraform plan` puede
fallar por ese motivo si tu entorno tiene bytecode cacheado**), el plan real
es:

```
Plan: 10 to add, 55 to change, 5 to destroy.
```

Muy por encima de lo documentado. Revisando el detalle: la mayoría de los
"55 to change" son **las 14 funciones Lambda + ~40 Glue jobs actualizándose
en cascada** porque el paquete compartido (`aws_s3_object.procesamiento_source`)
y 4 scripts de Glue (`cartelera_cines_estrenos`, `bluesky_menciones`,
`agenda_eventos`, `aforos_peatones_bicicletas`, todos `silver_to_gold`)
cambiaron de contenido — esto coincide con el "drift deliberado" que la
tarea 090 dejó documentado (arregló el bug de `Column 'fecha' does not
exist` en esos 4 datasets desplegando directamente a S3, sin pasar por
Terraform). Los "5 to destroy"/"5 to add" adicionales son remplazos
(`must be replaced`) de esos mismos 5 objetos S3 — consistente, no parece
alarmante en sí mismo.

**Pero el número que el equipo cree estar revisando (15 cambios) ya no es
el número real (55 cambios)** — si la tarea de "apply" (punto 3 de la
Prioridad 1) se crea citando el plan de `doc/088`, quien la ejecute
aplicaría un conjunto de cambios sustancialmente mayor al que fue aprobado.

## Nota relacionada (observación, no requiere acción de este ticket)

Durante esta misma revisión se observó una ejecución real de
`madrono-tfm-dev-cartelera-cines-estrenos-silver-to-gold` fallando a las
09:42 de hoy con exactamente el error `Column 'fecha' does not exist` que
la tarea 090 dijo haber corregido, y la siguiente ejecución (09:54) ya
`SUCCEEDED`. Es coherente con un despliegue manual a S3 (fuera de
Terraform) aterrizando a mitad de la ventana de observación — no se ha
encontrado ningún fallo persistente, solo se deja constancia por si vuelve
a aparecer.

## Objetivo

Recapturar el plan de drift real y ponerlo delante de la revisión humana,
para que el punto 3 de la Prioridad 1 de `NEXT_STEPS.md` (la tarea de
"apply") se cree sobre datos actuales, no sobre los de hace un día.

## Alcance concreto

1. Confirma que la tarea 092 (fileset sin `__pycache__`) ya está fusionada
   — si no, tu `terraform plan` puede fallar por ese motivo, no por drift
   real.
2. Ejecuta `terraform plan` sin acotar en `infra/terraform/` (con
   `terraform init -backend-config=backend.hcl` primero si hace falta) y
   vuelca el resultado íntegro, igual que hizo `doc/088`.
3. Compara contra `doc/088`: qué recursos nuevos aparecen, cuáles
   coinciden, y documenta explícitamente por qué el número total subió
   (la hipótesis del despliegue manual de la tarea 090 de arriba, verificada
   contra el `terraform plan` real, no solo asumida).
4. Actualiza `NEXT_STEPS.md` (Prioridad 1, punto 2) y añade una nota en
   `doc/088-...md` (no lo reescribas, añade una sección "Actualización
   26/8" al final) señalando que el plan cambió y por qué.
5. **No crees tú la tarea de "apply"** — solo deja el plan actualizado listo
   para que un humano lo revise, igual que se hizo con la 088 original.

## Restricciones

- `allow_infra_apply: false` — es una tarea de "plan", no de "apply", no
  ejecutes `terraform apply` bajo ningún concepto.
- No toques scripts de Glue ni código de `procesamiento/`/`ingesta/` — si
  encuentras algo que corregir ahí, documéntalo, no lo arregles en esta
  tarea.
- Documenta en `doc/093-...md` el plan completo (igual que `doc/088`) y el
  análisis de la diferencia.

## Criterios de aceptación

- `doc/093-...md` contiene el `terraform plan` real, completo, de hoy.
- `NEXT_STEPS.md` y `doc/088-...md` reflejan que el plan se recapturó y por
  qué cambió.
- Hay un commit real, sin ningún `terraform apply` ejecutado.
