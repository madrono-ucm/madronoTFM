---
kind: vic-eval
title: "Evaluación técnica ronda 5 — comprobación de tipos con mypy"
owner: Claude (QA)
status: pending
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-5.md`](../doc/PLAN-EVALUACION-TECNICA-5.md).
Ningún cambio de código — `mypy` instalado solo en el `.venv` local para
esta auditoría.

## Alcance

- `mypy` sobre `ingesta/ procesamiento/ grafo/ asistente/ modelado/ herramientas/`
  (sin `tests/` salvo que un hallazgo en producción lo requiera para
  contexto) — sin `pyproject.toml`/`mypy.ini` en el repo, correr primero
  sin flags estrictos (`--ignore-missing-imports` para no ahogarse en
  stubs de terceros ausentes) y solo escalar a `--strict` si el primer
  pase queda manejable.
- Triar: separar errores de tipo con potencial de bug real (llamar una
  función con un tipo incompatible, acceder a un atributo que no existe
  en ese tipo, un `return` inconsistente con la anotación) de ruido
  causado por la falta de stubs de terceros (`boto3`, `pandas`, etc. sin
  tipado completo) — este ruido es esperable en un proyecto sin `mypy`
  configurado desde el origen y no amerita ticket.
- Cualquier hallazgo con pinta de bug real → un ticket `FIL_*` con el
  fichero/línea exactos y por qué importa.

## Criterios de aceptación

- Salida completa de `mypy` revisada, no solo el conteo total.
- Hallazgos triados por severidad real (bug de tipo genuino vs. ruido de
  stubs ausentes), no un volcado sin filtrar.
- Cero cambios de código aplicados aquí.
