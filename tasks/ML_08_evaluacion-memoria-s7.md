---
kind: ml
title: "Cuadernos de evaluación para memoria §7 (baseline vs GBT vs GNN + ablaciones)"
owner: Filippos (interactive)
status: pending
depends_on: [ML_03, ML_05]
created_at: "2026-08-28"
---

## Objetivo

Las salidas reales que necesita la Pista Memoria para §7.1-§7.3
(`VIC_05`). Un cuaderno/entry point por estudio, resultados commiteados.

## Estudios

1. **Comparación principal** (siempre): baseline (persistencia/climatología)
   vs LightGBM vs GNN, por horizonte (1/3/6 h) y por tipo de nodo. Métricas
   de `ML_02`. Tabla + figura.
2. **Explicabilidad** (siempre): SHAP (GBT, `ML_03`) + importancia de
   aristas (GNN, `ML_05`) — qué señales / qué vecinos del grafo pesan.
3. **Ablación de fusión multi-señal vs fuente única** (pendiente decisión 8,
   `NEXT_STEPS.md` §5.7): reentrenar el mejor modelo con subconjuntos de
   features (solo el propio target; +meteo; +grafo; todo) y medir la mejora.
4. **Ablación "solo sustrato europeo común"** (pendiente decisión 8):
   entrenar con todas las fuentes de Madrid pero **evaluar** usando solo
   CAMS + AEMET + calendario — estima la pérdida al portar a otra ciudad.

## Alcance

- `modelado/evaluation/estudios/` con un módulo por estudio + un
  `run_all.py`.
- Resultados a `modelado/evaluation/artifacts/` (CSV + PNG) y al `doc/`.
- Cada estudio loguea un run de MLflow con `tags.study=<nombre>`.

## Criterios de aceptación

- Estudios 1 y 2 completos con datos reales.
- Estudios 3 y 4: hechos si la decisión 8 los mantiene; si se recortan,
  anotarlo en el `doc/` y en `VIC_05`.
- Todo reproducible (`run_all.py` regenera los artefactos).

## Restricciones

- Sin fuga: las ablaciones reusan el split temporal de `ML_02`.
