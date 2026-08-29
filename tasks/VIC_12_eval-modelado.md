---
kind: vic-eval
title: "Evaluación técnica — modelado/ (ML_01-ML_10)"
owner: Claude (QA)
status: pending
created_at: "2026-08-29"
---

Parte de [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md).
Solo lectura/test.

## Alcance

- `python3 -m unittest discover -s modelado/tests -t .` — suite completa
  (instalar `torch` si hace falta para `ML_05`, disco ya no es un
  problema tras el resize de la tarea 104).
- Confirmar que los artefactos reales (`modelado/evaluation/artifacts/`)
  siguen siendo consistentes entre sí (Tabla 3 de la memoria vs
  `comparacion_todos.csv`, etc.).
- Estado de los gaps ya conocidos: `ML_01` sin join real de meteo/AEMET ni
  festivos reales, STGNN sin exportar a ONNX.

## Criterios de aceptación

- Resultado real de la suite.
- Confirmación de que los artefactos citados en la memoria siguen
  existiendo y coincidiendo.
- Cualquier discrepancia documentada, con ticket `FIL_*` si implica un
  cambio de código.
