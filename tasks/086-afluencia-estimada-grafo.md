---
id: 86
slug: afluencia-estimada-grafo
title: "Especificación: afluencia estimada vía grafo (sustituto de Google Maps)"
status: in_review
force: false
allow_infra_apply: false
branch: task/086-afluencia-estimada-grafo
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

La tarea 083 (`doc/083-investigacion-google-maps-arquitectura.md`)
demostró que Google Maps no puede dar datos reales de afluencia a coste 0,
y decidió sustituir la capacidad, no eliminarla. Esta tarea es
**solo la especificación** (decisión explícita del 25/8, ver PROGRESS.md)
— la implementación queda para una sesión de seguimiento.

## Qué hace esta tarea

Documenta en `doc/086-afluencia-estimada-grafo.md` un diseño completo en
dos fases:

- **Fase A** (prerrequisito, `grafo/`): añadir `aforos_peatones_bicicletas`
  (contadores oficiales de peatones/bicicletas) como nuevo origen de nodos
  `:EstacionMedida`, siguiendo el patrón ya usado para trafico/calidad_aire/
  ruido, y recargar la instancia real de Neo4j.
- **Fase B** (`asistente/`): nueva tool `afluencia_estimada(lugar,
  radio_m, momento)`, mismo patrón que `trafico_cercano` (tarea 081) —
  resuelve `lugar` en el grafo, cruza `PROXIMO_A` con aforos (señal
  primaria) + BiciMAD/tráfico (secundarias), da un `nivel_estimado`
  simplificado con su limitación documentada.

Incluye el hallazgo de que el grafo **no tiene hoy** nodos de
`aforos_peatones_bicicletas` (verificado contra `grafo/README.md`) — por
eso la Fase A es un prerrequisito real, no opcional.

## Alcance de ESTA tarea (spec, no implementación)

- NO se modifica `grafo/`, `asistente/`, ni `infra/terraform/`.
- NO se ejecuta ninguna carga real contra Neo4j.
- Solo se documenta el diseño con detalle suficiente para implementarlo sin
  releer `doc/083`.

## Criterios de aceptación

- `doc/086-afluencia-estimada-grafo.md` especifica ambas fases con el
  detalle de implementación necesario (funciones a añadir, patrón a
  replicar, verificación esperada).
- Queda explícito que la Fase A es prerrequisito de la Fase B, y por qué.
- Se documenta por qué la tool se llama `afluencia_estimada`, no
  `afluencia_prevista` (el nombre del esqueleto original, tarea 044).

## Para la tarea de seguimiento que implemente esto

- Confirmar el nombre real de la tabla Gold de `aforos_peatones_
  bicicletas` antes de escribir la query de `extract.py`.
- Si la Prioridad 1 de `NEXT_STEPS.md` (drift de Terraform) sigue sin
  reconciliar, verificar primero que el código de este dataset realmente
  desplegado coincide con `main`.
- La escritura real contra Neo4j (Fase A, paso 5) es una acción con efecto
  real fuera del propio repositorio — trátala como las demás tareas de
  infraestructura de este proyecto (interactiva, revisada por un humano,
  no delegada sin más al demonio con `allow_infra_apply`).
