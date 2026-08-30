---
kind: fil
title: "prevision_animada.parquet — inferencia de los dos STGNN sobre días curados"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
depends_on: [FIL_32]
milestone: M2
---

## Objetivo

El fichero que alimenta el mapa animado: por nodo y hora, la señal observada
y la prevista por los modelos de grafo, más un índice de salud compuesto.

## Alcance

- Ventana: **1 día curado** por defecto (24 h), con selector de 3-4 días
  (viernes lluvioso con hora punta / día de ozono / día de partido / día
  tranquilo). Elegidos sobre datos ya presentes en Gold (pipeline congelado).
- Inferencia con los **ONNX vendorizados** (`stgnn_trafico`,
  `stgnn_calidad_aire`) vía `asistente/prevision_grafo.py` — sin reentrenar,
  sin `torch`.
- Ruido: **baseline de perfil horario** — exposición = media histórica por
  `(sonómetro, hora-de-la-semana)` sobre los datos de `ruido_madrid`.
- Interpolación IDW de las señales de sensor (aire ~24 estaciones, ruido,
  tráfico) a los nodos/aristas del grafo (`FIL_34` la consume; el cálculo
  vive aquí).
- Índice de salud 0-100 por nodo = mezcla normalizada de aire (NO₂+O₃),
  ruido dB y proximidad a tráfico. Pesos documentados.
- Salida `viz/data/prevision_animada.parquet`:
  `node_id, lat, lon, district, ts, y_traf, y_traf_persist, y_no2, y_o3,
  y_noise, health_index, edge_importance_out`.
- `viz/build_prevision_animada.py` + tests (formas, sin NaN en columnas
  clave, `y_*_persist` = persistencia real de la ventana).

## Honestidad

`y_traf_persist` / la persistencia de aire se guardan a propósito para la
capa "modelo vs baseline" (E2) del mapa: el STGNN se muestra por la
propagación y la explicabilidad, no porque gane en puntos (§7.4).

## Coste

Una consulta a Athena para exportar la ventana de Gold de los días curados
(o reutilizar un parquet ya en `modelado/_data/`). Cero infra nueva.

## Entregable / progreso

Milestone **M2** en `viz/PROGRESO_MAPA.md`.
