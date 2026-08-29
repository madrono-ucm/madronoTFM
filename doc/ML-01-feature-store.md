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

## `--scope` — ¿traer toda la red o solo los nodos que importan?

Pregunta planteada por Filippos. Verificado con Cypher: de **4 702**
`:EstacionMedida` de tráfico, **1 813** tienen `PROXIMO_A` a un `:Lugar`;
de **24** estaciones de calidad del aire, solo **11**. `build.py --scope`:

- `all` (por defecto): toda la red. Para el target de **congestión de red**
  (predecir en cualquier sensor de Madrid) y la ablación de fuente única de
  §7.3.
- `grafo-lugares`: solo los sensores con `PROXIMO_A` a un `:Lugar`. Para la
  **fusión** / la afluencia / lo que alimenta al asistente.

`ML_02` elige el scope por experimento. No se limita por rendimiento (ver
abajo), solo por criterio de modelado.

## Rendimiento — lectura de Athena

`run_athena_query` (de `grafo.extract`, reutilizado) pagina el resultado con
`get_query_results` a 1000 filas/llamada. Para el panel de tráfico (~1,5 M
filas) son ~1500 round-trips a la API → **>15 min**. `query_df` de
`modelado/features/athena.py` lee en su lugar el **CSV que Athena deja en
S3** (`ResultConfiguration.OutputLocation`) de una vez con
`pandas.read_csv`: el mismo panel en **~22 s**. `_reindex_horario_completo`
también se vectorizó (`MultiIndex.from_product`, sin bucle Python por
entidad).

## Ejecución real contra Athena (28/8)

`AWS_PROFILE=madrono python -m modelado.features.build ...`:

| Target / scope | Filas | Entidades | Ventana | s |
|---|---|---|---|---|
| `calidad_aire` / `all` | 39 942 | 123 (estación × contaminante) | 2026-08-15 01:00 → 08-28 15:00 | ~17 |
| `calidad_aire` / `grafo-lugares` | 17 542 | 54 (11 estaciones cerca de un `:Lugar`) | ídem | ~5 |
| `trafico` / `all` | **1 511 995** | 4 702 puntos | ídem | ~22 |
| `trafico` / `grafo-lugares` | 580 325 | 1 813 puntos | ídem | ~20 |
| `afluencia` (Gold de FIL_06) | 0 | 0 | — | — |

19 features (4 lags + 4 estadísticos rolling + 11 de calendario). Targets
`h1/h3/h6`. **(Actualizado el 29/8 a 30 features — ver abajo.)**

**`afluencia` da 0 filas**: la tabla Gold de FIL_06 solo tiene ~1 h de datos
(el job horario acaba de empezar) → `build_panel` descarta todo (sin lags
posibles con una sola hora). Se rellenará solo según el job acumule horas;
no es un bug.

8 tests de `panel.py` en verde. `pandas 3.0.5` / `pyarrow 25.0.1` (`--only-binary
:all:` — no hay wheels de fuente para Python 3.14).

## Cierre de huecos: meteo + previsión AEMET + festivos (29/8)

Los tres enriquecedores que quedaban pendientes tras la primera pasada están
ahora implementados y verificados contra Athena real.
`modelado/features/exogenas.py` (funciones puras, 22 tests nuevos en
`test_exogenas.py` + `test_build.py`):

### Meteo observada — `weather_panel`

Join espacial de `meteorologia_por_estacion_magnitud_hora` (formato largo):
para cada entidad de sensor, la estación meteo **más cercana que reporta esa
magnitud** (haversine sobre lat/lon; una asignación por magnitud porque no
todas las estaciones miden todo — en la ventana: 24 estaciones dan
`temperature_c`, 22 `humidity_pct`, 9 `wind_speed_ms`/`precipitation_lm2`,
7 `pressure_mb`). 5 columnas `meteo_*`. `known_at = ts` (valor observado esa
hora) → sin fuga. Simplificación asumida: no hay corte de distancia máxima
(el área metropolitana de Madrid es pequeña y estas magnitudes varían poco
espacialmente); una magnitud rara empareja con la estación más cercana
aunque esté a varios km.

### Previsión AEMET — `forecast_panel`

De la tabla **Silver** `aemet_prevision` (la Gold
`aemet_prevision_por_municipio_leadtime` es un `overwrite` sin histórico —
4 filas, inservible para un panel temporal). Para el día de validez `D` se
toma la **última `elaborated_at` de un día de calendario estrictamente
anterior a `D`** ("la previsión de ayer para hoy"), y se agregan sus
periodos: `prev_temp_max_c` (máx), `prev_temp_min_c` (mín),
`prev_precip_prob_pct` (máx), `prev_wind_kmh` (media),
`prev_humidity_max_pct` (máx), `prev_forecast_age_h` (antigüedad de la
previsión a las 00:00 de `D`). 6 columnas. `known_at < D 00:00 ≤ ts` para
toda hora de `D` → feature exógena de futuro conocido, sin fuga. El primer
día de la ventana se queda sin previsión (no hay elaboración anterior) y sus
filas van con NaN (se descartan casi todas en el warm-up). Solo hay 1
municipio (Madrid) → misma previsión diaria para todas las entidades; es una
señal diaria legítima, no un problema.

### Festivos

`--festivos` por defecto a la muestra commiteada
`ingesta/capturas/samples/calendario_laboral_madrid_sample.json` (el año
2026 completo; no hay pipeline Silver/Gold para este dataset). `_cargar_festivos`
**arreglado**: antes metía *todas* las fechas del fichero en el set de
festivos (con la muestra del año entero, marcaba todos los días como
festivo); ahora filtra `is_holiday` / `day_type == "festivo"`. En la ventana
2026-08-15..28 el único festivo real es el 15/8 (Asunción) — y ahora se
marca solo ese día.

### Ejecución real (29/8)

`AWS_PROFILE=madrono python -m modelado.features.build --target ... --desde
2026-08-15 --hasta 2026-08-28`:

| Target / scope | Filas | Entidades | Features | meteo no-nulo | previsión no-nulo |
|---|---|---|---|---|---|
| `calidad_aire` / `all` | 39 942 | 123 | **30** | 83–90 % | 92,9 % (NaN = 1er día) |
| `trafico` / `all` | 1 511 995 | 4 702 | **30** | ~85 % | 92,9 % |

30 features = 19 previas + 5 `meteo_*` + 6 `prev_*`. Flags `--sin-meteo` /
`--sin-prevision` para la ablación de fuente única de §7.3. El join de meteo
y previsión es independiente de `--scope`.

## Pendiente / siguiente (`ML_02`)

- Splits temporales + líneas base (persistencia, climatología, seasonal-naive)
  + módulo de métricas.
- `afluencia`: la Gold de `FIL_06` sigue acumulando horas; rehacer el panel
  cuando tenga ventana suficiente para lags.
- Mejora futura (no bloqueante): retener histórico de `elaborated_at` en la
  Gold de previsión permitiría una feature de previsión a resolución
  sub-diaria; hoy se resuelve leyendo Silver.
