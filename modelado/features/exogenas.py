"""Features exógenas del panel (ML_01): meteo observada y previsión AEMET.

Funciones puras sobre `pandas.DataFrame` -- testables sin credenciales
(`modelado/tests/test_exogenas.py`). El entry point que las alimenta con
Athena real es `modelado/features/build.py`.

Regla de oro (ver `modelado/README.md`): en el panel de la hora `t` solo
entran features con `known_at <= t`.

- **Meteo observada** (`weather_panel`): valor medio de la magnitud en la
  hora `t`, de la estación meteo **más cercana** a cada entidad de sensor
  (join espacial por lat/lon, una asignación por magnitud porque no todas
  las estaciones miden todas las magnitudes). `known_at = t`.
- **Previsión AEMET** (`forecast_panel`): previsión diaria del municipio
  para el día `D`, tomando la **última elaboración de un día de calendario
  estrictamente anterior a `D`** ("la previsión de ayer para hoy"). Así el
  valor es conocido antes de que empiece `D` -> `known_at < D 00:00 <= t`
  para toda hora `t` de `D`. Feature exógena de futuro conocido.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_EARTH_RADIUS_M = 6_371_000.0

# Magnitudes de `meteorologia_por_estacion_magnitud_hora` que se unen al
# panel. Se dejan fuera `wind_direction_deg` (circular, poco útil para un
# GBT sin tratarla), `solar_radiation_wm2` / `uv_radiation_mwm2` (pocas
# estaciones y fuertemente colineales con la hora del día).
MAGNITUDES_METEO: "tuple[str, ...]" = (
    "temperature_c",
    "humidity_pct",
    "wind_speed_ms",
    "precipitation_lm2",
    "pressure_mb",
)


def haversine_m(lat1, lon1, lat2, lon2):
    """Distancia en metros sobre la esfera. Acepta escalares o arrays
    (broadcasting de numpy)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def nearest_station_map(
    entidades: "dict[str, tuple[float, float]]",
    estaciones: "dict[str, tuple[float, float]]",
) -> "dict[str, str]":
    """`{entity_id: station_id de la estación meteo más cercana}`. Entidades
    sin lat/lon válida (NaN) se omiten. `estaciones` vacío -> mapa vacío."""
    est_ids = [s for s, (la, lo) in estaciones.items() if pd.notna(la) and pd.notna(lo)]
    if not est_ids:
        return {}
    est_lat = np.array([estaciones[s][0] for s in est_ids], dtype="float64")
    est_lon = np.array([estaciones[s][1] for s in est_ids], dtype="float64")
    out: "dict[str, str]" = {}
    for eid, (la, lo) in entidades.items():
        if pd.isna(la) or pd.isna(lo):
            continue
        d = haversine_m(float(la), float(lo), est_lat, est_lon)
        out[eid] = est_ids[int(np.argmin(d))]
    return out


def _estaciones_latlon(meteo_long: pd.DataFrame) -> "dict[str, tuple[float, float]]":
    prim = (
        meteo_long.dropna(subset=["lat", "lon"])
        .drop_duplicates("station_id")
        .set_index("station_id")[["lat", "lon"]]
    )
    return {s: (r.lat, r.lon) for s, r in prim.iterrows()}


