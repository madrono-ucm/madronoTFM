---
kind: fil
title: "Backtest offline más largo con MTD (~29 meses)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
updated_at: "2026-08-31"
resolved_at: "2026-08-31"
depends_on: [FIL_33]
milestone: opcional
target: "2026-09-12"
---

## Estado (2026-08-31) — hecho

`modelado/training/backtest_stgnn_mtd.py` + `doc/FIL-38-...md` +
`modelado/evaluation/artifacts/backtest_mtd.{csv,json}`. Ficheros MTD v4
subconjunto (300 sensores) en `modelado/_data/mtd/` (~18 MB, `.gitignore`).

**Resultado**: el STGNN del proyecto bate a la persistencia en h1/h3/h6
(skill **+0,37 / +0,70 / +0,85**) sobre ~29 meses de MTD — margen que crece
con el horizonte. Confirma el `tier2_trafico` del proyecto sobre un dataset
abierto independiente y una ventana larga. Tabla completa en `doc/FIL-38`.

## Objetivo

Una tabla de resultados `§7` más creíble: skill vs persistencia del STGNN
sobre **~29 meses** (2022-06 .. 2024-10) en vez de la ventana corta del
proyecto.

## Resolución (2026-08-31)

- Se consume el **subconjunto de 300 sensores** de MTD v4
  (`10.17632/697ht4f65b.4`, CC BY 4.0) vía los **tensores ya preparados**
  que publica el dataset (`his_MTD_*.npz`, `idx_*.npy`, `MTD_adj_matrix.npy`),
  no el CSV crudo de 10 GB.
- `backtest_stgnn_mtd.py`: adaptador (`_cargar_mtd` / `_edges_desde_adj` /
  `_ventanas`) + entrena `STGNN(in_dim=3, n_horizontes=3)` (misma
  arquitectura del proyecto) + skill vs persistencia a h1/h3/h6 →
  `modelado/evaluation/artifacts/backtest_mtd.{csv,json}`.
- **Meteo histórica de la Comunidad de Madrid: no hace falta** — MTD ya trae
  wind/temperature/precipitation alineados. Sólo sería necesaria si se
  reconstruyera el panel desde el CSV crudo.
- No toca los ONNX vendorizados ni las tools (**results-only**).

## Puede dejar de ser opcional — decisión pendiente del usuario

El gap de `FIL_33` (Gold consultable ~14 días de agosto 2026, sin variedad
meteo garantizada, ruido sólo 5 días) hace que la animación sobre datos del
proyecto sea **fina**: 2-3 días laborable-vs-finde, sin lluvia/ozono/evento.
Si se quiere una animación **rica** (estaciones, días de lluvia, contraste
real), **MTD es el sustrato de la animación**, no sólo de una tabla — y
entonces este ticket **adelanta** a `FIL_33` y le cambia el origen de datos.
Trade-off: MTD son 554 sensores (no 1.798), sin ruido, y hay que escribir el
adaptador antes. Ver la nota "Fork abierto" en `viz/PROGRESO_MAPA.md`.

## Alcance

- Datasets **descargables, en local** — cero AWS, cero pipeline:
  - MTD v4 (Gómez & Ilarri, `10.17632/697ht4f65b.4`, CC BY 4.0) —
    intensidad de tráfico + atributos de vía + matriz de adyacencia.
  - Meteo horaria histórica de la Comunidad de Madrid (CC BY 4.0) — relleno
    exógeno 2022-2024 para `modelado/features/exogenas.py`.
- `modelado/datasets/mtd_panel.py` — adapta el CSV de MTD a un panel horario
  con el esquema de `ML_01` (resample 15 min→h, renombrado de columnas,
  `target_h{1,3,6} = shift(-h)`, adyacencia → formato `edges_desde_lista`).
- `modelado/datasets/meteo_historico.py` — CSV de la Comunidad →
  `meteo_long` para `weather_panel()`.
- `modelado/training/backtest_stgnn_mtd.py` — reutiliza `entrenar()`,
  holdout de 1 mes, tabla skill/persistencia h1/h3/h6.
- Tests de los adaptadores (sin credenciales).

## No hace

- No toca los ONNX vendorizados ni las tools (el modelo MTD es un artefacto
  de resultados, no se sirve — decisión "results-only").
- No reintroduce gasto AWS.

## Entregable / progreso

Fila "opcional" en `viz/PROGRESO_MAPA.md`. `DATA_SOURCES.md` (de `FIL_36`)
ya cubre la atribución.
