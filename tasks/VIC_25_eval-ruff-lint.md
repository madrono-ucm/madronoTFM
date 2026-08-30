---
kind: vic-eval
title: "Evaluación técnica ronda 4 — lint estático con ruff"
owner: Claude (QA)
status: pending
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-4.md`](../doc/PLAN-EVALUACION-TECNICA-4.md).
Ningún cambio de código en este ticket — `ruff` instalado solo en el
`.venv` local para esta auditoría.

## Alcance

- `ruff check` sobre `ingesta/ procesamiento/ grafo/ asistente/ modelado/ herramientas/ tests/`.
- Triar los resultados: separar bugs reales probables (F-series: imports
  sin usar que oculten un error, variables sin usar que deberían usarse,
  comparaciones con `is`/`==` sospechosas, `except` demasiado amplios) de
  ruido de estilo puro (líneas largas, etc. — no vale la pena un ticket
  por eso en un repo sin `ruff` configurado desde el principio).
- Cualquier hallazgo con pinta de bug real (no solo estilo) → un ticket
  `FIL_*` con el fichero/línea exactos y por qué importa.

## Criterios de aceptación

- Salida completa de `ruff check` revisada, no solo el conteo total.
- Hallazgos triados por severidad real, no un volcado sin filtrar.
- Cero cambios de código aplicados aquí.
