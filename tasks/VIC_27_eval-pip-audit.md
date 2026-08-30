---
kind: vic-eval
title: "Evaluación técnica ronda 4 — CVEs de dependencias con pip-audit"
owner: Claude (QA)
status: pending
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-4.md`](../doc/PLAN-EVALUACION-TECNICA-4.md).
Ningún cambio de código en este ticket.

## Alcance

- `pip-audit` contra el entorno real (`.venv` de esta EC2, que instala
  `ingesta/requirements.txt` + `modelado/requirements.txt` +
  `asistente/requirements.txt` combinados) — base de datos real de OSV/PyPI.
- Por cada CVE real encontrado: ¿el paquete afectado se usa en una ruta de
  código expuesta a entrada no confiable (una API externa, un input de
  usuario) o solo en un contexto interno/de desarrollo? Prioriza el
  primero.
- No proponer un `pip install -U` genérico sin comprobar que la versión
  nueva no rompe algo (`FIL_23` ya mostró que un cambio de versión de
  `torch` sin cuidado tiene efectos secundarios reales).

## Criterios de aceptación

- Salida completa de `pip-audit` revisada.
- CVEs reales explicados con impacto real en este proyecto, no solo
  copiados de la base de datos.
- Cualquier CVE que amerite acción → ticket `FIL_*` con la versión exacta
  a la que actualizar y qué verificar después.
