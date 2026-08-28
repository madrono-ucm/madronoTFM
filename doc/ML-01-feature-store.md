# ML-01 — `modelado/` esqueleto + feature store

## Qué se creó

`modelado/` (hermano de `ingesta/`/`procesamiento/`/`grafo/`/`asistente/`),
con la estructura de subpaquetes de `tasks/ML_00_README.md` y su primera
pieza: el **feature store**.

- `modelado/features/athena.py` — reutiliza `grafo.extract.run_athena_query`
  + `query_df()` → `pandas.DataFrame`. A diferencia de `asistente/athena.py`
  (que copia el helper para desplegarse como servicio), `modelado/` corre
  como batch en el mismo repo/entorno, así que acoplarse a `grafo.extract`
  es correcto y evita una tercera copia.
- `modelado/features/panel.py` — **funciones puras** (pandas), testables sin
  credenciales:
  - `_reindex_horario_completo`: cada entidad a un rango horario continuo
    (huecos = NaN) → `shift(k)` = "hace k horas de reloj", no "k
    observaciones".
  - `add_lag_rolling_features`: lags `t-1/2/3/24h` + media/desv rolling 3/24 h
    sobre `shift(1)` (nunca la hora actual).
  - `add_calendar_features`: hora, día, finde, festivo + codificación cíclica.
  - `add_neighbour_features`: media/min/max del valor de las entidades
    vecinas (`PROXIMO_A`) **en la misma hora**.
  - `add_targets`: `target_h{h}` = `shift(-h)` (futuro).
  - `build_panel`: orquesta; descarta el warm-up.
- `modelado/features/build.py` — entry point Athena(Gold) → panel → Parquet.
  Targets: `calidad_aire`, `trafico`, `afluencia` (Gold de FIL_06). Vecinos
  (Neo4j) y festivos, opcionales por flag.

## Anti-fuga temporal

Verificado con test explícito (`test_panel.py::BuildPanelTests`): para toda
fila en `t`, `value_lag_kh < value` (pasado) y `target_h1 == value(t+1)`
(futuro). Regla documentada en `modelado/README.md`.

## Ejecución real contra Athena (28/8)

`AWS_PROFILE=madrono python -m modelado.features.build ...`:

| Target | Filas | Entidades | Ventana | Features |
|---|---|---|---|---|
| `calidad_aire` | **39 940** | 123 (estación × contaminante) | 2026-08-15 01:00 → 08-28 15:00 | 19 (4 lags + 4 rolling + calendario) |
| `trafico` | _(en curso, ver `doc/` al cerrar)_ | ~4 300 puntos | ~14 días | 19 |

8 tests de `panel.py` en verde. `pandas 3.0.5` / `pyarrow 25.0.1` instalados
(`--only-binary :all:` — no hay wheels de fuente para Python 3.14).

## Pendiente / siguiente (`ML_02`)

- Splits temporales + líneas base (persistencia, climatología, seasonal-naive)
  + módulo de métricas.
- Enriquecer el panel con meteo (join espacial) y previsión AEMET —
  esqueleto listo en `build.py`, falta el join real.
- Festivos: `--festivos` acepta el JSON de `calendario_laboral_madrid`;
  confirmar el formato del fichero real y subirlo a Bronze o commitear la
  muestra.
