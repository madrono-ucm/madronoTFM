---
kind: vic-eval
title: "Evaluación técnica — herramientas/, CI, cola del demonio, disco"
owner: Claude (QA)
status: pending
created_at: "2026-08-29"
---

Parte de [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md).
Solo lectura/test.

## Alcance

- `herramientas/costes/desglose_glue.py` — correr de verdad, revisar coste
  real y jobs fallando repetidamente.
- `gh run list` — confirmar que la CI sigue en verde en los últimos runs
  (incluido `modelado/`, tarea 103).
- `journalctl -u madrono-agent` — salud reciente del demonio, cola vacía o
  con algo atascado.
- `df -h /` — confirmar el resize de la tarea 104 y que sigue habiendo
  margen razonable.

## Criterios de aceptación

- Resultado real de cada comprobación.
- Cualquier hallazgo (coste anómalo, CI roja, demonio atascado, disco de
  nuevo ajustado) documentado, con ticket `FIL_*` si implica un cambio de
  código.
