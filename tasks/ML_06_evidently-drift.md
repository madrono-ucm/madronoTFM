---
kind: ml
title: "Evidently — informe de deriva (train vs datos recientes)"
owner: Filippos (interactive)
status: done
depends_on: [ML_01]
created_at: "2026-08-28"
---

> **Estado 29/8: ✅ HECHO.** `modelado/evaluation/drift.py`: PSI + KS por
> feature (numpy, siempre) + informe Evidently `DataDriftPreset` HTML/JSON
> (best effort, probado con 0.7.21). Entry point
> `python -m modelado.evaluation.drift --panel … --target …`. Resultado
> real (calidad_aire y trafico): solo 3/19 features con PSI>0.2 y son las
> de día de la semana (artefacto de partición ref 10 d vs actual 3 d); la
> señal es estable. Ilustrativo, no concluyente (§7.4). `evidently>=0.7,<0.8`
> en requirements. 32 tests en verde (+5 `test_ml06.py`). `doc/ML-06`.

## Objetivo

La pieza de "vigilancia de deriva" que nombra la memoria (§5.5: Evidently).

## Alcance

- `modelado/evaluation/drift.py`: dado el panel de `ML_01`, compara la
  distribución de las features (y del target) entre el periodo de train y el
  periodo más reciente (p. ej. últimos 3 días vs el resto) con
  `evidently` (`DataDriftPreset` + `TargetDriftPreset`).
- Genera el informe HTML/JSON a `modelado/evaluation/artifacts/drift/` y un
  resumen (nº de features con deriva significativa) para loguear en MLflow.
- Entry point `python -m modelado.evaluation.drift --target ...`.

## Criterios de aceptación

- Informe real generado sobre el panel de calidad del aire y de tráfico;
  resumen en el `doc/` (con la ventana corta se espera poca deriva — anotar
  el resultado tal cual).
- Test: `drift.py` corre sobre una fixture pequeña sin romper.

## Restricciones

- `evidently` a `modelado/requirements.txt`.
- Con ~2-4 semanas de datos el análisis de deriva es ilustrativo, no
  concluyente — decirlo (§7.4).
