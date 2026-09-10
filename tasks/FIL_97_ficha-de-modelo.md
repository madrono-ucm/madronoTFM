---
kind: fil
title: "Ficha de modelo (/modelo): STGNN + índice de salud hechos visibles — skill vs persistencia, horizonte, reentreno nocturno"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_38, FIL_63, FIL_91]
milestone: "M7"
target: "2026-09-13"
---

## Motivación

Showcase, pieza 3 de 5 (plan «hacer brillar todas las capas», 2026-09-10).

El **machine learning** (STGNN de tráfico y aire por hora, índice de
salud, campeones ONNX en MLflow, reentreno nocturno con historial real de
aceptación/rechazo, backtest de skill vs persistencia) es lo más difícil
del proyecto y, igual que los datos, **no tiene UI**. Solo está en MLflow
y en la memoria. Una «model card» es el artefacto estándar de portfolio de
ML para enseñar rigor y honestidad de una vez.

Material real ya existente que la página consume/muestra:

- `modelado/evaluation/artifacts/backtest/backtest_calidad_aire.csv` +
  `skill_vs_fecha_calidad_aire.png`
- `modelado/evaluation/artifacts/estudios/skill_{trafico,calidad_aire}.png`
- `modelado/evaluation/artifacts/backtest_mtd.{csv,json}` (FIL_38)
- MLflow registry: campeones `@champion` (`modelado/registry/`),
  `doc/ML-10-reentrenamiento-nocturno-backtest.md`, el `historial.csv` de
  reentreno (un rechazo y una promoción reales el mismo día, VIKT-06).

## Alcance

### 1. Artefacto de resumen versionado — `modelado/evaluation/artifacts/model_card.json`

Generado por un script reproducible (`modelado/evaluation/model_card.py` o
extensión de `backtest.py`), **no escrito a mano**:

- Por modelo (`trafico_stgnn`, `calidad_aire_stgnn`, grafo, índice de
  salud): tarea, target, **horizonte** (h+1…), ventana de entrenamiento,
  features, versión ONNX `@champion`, fecha de promoción.
- Métricas: MAE / RMSE y **skill = 1 − MAE_modelo / MAE_persistencia** por
  horizonte; la serie skill-vs-fecha (los CSV de arriba).
- Reentreno nocturno: nº de evaluaciones, promociones, rechazos, criterio
  de gate (del `historial.csv` real).
- Limitaciones declaradas (§7.4): 3 días curados, tope de fiabilidad
  «baja», por qué.

### 2. Endpoint `GET /modelo/resumen`

Sirve ese JSON (vendorizado en `asistente/modelos/` como ya se hace con
`grafo_ruta.json`, para no depender de MLflow en la EC2). Cacheado.

### 3. Página `/modelo` (estática, servida como el mapa)

- Tarjeta por modelo: horizonte, ventana, versión, fecha de promoción.
- **Curva de skill vs persistencia** como SVG inline (redibujada desde el
  CSV, no el PNG — que se lea en móvil y en dark mode).
- Tabla MAE/skill por horizonte.
- Bloque «reentreno nocturno»: el historial real de aceptación/rechazo con
  el criterio, en una frase.
- Bloque «qué NO hace»: limitaciones §7.4, tope de fiabilidad.
- Lenguaje llano (un no-especialista entiende «skill 0,3 = 30 % mejor que
  repetir la última hora»), línea visual de la landing.

## Fuera de alcance

- Entrenar / reevaluar modelos aquí (se consumen artefactos ya
  generados).
- Levantar MLflow UI en la EC2 (el JSON vendorizado lo evita).
- El detalle de arquitectura STGNN — la página enlaza a `doc/` y a la
  memoria (S5/S6).

## Verificación

- `model_card.py` regenera `model_card.json` de forma determinista desde
  los artefactos del repo; `git diff` estable entre dos ejecuciones.
- Las cifras de la página cuadran con `backtest_mtd.json` y con los CSV de
  skill (±0 en las que son exactas).
- `GET /modelo/resumen` responde con o sin MLflow (usa el JSON
  vendorizado); degrada con `disponible:false` si falta el fichero.
- La curva SVG coincide en forma con
  `skill_vs_fecha_calidad_aire.png`; legible a ~400 px y en dark mode.
- Test: `TestClient` sobre `/modelo/resumen`; `pytest modelado/` cubre el
  generador; jsdom para el SVG desde un `resumen` de ejemplo.

## Prioridad y secuencia

**Media-alta.** Datos ya existen; el trabajo es el generador + el SVG +
prosa. Después de FIL_38 (backtest MTD, en main). Paralelo a FIL_96.
Estimación ~1–1,5 días. Objetivo **2026-09-13**. Alimenta la parada
«Modelo» de FIL_98.
