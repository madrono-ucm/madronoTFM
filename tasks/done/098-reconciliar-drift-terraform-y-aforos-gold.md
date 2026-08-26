---
id: 98
slug: reconciliar-drift-terraform-y-aforos-gold
title: 'Prioridad 1 y 2: aplicar el drift real de Terraform y desbloquear el Gold de aforos_peatones_bicicletas'
status: done
force: false
allow_infra_apply: true
branch: task/098-reconciliar-drift-terraform-y-aforos-gold
pr_number: null
pr_url: null
attempts: 1
next_retry_at: null
last_error: null
created_at: '2026-08-26T17:00:00+00:00'
updated_at: '2026-08-26T17:45:00+00:00'
started_at: '2026-08-26T17:00:00+00:00'
submitted_at: '2026-08-26T17:45:00+00:00'
merged_at: null
---

## Objetivo

A petición directa del usuario ("work on the priority 1 and 2 and that you
start fixing the issues and fill the missing pieces"), ejecutar el trabajo
que `NEXT_STEPS.md` llevaba desde el 25/8 marcando como Prioridad 1 y 2:

1. **Prioridad 1**: revisar el plan real de Terraform (`doc/093`, pendiente
   de revisión humana) y aplicarlo, excluyendo deliberadamente la
   infraestructura de Kafka (tarea 042, nunca debe aplicarse sin que se
   pida explícitamente).
2. **Prioridad 2**: verificar en vivo, tras el `apply`, que el fix de
   partition projection de `aforos_peatones_bicicletas` (escrito en
   `infra/terraform/glue.tf` desde la tarea 087, nunca aplicado) desbloquea
   de verdad ese Gold.

## Restricciones

- No aplicar los recursos de Kafka (`aws_instance.kafka` y dependientes) —
  deliberadamente excluidos por todos los `doc/` previos.
- Revisar el plan completo, recurso por recurso, antes de aplicar nada real
  — no confiar solo en el resumen `N to add/change/destroy`.
- Pedir confirmación explícita del usuario antes de cualquier `terraform
  apply` real (acción de alto impacto, difícil de revertir).
- Verificar el resultado contra AWS/Athena real, no solo contra el código
  de salida de `terraform apply`.

## Qué se hizo

Ver `doc/098-reconciliar-drift-terraform-y-aforos-gold.md` para el detalle
completo: el bloqueo real de permisos IAM encontrado y resuelto (con
aprobación del usuario), la verificación línea a línea del plan completo
antes de aplicar, cómo se excluyó Kafka sin `-exclude` (no soportado en
esta versión de Terraform), el resultado del `apply` (50 added, 64
changed, 50 destroyed, sin errores), y la verificación en vivo de ambas
prioridades (Glue/Lambda actualizados, y `aforos_peatones_bicicletas` con
1971 filas reales en Silver y Gold, antes 0).

## Criterios de aceptación

- `terraform plan` sin acotar, tras el `apply`, muestra únicamente los 5
  recursos de Kafka pendientes (`5 to add, 0 to change, 0 to destroy`).
- `aforos_peatones_bicicletas` devuelve filas reales en Athena (Silver y
  Gold), verificado con una consulta real, no inferido.
- `NEXT_STEPS.md` actualizado marcando ambas prioridades como hechas.
- Documentado en `doc/098-...md`.
