---
id: 85
slug: plan-cierre-tfm
title: "Plan de cierre hacia el 17 de septiembre de 2026"
status: in_review
force: false
allow_infra_apply: false
branch: task/085-plan-cierre-tfm
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-25T00:00:00+00:00'
updated_at: '2026-08-25T00:00:00+00:00'
started_at: '2026-08-25T00:00:00+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Parte de la revisión de arquitectura del 25/8 (tareas 083-084). Se pidió un
plan detallado de los siguientes pasos para poder cerrar el proyecto antes
del 17/9/2026, basado en hallazgos reales, no en una lista genérica de
TODOs.

## Qué se hizo

Se creó `NEXT_STEPS.md`, con 7 prioridades ordenadas por urgencia real:
reconciliar el drift de Terraform (tarea 083), arreglar las 2 tablas Gold
rotas que quedan (`aparcamientos`, `cartelera_cines_estrenos`), implementar
la tarea 086 (afluencia por grafo), las 3 tools restantes del asistente
(más el gap de credenciales Neo4j en SSM), CI mínima, memoria (enlazando
con el reparto ya existente en `PLAN.md` sin duplicarlo), y gaps menores
(EMT con 1 sola parada real, `grafo/README.md` desactualizado, visibilidad
de coste).

## Criterios de aceptación

- `NEXT_STEPS.md` existe en la raíz, con prioridades justificadas (no solo
  listadas) y sin duplicar el reparto por sección ya existente en
  `PLAN.md`.
- Cada prioridad enlaza a su fuente (`doc/NNN`) donde aplica.
