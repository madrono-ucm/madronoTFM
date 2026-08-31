---
kind: fil
title: "prevision_animada.parquet — inferencia de los STGNN sobre días curados"
owner: Filippos (interactive)
status: done
resolved_at: "2026-08-31"
allow_infra_apply: false
created_at: "2026-08-30"
updated_at: "2026-08-30"
depends_on: [FIL_32]
milestone: M2
target: "2026-09-04"
---

## Objetivo

El fichero que alimenta el mapa animado: por nodo y hora, la señal observada
y la prevista por los modelos de grafo, más un índice de salud compuesto.

## GAP CRÍTICO — exportar Gold **YA** (antes de que se pierda)

Las tablas Gold tienen ventana corta y **partition projection deslizante**
(`NEXT_STEPS.md` §"volumetría": tráfico/aire **14 días**, meteo **15 días**,
ruido **5 días**). El pipeline está congelado desde el 30/8 → los datos
frescos son ~**2026-08-16 .. 2026-08-29**. Cuando el calendario avance más
allá de mediados de septiembre, esas particiones de agosto **pueden dejar de
ser consultables por Athena** aunque el Parquet siga en S3 (la projection no
generará esas rutas).

**Primera tarea de este ticket, sin depender de nada más:** exportar a
`viz/data/gold_slices/` (parquet local, versionado o en release) las
ventanas de:
- `gold.trafico_por_punto_hora` para los 1.798 `point_id` del STGNN,
  rango completo consultable (~14 días).
- `gold.calidad_aire_..._contaminante_hora`, ~24 estaciones, mismo rango.
- `gold.meteorologia_..._magnitud_hora` (15 días) — para el ticker (E5).
- `gold.ruido_*` (lo que haya, ~5 días).
Una consulta Athena de lectura. Cero infra. Después, todo offline.

## Alcance

### Días curados — **data-driven, no narrativos**
La ventana consultable (~14 días de agosto 2026) **no garantiza** día de
lluvia, de ozono ni de partido. Curación por estadística sobre el propio
Gold: **2-3 días** con margen ≥1,5 días respecto a los bordes de la ventana,
elegidos por contraste real disponible — p. ej. laborable con pico de hora
punta vs. fin de semana tranquilo, y quizá un día con el mayor pico de NO₂.
Etiquetas descriptivas derivadas de los datos, no asumidas.

### Inferencia (ONNX vendorizados, sin `torch`, sin reentrenar)
- **Ventana deslizante 24×**: por cada hora `h` del día curado, una llamada
  a `prevision_grafo.predecir(series, ancla=h, target=...)` con 12 h de
  lookback. El slice Gold debe cubrir `día − 12 h .. día + 0`.
- **Dos patrones de llamada distintos**:
  - tráfico: `series_por_nodo` keyed `point_id`, `target="trafico"`.
  - calidad del aire: keyed `"<station_id>__<contaminante>"`,
    `target="calidad_aire"` (~54 nodos, ~11-24 estaciones).
- `festivos`: reutilizar `modelado.features.build._DEFAULT_FESTIVOS` /
  `calendario_laboral_madrid_sample.json`.

### Proyección de señales al grafo de tráfico (hero)
- Aire: IDW desde ~24 estaciones a los 1.798 nodos. **Superficie suave, no
  resolución de calle** — se documenta como tal en la memoria.
- **Ruido: NO es horario.** `gold.ruido_*` es **diario** por
  `(station_id, period, measured_date)`, `avg_laeq_db`, con `district` /
  `neighbourhood` ya incluidos, y sólo ~5 días. → El ruido entra como
  **capa de contexto estática por distrito** (LAeq medio diario), **no**
  como capa animada. No hay baseline de perfil horario posible.
- `y_traf_persist` = persistencia real de la ventana (para la capa E2).
- `edge_importance` del `meta.json` es **estático** (top-15, precalculado).
  No hay importancia por hora → la capa E1 dibuja ese conjunto fijo y lo
  anima por el tráfico previsto en sus extremos.

### Índice de salud 0-100 por nodo/hora
Mezcla normalizada: aire (NO₂+O₃, por hora) + proximidad a tráfico previsto
(por hora) + ruido (constante diario del distrito). Pesos documentados.

### Salida
`viz/data/prevision_animada.parquet`:
`node_id, lat, lon, district, ts, y_traf, y_traf_persist, y_no2, y_o3,
noise_district_daily_db, health_index`.
+ `viz/build_prevision_animada.py` + tests (formas, sin NaN en columnas
clave, `y_traf_persist` = persistencia real). Tests bajo `tests/` (el CI
**no** recorre `viz/`).

## Honestidad

`y_traf_persist` / la persistencia de aire se guardan para la capa
"modelo vs baseline" (E2): el STGNN se muestra por la propagación y la
explicabilidad, no porque gane en puntos (§7.4).

## Coste

Una consulta Athena de lectura para los slices. Cero infra nueva.

## Entregable / progreso

Milestone **M2** en `viz/PROGRESO_MAPA.md`.

## Ampliación pendiente — capa social (`FIL_45`)

`prevision_animada.parquet` añade columnas para la capa social/accesibilidad:

- `banda_no2`, `banda_o3`, `banda_health` — la banda de umbral OMS/UE
  (etiqueta), no solo el valor.
- `dosis_no2_pct`, `dosis_o3_pct` — dosis acumulada de una ventana móvil
  (p. ej. 8 h) como % de la guía diaria, por nodo y hora ancla.
- `idw_dist_m` — distancia del nodo a la estación de aire más cercana de las
  11 del STGNN (para el toggle de confianza de la IDW, gap G4).

`viz/build_prevision_animada.py` calcula estas columnas de las que ya tiene;
umbrales OMS/UE como constantes documentadas. Cero AWS.
