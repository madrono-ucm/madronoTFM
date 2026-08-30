---
kind: vic-eval
title: "Evaluación técnica ronda 6 — cobertura de tests con pytest-cov"
owner: Claude (QA)
status: pending
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-6.md`](../doc/PLAN-EVALUACION-TECNICA-6.md).
Ningún cambio de código — `pytest-cov` instalado solo en el `.venv` local
para esta auditoría.

## Alcance

- `pytest --cov=ingesta --cov=procesamiento --cov=grafo --cov=asistente
  --cov=modelado --cov=herramientas --cov-report=term-missing` sobre la
  suite completa real.
- No perseguir un número de cobertura alto por sí mismo (no es el
  objetivo de este ticket). Identificar los módulos/funciones de
  **producción** (no scripts de un solo uso, no `__main__` de CLI) con 0%
  o cobertura muy baja, y de esos, leer el código para juzgar si el hueco
  esconde algo con potencial real de bug (lógica de negocio no
  verificada) o si es glue code trivial / manejo de errores defensivo que
  no vale la pena testear.
- Cualquier hueco de cobertura que, al leerlo, tenga pinta real de bug o
  de comportamiento crítico no verificado → un ticket `FIL_*` (proponiendo
  el test que falta, no solo señalando el número).

## Criterios de aceptación

- Salida completa de cobertura revisada, no solo el porcentaje agregado.
- Los huecos de mayor riesgo real (no solo los de menor %) identificados
  y leídos, con veredicto explícito.
- Cero cambios de código aplicados aquí.
