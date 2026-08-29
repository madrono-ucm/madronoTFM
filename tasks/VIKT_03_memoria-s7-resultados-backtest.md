---
kind: vikt
title: "Memoria §7.1-7.5 — consolidar resultados con ML_08 + evidencia de backtest ML_10"
owner: Pista Memoria — documentación (interactivo)
status: pending
depends_on: [VIKT_01]
created_at: "2026-08-29"
---

## Objetivo

Dejar §7 apoyado en las salidas **consolidadas** de `ML_08` (`run_all.py`)
en vez de en artefactos sueltos, y añadir la evidencia nueva de `ML_06`
(deriva), `ML_07` (paridad) y `ML_10` (backtest incremental).

## Secciones y cambios

- **§7.2 / Tabla 3**: verificar cada celda contra
  `modelado/evaluation/artifacts/estudios/comparacion_todos.csv`
  (`doc/ML-08`). Asegurar que están las filas de **`trafico` con STGNN**
  (no solo calidad del aire) si el backtest de `ML_08 --con-gnn-trafico`
  las produjo; si no, dejar claro en el pie que el STGNN de tráfico usa
  `scope=grafo-lugares` y referencia = persistencia.
- **§7.3 Comparativas / explicabilidad**: citar los ejemplos reales de
  importancia de aristas (`O₃@28079035 ← O₃@28079049`; punto `5412 ← 5768`)
  y el patrón SHAP consolidado (a 1 h manda `value`; a 3–6 h
  `value_roll24h_mean` y, en tráfico, `hora`). Mantener las ablaciones de
  decisión 8 como descartadas explícitas.
- **§7.4 Limitaciones** — añadir:
  - **Backtest incremental** (`ML_10`): la curva *skill vs fecha* de
    `calidad_aire` sube de ~0,63 a ~0,80 a h6 entre el 22 y el 28/8, con un
    bache real el 24–25/8 — evidencia directa de que la ventana es corta y
    el modelo aún no ha convergido (figura de
    `modelado/evaluation/artifacts/backtest/`).
  - **Paridad ONNX** (`ML_07`): el modelo servido reproduce a LightGBM con
    error medio ~0,1 % de la escala del target; hay una cola (p99) por una
    discrepancia conocida del convertidor en el límite de los *splits* —
    documentada, sin impacto práctico.
  - **Deriva** (`ML_06`): con ~2 semanas el análisis es ilustrativo; solo
    las features de día de la semana "derivan" (artefacto de partición), la
    señal es estable.
- **§7.5 Futuras líneas** — añadir:
  - Exportar el **STGNN a ONNX** (hoy bloqueado por `torch.export`: bucle
    temporal + `index_add` con nº de nodos dinámico) → tool
    `afluencia_prevista` servida igual que `calidad_aire_prevista`.
  - Cerrar el *gap* de `ML_01`: *join* real de meteo/previsión AEMET y
    festivos del calendario laboral en el *feature store*.

## Fuente técnica

`doc/ML-08`, `modelado/evaluation/artifacts/estudios/*`, `doc/ML-10` +
`.../backtest/*`, `doc/ML-06` + `.../drift/*`, `doc/ML-07` +
`modelado/export/artifacts/*_paridad.json`, `doc/ML-03`, `doc/ML-05`.

## Criterios de aceptación

- Toda cifra de §7 es trazable a un CSV/JSON de `modelado/evaluation/` o a
  un `doc/ML-*`.
- §7.4 menciona el backtest incremental con números reales y remite a la
  figura.
- §7.5 incluye `STGNN`→ONNX y el *join* de meteo/festivos.
- `.docx` con estilos/numeración intactos.

## Restricciones

- Coordinar el turno del `.docx`. `git pull` antes.