def weather_panel(
    meteo_long: pd.DataFrame,
    entidades_latlon: "dict[str, tuple[float, float]]",
    *,
    magnitudes: "tuple[str, ...]" = MAGNITUDES_METEO,
) -> pd.DataFrame:
    """Panel meteo por `(entity_id, ts)`: una columna `meteo_<magnitud>` con
    el `avg_value` de esa magnitud, esa hora, en la estación meteo más
    cercana a la entidad que **reporta esa magnitud**.

    `meteo_long`: columnas `station_id`, `ts`, `magnitude`, `avg_value`,
    `lat`, `lon` (formato largo de `meteorologia_por_estacion_magnitud_hora`).
    Devuelve un DataFrame con `entity_id`, `ts` y las columnas `meteo_*`;
    listo para `panel.build_panel(..., weather_df=...)`.
    """
    if meteo_long.empty or not entidades_latlon:
        return pd.DataFrame(columns=["entity_id", "ts"])

    meteo_long = meteo_long.copy()
    meteo_long["ts"] = pd.to_datetime(meteo_long["ts"])
    partes: "list[pd.DataFrame]" = []

    for mag in magnitudes:
        sub = meteo_long[meteo_long["magnitude"] == mag]
        if sub.empty:
            continue
        mapa = nearest_station_map(entidades_latlon, _estaciones_latlon(sub))
        if not mapa:
            continue
        # valor de la magnitud por (station_id, ts) -> lo llevamos a cada
        # entidad vía su estación más cercana.
        por_estacion = (
            sub.groupby(["station_id", "ts"], as_index=False)["avg_value"]
            .mean()
            .rename(columns={"avg_value": f"meteo_{mag}"})
        )
        asignacion = pd.DataFrame(
            {"entity_id": list(mapa), "station_id": list(mapa.values())}
        )
        parte = asignacion.merge(por_estacion, on="station_id", how="inner")
        partes.append(parte[["entity_id", "ts", f"meteo_{mag}"]])

    if not partes:
        return pd.DataFrame(columns=["entity_id", "ts"])

    out = partes[0]
    for parte in partes[1:]:
        out = out.merge(parte, on=["entity_id", "ts"], how="outer")
    return out.sort_values(["entity_id", "ts"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Previsión AEMET (Silver `aemet_prevision`, formato largo por periodo)
# ---------------------------------------------------------------------------

_PREV_AGG = {
    "temperature_max_c": ("prev_temp_max_c", "max"),
    "temperature_min_c": ("prev_temp_min_c", "min"),
    "precipitation_probability_pct": ("prev_precip_prob_pct", "max"),
    "wind_speed_kmh": ("prev_wind_kmh", "mean"),
    "humidity_max_pct": ("prev_humidity_max_pct", "max"),
}


def forecast_panel(prev_long: pd.DataFrame) -> pd.DataFrame:
    """Previsión diaria por día de validez `D`, **sin fuga**: se queda con la
    última `elaborated_at` cuyo día de calendario es estrictamente anterior a
    `D` (la "previsión de ayer para hoy"), y agrega sus periodos del día.

    `prev_long`: columnas `valid_date` (date/str ISO), `elaborated_at`
    (timestamp/str ISO) y las de `_PREV_AGG`. Devuelve `date` (= `valid_date`)
    y las columnas `prev_*` + `prev_forecast_age_h` (horas entre la
    elaboración y las 00:00 de `D`). El primer día del rango queda sin
    previsión (no hay elaboración de un día anterior) -> se descarta.
    """
    if prev_long.empty:
        return pd.DataFrame(columns=["date"])

    df = prev_long.copy()
    df["valid_date"] = pd.to_datetime(df["valid_date"]).dt.normalize()
    df["elaborated_at"] = pd.to_datetime(df["elaborated_at"])
    df["elab_dia"] = df["elaborated_at"].dt.normalize()
    df = df[df["elab_dia"] < df["valid_date"]]
    if df.empty:
        return pd.DataFrame(columns=["date"])

    # última elaboración disponible para cada día de validez
    ult = df.groupby("valid_date")["elaborated_at"].transform("max")
    df = df[df["elaborated_at"] == ult]

    filas = []
    for vd, bucket in df.groupby("valid_date"):
        fila = {"date": vd.date().isoformat()}
        for col, (nombre, how) in _PREV_AGG.items():
            if col in bucket:
                serie = pd.to_numeric(bucket[col], errors="coerce").dropna()
                fila[nombre] = getattr(serie, how)() if not serie.empty else np.nan
        edad = (vd - bucket["elaborated_at"].max()).total_seconds() / 3600.0
        fila["prev_forecast_age_h"] = round(edad, 1)
        filas.append(fila)

    return pd.DataFrame(filas).sort_values("date").reset_index(drop=True)
