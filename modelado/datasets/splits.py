"""Splits temporales (ML_02). Nunca aleatorio: train = todo lo anterior a la
ventana de validación; val = los `val_days` previos al test; test = los
últimos `test_days`. Con la ventana corta del proyecto (~3-4 semanas, ver
`NEXT_STEPS.md` §4) el test son los últimos 3 días por defecto.
"""

from __future__ import annotations

import pandas as pd


def temporal_split(
    panel: pd.DataFrame, *, test_days: int = 3, val_days: int = 2, ts_col: str = "ts"
) -> "tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]":
    """Devuelve `(train, val, test)` particionados por `ts_col`.

    Los cortes se calculan sobre el `ts` **máximo global** del panel: `test`
    = `(t_max - test_days, t_max]`; `val` = `(t_max - test_days - val_days,
    t_max - test_days]`; `train` = todo lo anterior. Sin solape.
    """
    ts = pd.to_datetime(panel[ts_col])
    t_max = ts.max()
    corte_test = t_max - pd.Timedelta(days=test_days)
    corte_val = corte_test - pd.Timedelta(days=val_days)

    train = panel[ts <= corte_val]
    val = panel[(ts > corte_val) & (ts <= corte_test)]
    test = panel[ts > corte_test]
    return train.copy(), val.copy(), test.copy()


def es_split_sin_fuga(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame, *, ts_col: str = "ts") -> bool:
    """`True` si train < val < test en el tiempo, sin solape."""
    def rango(df):
        s = pd.to_datetime(df[ts_col])
        return (s.min(), s.max())

    (_, tr_max), (va_min, va_max), (te_min, _) = rango(train), rango(val), rango(test)
    return bool(tr_max < va_min and va_max < te_min)
