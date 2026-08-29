---
kind: vic-eval
title: "Evaluación técnica — asistente/ (las 7 tools, en vivo)"
owner: Claude (QA)
status: pending
created_at: "2026-08-29"
---

Parte de [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md).
Solo lectura/test.

## Alcance

- `python3 -m unittest discover -s asistente/tests -t .` — suite completa.
- Verificación en vivo de las 7 tools contra Athena/Neo4j/ONNX reales
  (`calidad_aire`, `trafico_cercano`, `afluencia_estimada`,
  `disponibilidad_aparcamiento`, `eventos_cercanos`, `opciones_movilidad`,
  `calidad_aire_prevista`) — esta última ya se verificó en una sesión
  anterior de esta misma conversación, las otras 6 no se han vuelto a
  probar en vivo desde sus tareas originales.

## Criterios de aceptación

- Resultado real de la suite.
- Cada una de las 7 tools invocada al menos una vez contra datos reales,
  con el resultado real anotado.
- Cualquier tool rota o degradada, documentada, con ticket `FIL_*` si
  implica un cambio de código.
