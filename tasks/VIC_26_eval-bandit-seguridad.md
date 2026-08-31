---
kind: vic-eval
title: "Evaluación técnica ronda 4 — análisis de seguridad estático con bandit"
owner: Claude (QA)
status: done
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

## Hecho (30/8)

42 hallazgos (0 High, 32 Medium, 10 Low). Los 32 Medium revisados línea a
línea:

- `B608` (22, posible SQL injection): **falso positivo en las 22** — 14 en
  `asistente/mcp_agent/tools.py` pasan por `sql_literal()` (escapado
  correcto de comillas) antes de interpolar, 7 en `grafo/extract.py` no
  interpolan ningún valor externo, 1 en `frescura_gold.py` interpola un
  nombre de tabla que siempre viene de un diccionario interno fijo.
- `B314`/`B405` (10+8, XML sin `defusedxml`): **real, pero severidad
  baja** — 4 módulos de `ingesta/capturas/` parsean XML de feeds externos
  con `xml.etree.ElementTree` en vez de `defusedxml`. Riesgo bajo (CPython
  ≥3.7.1 ya bloquea XXE por defecto; queda expuesta la expansión de
  entidades internas, un DoS de memoria, no fuga de datos) pero el fix es
  barato → **`FIL_41`** (renumerado desde `FIL_31` el 31/8: colisión con
  `feat/fil31-trafico-stgnn-tool`, sin mergear a `main`, que en su último
  push añadió su propio `FIL_31_stgnn-trafico-como-tool-mcp.md` -- ver
  nota en `doc/PLAN-EVALUACION-TECNICA-4.md`).

Los 10 Low (`B110` try/except/pass) ya triados en `VIC_25` como decisiones
documentadas en el propio código, sin ticket nuevo.

Detalle completo en
[`doc/VIC-26-eval-bandit-seguridad.md`](../doc/VIC-26-eval-bandit-seguridad.md).
Cruzado contra `VIC_19`/`FIL_28`: sin solapamiento.
