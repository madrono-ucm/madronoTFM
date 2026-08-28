"""Construcción del panel horario de features (ML_01), **sin fuga temporal**.

Funciones puras sobre `pandas.DataFrame` -- testables sin credenciales
(`modelado/tests/test_panel.py`). El entry point que las orquesta contra
Athena real es `modelado/features/build.py`.

Contrato de entrada (`gold_df`): una fila por `(entity_id, ts)`, columnas:

- `entity_id` (str): estación de sensor / punto de tráfico / `:Lugar`.
- `ts` (`pd.Timestamp`, horario, sin tz o en Europe/Madrid consistente).
- `value` (float): la señal cruda del target en esa hora.
- opcional `lat`, `lon`.

Regla de oro (ver `modelado/README.md`): en el panel de la hora `t` solo
entran features con `known_at <= t`. Lags/rolling -> `shift(+k)`; target a
horizonte `h` -> `shift(-h)`; calendario -> siempre; meteo observada en `t`
-> conocida en `t`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_HORAS_DIA = 24
_DIAS_SEMANA = 7


def add_calendar_features(
    df: pd.DataFrame, *, ts_col: str = "ts", holidays: "set | None" = None
) -> pd.DataFrame:
    """Añade hora, día de la semana, fin de semana, festivo y sus
    codificaciones cíclicas. Todo derivado de `ts` -> `known_at = ts`."""
    out = df.copy()
    ts = pd.to_datetime(out[ts_col])
    out["hora"] = ts.dt.hour
    out["dia_semana"] = ts.dt.dayofweek  # lunes=0
    out["es_finde"] = (out["dia_semana"] >= 5).astype("int8")
    holidays = holidays or set()
    out["es_festivo"] = ts.dt.date.astype("O").isin(holidays).astype("int8")
    out["hora_sin"] = np.sin(2 * np.pi * out["hora"] / _HORAS_DIA)
    out["hora_cos"] = np.cos(2 * np.pi * out["hora"] / _HORAS_DIA)
    out["dsem_sin"] = np.sin(2 * np.pi * out["dia_semana"] / _DIAS_SEMANA)
    out["dsem_cos"] = np.cos(2 * np.pi * out["dia_semana"] / _DIAS_SEMANA)
    return out


def _reindex_horario_completo(df: pd.DataFrame, *, ts_col: str = "ts") -> pd.DataFrame:
    """Reindexa cada `entity_id` a un rango horario continuo entre su primer
    y último `ts`, rellenando huecos con NaN -- así `shift(k)` significa "hace
    k horas de reloj", no "k observaciones", aunque falten capturas."""
    partes = []
    for eid, g in df.groupby("entity_id", sort=False):
        g = g.sort_values(ts_col).drop_duplicates(ts_col)
        idx = pd.date_range(g[ts_col].min(), g[ts_col].max(), freq="h")
        g = g.set_index(ts_col).reindex(idx)
        g["entity_id"] = eid
        g.index.name = ts_col
        partes.append(g.reset_index())
    return pd.concat(partes, ignore_index=True) if partes else df.copy()


def add_lag_rolling_features(
    df: pd.DataFrame,
    *,
    value_col: str = "value",
    lags: "list[int]" = (1, 2, 3, 24),
    rolling_windows: "list[int]" = (3, 24),
) -> pd.DataFrame:
    """Lags y estadísticos rolling del propio target, estrictamente en el
    pasado. Asume `df` ya reindexado a horario completo por entidad."""
    out = df.sort_values(["entity_id", "ts"]).copy()
    g = out.groupby("entity_id", sort=False)[value_col]
    for k in lags:
        out[f"{value_col}_lag_{k}h"] = g.shift(k)
    pasado = g.shift(1)  # rolling sobre esto -> nunca incluye la hora actual
    for w in rolling_windows:
        roll = pasado.groupby(out["entity_id"], sort=False).rolling(w, min_periods=1)
        out[f"{value_col}_roll{w}h_mean"] = roll.mean().reset_index(level=0, drop=True)
        out[f"{value_col}_roll{w}h_std"] = roll.std().reset_index(level=0, drop=True)
    return out


def add_neighbour_features(
    df: pd.DataFrame,
    neighbours: "dict[str, list[str]]",
    *,
    value_col: str = "value",
    prefix: str = "vecinos",
) -> pd.DataFrame:
    """Media/min/max del `value_col` de las entidades vecinas (mapa
    `entity_id -> [ids de vecinos]`, p. ej. estaciones a <=300 m vía
    `PROXIMO_A`) **en la misma hora**. `known_at = ts` (valor observado del
    vecino), sin fuga."""
    out = df.copy()
    ancho = out.pivot_table(index="ts", columns="entity_id", values=value_col, aggfunc="mean")
    medias, mins, maxs = {}, {}, {}
    for eid in out["entity_id"].unique():
        cols = [v for v in neighbours.get(eid, []) if v in ancho.columns]
        if cols:
            sub = ancho[cols]
            medias[eid] = sub.mean(axis=1)
            mins[eid] = sub.min(axis=1)
            maxs[eid] = sub.max(axis=1)
    def _map(serie_por_eid, sufijo):
        col = pd.Series(index=out.index, dtype="float64")
        for eid, serie in serie_por_eid.items():
            m = out["entity_id"] == eid
            col.loc[m] = out.loc[m, "ts"].map(serie)
        out[f"{prefix}_{sufijo}"] = col.values
    _map(medias, "mean")
    _map(mins, "min")
    _map(maxs, "max")
    return out


def add_targets(
    df: pd.DataFrame, *, value_col: str = "value", horizons: "list[int]" = (1, 3, 6)
) -> pd.DataFrame:
    """Etiquetas: valor del target `h` horas en el futuro (`shift(-h)`)."""
    out = df.sort_values(["entity_id", "ts"]).copy()
    g = out.groupby("entity_id", sort=False)[value_col]
    for h in horizons:
        out[f"target_h{h}"] = g.shift(-h)
    return out


def build_panel(
    gold_df: pd.DataFrame,
    *,
    value_col: str = "value",
    lags: "list[int]" = (1, 2, 3, 24),
    rolling_windows: "list[int]" = (3, 24),
    horizons: "list[int]" = (1, 3, 6),
    holidays: "set | None" = None,
    neighbours: "dict[str, list[str]] | None" = None,
    weather_df: "pd.DataFrame | None" = None,
) -> pd.DataFrame:
    """Panel horario listo para entrenar: una fila por `(entity_id, ts)` con
    features (todas `known_at <= ts`) y una columna `target_h{h}` por
    horizonte (puede ser NaN al final de la serie -- el entrenamiento filtra
    por horizonte). Descarta el warm-up (filas sin ningún lag).
    """
    df = _reindex_horario_completo(gold_df)
    df = add_lag_rolling_features(df, value_col=value_col, lags=lags, rolling_windows=rolling_windows)
    if neighbours:
        df = add_neighbour_features(df, neighbours, value_col=value_col)
    if weather_df is not None and not weather_df.empty:
        df = df.merge(weather_df, on=["entity_id", "ts"], how="left")
    df = add_calendar_features(df, holidays=holidays)
    df = add_targets(df, value_col=value_col, horizons=horizons)

    lag_cols = [f"{value_col}_lag_{k}h" for k in lags]
    df = df[df[lag_cols].notna().any(axis=1)].reset_index(drop=True)
    return df
