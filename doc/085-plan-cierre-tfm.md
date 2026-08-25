# 085 — Plan de cierre hacia el 17 de septiembre de 2026

## Qué se implementó

`NEXT_STEPS.md` en la raíz: roadmap priorizado por urgencia real (no por
orden de aparición en el repositorio), con 7 prioridades concretas,
grounded en hallazgos verificados de esta sesión y del historial de
`doc/`, no en TODOs genéricos.

## Por qué este orden de prioridades

- **Prioridad 1 (drift de Terraform) antes que cualquier feature nueva**:
  es el hallazgo más grave de la tarea 083 — mientras no se reconcilie, no
  se puede confiar en que el código fusionado esté realmente desplegado,
  lo que afecta la fiabilidad de cualquier verificación futura "contra
  datos reales".
- **Prioridad 2 (Gold roto de `aparcamientos`) antes que la tarea 086**:
  la especificación de afluencia por grafo (tarea 086) quiere usar la
  ocupación de aparcamientos como señal secundaria; arreglarlo primero
  evita tener que revisitar esa tool más tarde.
- **CI como prioridad 5, no 1**: importante y barata, pero no bloquea
  ningún otro trabajo — se prioriza por debajo de arreglos que si bloquean.
- La sección de memoria no duplica el reparto ya existente en `PLAN.md`
  (tabla de secciones) — solo añade los dos hallazgos nuevos de esta
  sesión que le son relevantes (Google Maps como refuerzo de la discusión
  de zona gris, no como blocker resuelto sin más; el drift de Terraform y
  las tablas Gold rotas como candidatas a §7.4 Limitaciones si no se
  resuelven antes del cierre).

## Relevante para tareas futuras

- Este documento debe irse actualizando (tachando prioridades cerradas)
  según avance el trabajo — no es una foto fija como `PLATFORM_SCHEMA.md`.
- Si una prioridad nueva aparece que no encaja en esta lista, añadirla
  aquí en vez de solo mencionarla en `PLAN.md`, para mantener un único
  sitio con el estado técnico priorizado.
