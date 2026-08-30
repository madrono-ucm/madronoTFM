---
kind: vic-eval
title: "Evaluación técnica ronda 3 — asistente/prevision_grafo.py + calidad_aire_prevista_grafo"
owner: Claude (QA)
status: pending
created_at: "2026-08-30"
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-3.md`](../doc/PLAN-EVALUACION-TECNICA-3.md).
Ningún cambio de código en este ticket.

## Alcance

`FIL_26` es el módulo más nuevo y menos escrutado de esta sesión — se
verificó con una única llamada en vivo, no con la profundidad de `VIC_16`
(que sí revisó `asistente/prevision.py`, `models/`, y leyó los tests
completos de las otras tools). Esta pasada:

- Leer `asistente/prevision_grafo.py` completo: coherencia con
  `asistente/prevision.py` (¿duplica lógica que podría compartirse, o hay
  una razón real para que sean módulos separados?).
- Leer `asistente/tests/test_calidad_aire_prevista_grafo.py` (9 casos según
  el commit) — ¿cubre casos de fallo reales (Athena caído, nodo sin
  vecinos, `.meta.json` corrupto/ausente) igual de bien que
  `test_afluencia_prevista.py`?
- Verificar en vivo con **otro** lugar/estación distinto al que ya se probó
  (Retiro) para confirmar que no es una coincidencia feliz de un único
  caso.
- Revisar `asistente/modelos/stgnn_calidad_aire.meta.json` — ¿el contrato
  documentado en `CONTRATO.md` coincide exactamente con lo que este
  fichero contiene de verdad?

## Criterios de aceptación

- Lectura completa del módulo y sus tests, no solo una llamada de humo.
- Al menos una verificación en vivo con datos/lugar distintos a los ya
  usados en el commit original.
- Cualquier hallazgo → ticket `FIL_*` nuevo.
