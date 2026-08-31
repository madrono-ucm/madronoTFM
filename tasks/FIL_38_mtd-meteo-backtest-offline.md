---
kind: fil
title: "Backtest offline más largo con MTD + meteo histórica (OPCIONAL)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
updated_at: "2026-08-30"
depends_on: [FIL_33]
milestone: opcional
target: "2026-09-12 (si se elige la vía MTD para la animación)"
---

## Objetivo

Una tabla de resultados `§7` más creíble: skill vs persistencia de los STGNN
sobre **30 meses** (2022-2024) en vez de la ventana corta del proyecto.

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
