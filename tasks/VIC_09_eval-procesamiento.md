---
kind: vic-eval
title: "Evaluación técnica — procesamiento/"
owner: Claude (QA)
status: done
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

## Hecho (29/8)

- `python3 -m unittest discover -s procesamiento/tests -t .` → **367 passed**.
- Frescura real en Athena de los 15 tablas Gold (16º "dataset" es en
  realidad 2 tablas del mismo job, `aemet_prevision_avisos`):
  - **Al día** (fecha de hoy o ayer): `afluencia_lugares`, `agenda_eventos`,
    `aparcamientos`, `bicimad`, `bluesky_menciones`, `calidad_aire`,
    `cartelera_cines_estrenos`, `meteorologia`, `trafico`,
    `transporte_publico_emt`, `aemet_prevision` (forecast, fresco),
    `cams_calidad_aire` (forecast, fresco).
  - **Descontinuado, esperado**: `aforos_peatones_bicicletas` (fuente
    municipal congelada 2024-06-30, ya documentado).
  - **🔴 Estancado, NO esperado**: `ruido` (Gold en `2026-08-19`, 11 días,
    pese a Bronze/Silver frescos y el job `SUCCEEDED` a diario) y
    `aemet_avisos` (Gold en `2026-08-22`, 8 días, pese a Bronze con avisos
    reales cada día y el job `SUCCEEDED`). Investigado hasta encontrar una
    hipótesis de causa raíz razonada (mismo patrón de escritura vacía
    silenciosa que `aparcamientos`/`cartelera` en tareas 072/090) — ver
    [`FIL_11`](FIL_11_ruido-aemet-avisos-gold-estancado.md).
- Puertas Great Expectations: los 14 directorios de
  `silver/_quality_reports/` existen y corresponden a los 14 datasets
  originales — estructuralmente en su sitio; no se ha auditado el
  contenido de cada informe uno a uno (fuera del alcance de este ticket,
  dado el tiempo).
