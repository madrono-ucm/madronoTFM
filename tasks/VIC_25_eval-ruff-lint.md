---
kind: vic-eval
title: "Evaluación técnica ronda 4 — lint estático con ruff"
owner: Claude (QA)
status: done
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

## Hecho (30/8)

1237 hallazgos, 1135 auto-corregibles — dominados por reglas de
modernización de tipado (`UP037`/`UP045`, 1022 de los 1237) en un repo sin
`ruff` configurado nunca. Cada categoría con potencial de bug real
(`DTZ*`, `RUF012`, `B008`, `F401`/`F841`/`RUF059`, `S110`/`BLE001`,
`PLR0124`, `PYI034`, `RUF100`) revisada a mano con lectura del código real:
todas resultaron ser falsos positivos de reglas que no entienden patrones
del dominio (FastAPI `Query`, idioma `x != x` para NaN,
`.replace(tzinfo=...)` tras parseo naive), decisiones ya documentadas
explícitamente en el código (`agenda_eventos` sin timezone, los dos
`noqa: BLE001` con razón), o código de test sin efecto en producción.
Detalle completo en
[`doc/VIC-25-eval-ruff-lint.md`](../doc/VIC-25-eval-ruff-lint.md).

**Cero `FIL_*` nuevos.** El análisis estático corrobora desde un ángulo
distinto lo que las rondas 1-3 (ejecución en vivo) ya habían verificado:
no hay bugs funcionales escondidos.
