---
kind: ml
title: "modelado/ esqueleto + feature store (Athena -> Parquet, panel horario sin fugas)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-28"
---

## Objetivo

Nuevo directorio `modelado/` (hermano de `ingesta/`/`procesamiento/`/
`grafo/`/`asistente/`), y su primera pieza: un **feature store** que
materializa, de forma reproducible y **sin fuga temporal**, un panel
horario listo para entrenar.

## Estructura de `modelado/`

```
modelado/
├── README.md, requirements.txt, __init__.py
├── features/          # esta tarea
│   ├── athena.py      # helper de consulta (reutiliza el patrón de grafo/extract.py)
│   ├── panel.py       # construye el panel (funciones puras, testables)
│   └── build.py       # entry point: escribe Parquet a s3://.../features/ o local
├── datasets/          # ML_02
├── models/            # ML_03 / ML_05
├── training/          # ML_03+
├── evaluation/        # ML_02 / ML_08
├── registry/          # ML_04
├── export/            # ML_07
└── tests/
```

## Feature store — panel horario

**Entidad** = `(node_id, ts)` donde `node_id` es una estación de sensor y
`ts` una hora. **Regla de oro anti-fuga**: cada feature lleva explícito su
"conocido-a" (`known_at`); en el panel de la hora `t` solo entran valores
con `known_at <= t`.

Grupos de features (una función pura por grupo en `panel.py`):

1. **Lags y rolling** del propio target: `t-1h`, `t-2h`, `t-3h`, `t-24h`;
   media/desv 3 h y 24 h. (De `trafico_por_punto_hora` /
   `calidad_aire_por_estacion_contaminante_hora`.)
2. **Calendario**: hora, día de la semana, fin de semana, festivo (de
   `ingesta/capturas/calendario_laboral_madrid.py` -> hay muestra
   commiteada; si no está en Bronze/Athena, leer el fixture o subirlo).
3. **Meteo**: de `meteorologia_por_estacion_magnitud_hora`, unida a la
   estación de sensor por proximidad (usar el grafo: estación meteo más
   cercana vía `PROXIMO_A`, o join espacial por lat/lon).
4. **Previsión meteo**: de `aemet_prevision_por_municipio_leadtime` (ya
   arreglada, `FIL_01`) — feature exógena real de futuro conocido.
5. **Vecinos de grafo**: agregados (media, min, max) del target y de tráfico
   sobre las estaciones a <=300 m vía `PROXIMO_A` (consulta Neo4j una vez,
   cachear el mapa `estacion -> vecinos`).
6. **Contexto de evento/social** (opcional en esta tarea): recuento de
   `agenda_eventos` en el distrito ese día; `bluesky_menciones` del término.

## Alcance concreto

1. `modelado/README.md` con el diseño de arriba y la realidad de datos
   (~2-4 semanas, ver `NEXT_STEPS.md` §4).
2. `features/athena.py`: consulta Athena (mismo patrón que
   `grafo/extract.py`, workgroup `madrono-tfm-dev-silver-gold`, DB
   `madrono-tfm_dev_gold`). Tests con un `FakeAthenaClient`.
3. `features/panel.py`: funciones puras que, dado un `dict`/`DataFrame` de
   filas Gold + el mapa de vecinos + el calendario, devuelven el panel.
   Tests con fixtures pequeñas construidas a mano (mismo criterio que
   `procesamiento/silver_gold/*/aggregate.py` tests).
4. `features/build.py`: entry point. Genera el panel para un rango de fechas
   y lo escribe como Parquet particionado por `date` (local para
   desarrollo, `s3://madrono-tfm-dev-gold-.../features/<target>/` si se
   decide persistir).
5. Ejecutar `build.py` de verdad contra Athena real para el target de
   **calidad del aire** (NO2/PM2.5/O3 por estación) y **tráfico**
   (`avg_load_ratio`/`avg_service_level` por punto); anotar en el `doc/` el
   nº de filas, rango de fechas y nº de features del panel resultante.

## Criterios de aceptación

- `modelado/` existe con la estructura y un README que fija el diseño.
- `python -m modelado.features.build --target calidad_aire --desde ... --hasta ...`
  produce un Parquet con el panel; verificado contra Athena real.
- Tests de `features/` en verde (sin credenciales: mock de Athena, fixtures
  para `panel.py`).
- `doc/` con las dimensiones reales del panel (filas × features, ventana).

## Restricciones

- Sin fuga temporal: cada feature con `known_at` explícito; documentarlo.
- No entrenar nada en esta tarea — solo el panel.
- Credenciales AWS/Neo4j de SSM, nunca a disco (`infra/OPERACION.md`).
