---
kind: vic-eval
title: "Evaluación técnica ronda 4 — análisis de seguridad estático con bandit"
owner: Claude (QA)
status: pending
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-4.md`](../doc/PLAN-EVALUACION-TECNICA-4.md).
Ningún cambio de código en este ticket.

## Alcance

- `bandit -r` sobre `ingesta/ procesamiento/ grafo/ asistente/ modelado/ herramientas/`
  (excluir `tests/`/`*/tests/` — los patrones que `bandit` marca como
  riesgo en producción son a menudo intencionados en un test).
- Cada hallazgo de severidad media/alta: leer el código real antes de
  decidir si es un falso positivo (p. ej. `subprocess`/`pickle`/`eval`
  usados con entrada no controlada por el usuario no son lo mismo que con
  entrada externa) o un problema real.
- Cruzar contra lo que `VIC_19` ya encontró (la credencial de Bluesky,
  `FIL_28`) para no duplicar.

## Criterios de aceptación

- Salida completa revisada línea a línea para severidad media/alta (baja
  se puede resumir).
- Cada hallazgo con veredicto explícito: falso positivo (con la razón) o
  real (→ ticket `FIL_*`).
