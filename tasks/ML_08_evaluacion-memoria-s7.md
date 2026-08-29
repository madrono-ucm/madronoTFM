---
kind: ml
title: "Cuadernos de evaluación para memoria §7 (baseline vs GBT vs GNN + ablaciones)"
owner: Filippos (interactive)
status: done
depends_on: [ML_03, ML_05]
created_at: "2026-08-28"
---

> **Estado 29/8: ✅ HECHO (estudios 1 y 2).** `modelado/evaluation/estudios/`:
> `estudio_comparacion.py` (puro) + `run_all.py`. Regenera
> `modelado/evaluation/artifacts/estudios/` (`comparacion_<t>.csv`,
> `comparacion_todos.csv`, `explicabilidad_<t>.json`, `skill_<t>.png`) y
> loguea un run MLflow por estudio (`tags.study=`). Tablas reales:
> `calidad_aire` LightGBM +0.29/+0.58/+0.68, STGNN +0.48/+0.55 a h3/h6;
> `trafico` LightGBM +0.37/+0.61/+0.76. SHAP + importancia de aristas
> consolidadas. **Ablaciones 3 y 4 descartadas** (decisión 8, ver `VIC_05`),
> anotado en `doc/ML-08`. 39 tests en verde (+4 `test_ml08.py`).

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
