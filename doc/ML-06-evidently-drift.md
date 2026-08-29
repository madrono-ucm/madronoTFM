# ML-06 — Evidently: informe de deriva (train vs datos recientes)

## Qué se creó

- **`modelado/evaluation/drift.py`** — dos capas:
  1. **Estadística pura** (numpy, sin dependencias frágiles): **PSI** +
     **Kolmogorov-Smirnov** por feature entre el periodo de referencia (lo
     antiguo) y el actual (últimos `--dias-recientes`, 3 por defecto).
     `deriva_psi` = PSI > 0.2 (umbral interpretable); `deriva_ks` = p < 0.05
     (muy sensible al tamaño de muestra). Es el resultado que siempre se
     produce y el que se resume para MLflow.
  2. **Informe Evidently** (`DataDriftPreset`, HTML + JSON) — *best effort*:
     si `evidently` responde se guarda; si su API cambió o no está, se anota
     y se sigue. Probado con `evidently 0.7.21` (`rep.run(...)` → `Snapshot`
     con `save_html`). El frame que va a Evidently se submuestrea a 150 k
     filas (la estadística pura usa todo).
- Entry point: `python -m modelado.evaluation.drift --panel … --target …`.
  Salida en `modelado/evaluation/artifacts/drift/<target>/`:
  `resumen.json`, `features.csv`, `evidently_drift.{html,json}`.
- **`modelado/tests/test_ml06.py`** — 5 tests: PSI = 0 con misma
  distribución, PSI detecta desplazamiento de media, KS p bajo con deriva,
  `tabla_drift` marca la columna derivada y no la estable, `analizar` sobre
  una fixture pequeña.

`evidently 0.7.21` (wheel binario, Python 3.14). `evidently>=0.7,<0.8` en
`modelado/requirements.txt`. `python -m pytest modelado/ -q` → **32
passed**.

## Resultado real (paneles de `ML_01`)

Referencia `2026-08-15 … 08-25` (~10 d) vs actual `08-25 … 08-28` (~3 d).

| target | filas ref / actual | PSI > 0.2 | KS p < 0.05 |
|---|---|---|---|
| `calidad_aire` | 31 332 / 8 610 | **3 / 19** | 16 / 19 |
| `trafico` | 452 619 / 127 706 | **3 / 19** | 16 / 19 |

En **ambos targets** las únicas 3 features con PSI > 0.2 son las de **día de
la semana** (`dia_semana`, `dsem_sin`, `dsem_cos`): una porción de 3 días no
contiene la misma mezcla de días laborables/fin de semana que una de 10
días — es un **artefacto de la partición**, no deriva de concepto. Las
features de señal (`value`, lags, rolling) tienen PSI 0.04–0.11, **por
debajo del umbral**: la distribución del target y sus derivados es estable
en la ventana disponible. `lat`/`lon`/`es_festivo` → PSI ≈ 0 (control).

El KS marca 16/19 en los dos casos porque con decenas de miles de filas
detecta como "significativa" cualquier diferencia mínima (PSI 0.004 →
p < 0.05); por eso el criterio de referencia es el **PSI**, no el p-valor.

**Con ~2 semanas de datos este análisis es ilustrativo, no concluyente**
(§7.4). Su valor es dejar el mecanismo montado: cuando el histórico crezca,
`ML_10` (reentrenamiento nocturno) puede llamar a `analizar()` y comparar
`n_deriva_psi` contra un umbral para decidir si toca reentrenar.

## Criterios de aceptación

- [x] Informe real generado sobre calidad del aire y tráfico; resumen aquí
  (poca deriva de señal, anotado tal cual).
- [x] Test: `drift.py` corre sobre una fixture pequeña sin romper.
- [x] `evidently` en `modelado/requirements.txt`.
- [x] Naturaleza ilustrativa declarada (§7.4).

## Pendiente / lo retoman otros tickets

- `ML_10` — enganchar `analizar()` al reentrenamiento nocturno (umbral de
  `n_deriva_psi` → gatillo de reentrenamiento) y registrar el resumen como
  métrica/artefacto de MLflow.
- Deriva de **predicción** (no solo de datos): comparar la distribución de
  `ŷ` reciente vs la de train — encaja mejor en `ML_08`/`ML_10` con el
  modelo servido.
