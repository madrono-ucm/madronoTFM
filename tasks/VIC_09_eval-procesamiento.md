---
kind: vic-eval
title: "Evaluación técnica — procesamiento/"
owner: Claude (QA)
status: pending
created_at: "2026-08-29"
---

Parte de [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md).
Solo lectura/test.

## Alcance

- `python3 -m unittest discover -s procesamiento/tests -t .` — suite completa.
- Frescura real en Athena de los 16 datasets "en producción continua"
  (no solo los 6 que rompió la tarea 106 — el resto no se ha vuelto a
  comprobar desde antes del incidente).
- Confirmar que las puertas Great Expectations siguen activas
  (`silver/_quality_reports/` con informes recientes).

## Criterios de aceptación

- Resultado real de la suite.
- Tabla con `max(date)`/`max(hour)` real de Athena para los 16 datasets.
- Cualquier dataset desactualizado o con puerta de calidad rota,
  documentado, con ticket `FIL_*` si implica un cambio de código.
