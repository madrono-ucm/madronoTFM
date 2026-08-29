---
kind: vic-eval
title: "Evaluación técnica — ingesta/"
owner: Claude (QA)
status: pending
created_at: "2026-08-29"
---

Parte de [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md).
Solo lectura/test — ningún cambio de código aquí; cualquier hallazgo que
implique cambiar código se empaqueta como ticket `FIL_*` aparte.

## Alcance

- `python3 -m unittest discover -s ingesta/tests -t .` — suite completa.
- Verificar que los 24 módulos de captura listados en `ingesta/README.md`
  existen y tienen su `lambda_handler` real (no solo código de muestra).
- Spot-check en vivo de 2-3 fuentes reales (no solo confiar en la última
  ejecución de Lambda — invocar `capture_all()`/lo que corresponda contra
  la fuente real, o verificar el Bronze más reciente en S3).

## Criterios de aceptación

- Resultado real de la suite (nº de tests, verde/rojo).
- Al menos 2-3 fuentes verificadas en vivo, con resultado real.
- Cualquier discrepancia código↔realidad documentada, con ticket `FIL_*`
  si implica un cambio de código.
