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

---

## Revisión FIL (2026-08-30) — sin hallazgos, sin ticket nuevo

- **`asistente/prevision_grafo.py` leído completo.** No duplica lógica de
  `asistente/prevision.py`: `_features_17` **reutiliza** `prevision.construir_features`
  y recorta `lat`/`lon` (`_IDX_17`). El caché de sesión ONNX + meta es propio del
  contrato de grafo (más pesado); un helper compartido no ahorraría nada real.
  Separación deliberada (vector único LightGBM vs ventana de grafo STGNN).
- **`CONTRATO.md` § STGNN ↔ `stgnn_calidad_aire.meta.json`**: coinciden exactamente
  — `feature_cols` (17, = FEATURES sin lat/lon, verificado por `_cargar` con un
  `assert`), `x_mu/x_sd` (17), `y_mu/y_sd` (3), `longitud_ventana` 12,
  `node_index`/`node_coords` (54), `edge_index` [2,602] + `edge_weight` (602),
  `importancia_aristas` (top-15), `origen_grafo` `coords-knn8`.
- **Tests**: +2 casos de fallo (`test_meta_corrupto_degrada_sin_excepcion`,
  `test_stgnn_revienta_en_inferencia_degrada`) → 11 en total, a la par con
  `test_afluencia_prevista.py`.
- **Verificación en vivo con 5 estaciones distintas a Retiro** (Plaza de España·PM10,
  Méndez Álvaro·PM10, Villaverde·O3, Ramón y Cajal·NO2, + IDs crudos): todas OK,
  peor-caso por contaminante sensato, `vecinos_influyentes` poblado sólo cuando el
  nodo aparece en el top-15 (no fabrica), `data_completeness` refleja huecos reales
  de Gold, `disponible=False` limpio para estaciones fuera del grafo de 11.
