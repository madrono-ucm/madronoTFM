---
kind: vic-eval
title: "Evaluación técnica — herramientas/, CI, cola del demonio, disco"
owner: Claude (QA)
status: done
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

## Hecho (29/8)

- `herramientas/costes/desglose_glue.py`: coste total real 124,27 USD,
  23,05 USD desperdiciado en ejecuciones sin resultado útil (creció
  ligeramente desde los 122,35 USD de la última revisión, consistente con
  el volumen de trabajo reciente — no hay ningún salto anómalo).
- `gh run list`: CI en verde en todos los pushes recientes de esta misma
  ronda de evaluación.
- `journalctl -u madrono-agent`: demonio sano, cola vacía, sin errores.
- `df -h /`: 58% usado, 9,4G libres — margen razonable tras el resize de
  la tarea 104 (era 95%/375M libres antes).
- Sin hallazgos que requieran un ticket `FIL_*`.
