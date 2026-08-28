import datetime as dt
import unittest

import pandas as pd

from modelado.features import panel


def _serie(entity_id: str, valores: "list[float]", inicio="2026-08-15 00:00") -> pd.DataFrame:
    ts = pd.date_range(inicio, periods=len(valores), freq="h")
    return pd.DataFrame({"entity_id": entity_id, "ts": ts, "value": valores})


class CalendarTests(unittest.TestCase):
    def test_features_calendario(self):
        # 2026-08-15 es sábado -> 17 es lunes.
        df = _serie("A", [1.0] * 3, inicio="2026-08-17 22:00")
        out = panel.add_calendar_features(df, holidays={dt.date(2026, 8, 17)})
        self.assertEqual(list(out["hora"]), [22, 23, 0])
        self.assertEqual(list(out["dia_semana"])[:2], [0, 0])  # lunes
        self.assertEqual(list(out["es_finde"]), [0, 0, 0])
        self.assertEqual(list(out["es_festivo"])[:2], [1, 1])
        self.assertEqual(list(out["es_festivo"])[2:], [0])  # 18/8 no
        self.assertAlmostEqual(out["hora_sin"].iloc[2], 0.0, places=9)  # hora 0

    def test_sabado_domingo_es_finde(self):
        df = _serie("A", [1.0] * 3, inicio="2026-08-15 22:00")  # sábado -> domingo
        out = panel.add_calendar_features(df)
        self.assertEqual(list(out["es_finde"]), [1, 1, 1])


class LagRollingTests(unittest.TestCase):
    def test_lag_es_el_valor_anterior_por_entidad(self):
        df = pd.concat([_serie("A", [10, 20, 30, 40]), _serie("B", [1, 2, 3, 4])], ignore_index=True)
        out = panel.add_lag_rolling_features(df, lags=[1, 2], rolling_windows=[2])
        a = out[out.entity_id == "A"].reset_index(drop=True)
        self.assertTrue(pd.isna(a["value_lag_1h"].iloc[0]))
        self.assertEqual(list(a["value_lag_1h"].iloc[1:]), [10, 20, 30])
        self.assertEqual(list(a["value_lag_2h"].iloc[2:]), [10, 20])
        # rolling de ventana 2 sobre el pasado (shift(1)): fila idx 2 -> mean(10,20)=15
        self.assertAlmostEqual(a["value_roll2h_mean"].iloc[2], 15.0)
        # nunca incluye la hora actual: fila idx 1 -> solo 10
        self.assertAlmostEqual(a["value_roll2h_mean"].iloc[1], 10.0)

    def test_reindexa_huecos_horarios(self):
        ts = [pd.Timestamp("2026-08-15 00:00"), pd.Timestamp("2026-08-15 03:00")]  # hueco de 2h
        df = pd.DataFrame({"entity_id": "A", "ts": ts, "value": [5.0, 9.0]})
        out = panel._reindex_horario_completo(df)
        self.assertEqual(len(out), 4)  # 00,01,02,03
        self.assertTrue(out["value"].isna().iloc[1:3].all())


class TargetTests(unittest.TestCase):
    def test_target_es_el_valor_futuro(self):
        df = _serie("A", [10, 20, 30, 40])
        out = panel.add_targets(df, horizons=[1, 2])
        self.assertEqual(list(out["target_h1"].iloc[:3]), [20, 30, 40])
        self.assertTrue(pd.isna(out["target_h1"].iloc[-1]))
        self.assertEqual(list(out["target_h2"].iloc[:2]), [30, 40])


class NeighbourTests(unittest.TestCase):
    def test_media_de_vecinos_misma_hora(self):
        df = pd.concat(
            [_serie("A", [10, 10]), _serie("B", [20, 40]), _serie("C", [30, 60])],
            ignore_index=True,
        )
        out = panel.add_neighbour_features(df, {"A": ["B", "C"]}, prefix="vec")
        a = out[out.entity_id == "A"].reset_index(drop=True)
        self.assertEqual(list(a["vec_mean"]), [25.0, 50.0])  # (20+30)/2 ; (40+60)/2
        self.assertEqual(list(a["vec_min"]), [20.0, 40.0])
        # B/C sin vecinos definidos -> NaN
        self.assertTrue(out[out.entity_id == "B"]["vec_mean"].isna().all())


class BuildPanelTests(unittest.TestCase):
    def test_sin_fuga_temporal(self):
        df = _serie("A", list(range(0, 30)))  # 30 horas, valores 0..29
        p = panel.build_panel(df, lags=[1, 2, 3], rolling_windows=[3], horizons=[1, 3])
        # el warm-up (fila 0, sin ningún lag) se descarta
        self.assertNotIn(0, p["value"].tolist()[:1] if len(p) else [])
        # para cada fila, target_h1 == value de la hora siguiente
        m = p.dropna(subset=["target_h1"])
        self.assertTrue(((m["target_h1"] - m["value"]) == 1).all())
        # ninguna columna de feature filtra el futuro: value_lag_kh <= value
        for k in (1, 2, 3):
            sub = p.dropna(subset=[f"value_lag_{k}h"])
            self.assertTrue((sub[f"value_lag_{k}h"] < sub["value"]).all())

    def test_columnas_esperadas(self):
        df = _serie("A", [1.0] * 40)
        p = panel.build_panel(df, lags=[1, 24], rolling_windows=[3], horizons=[1, 6])
        for c in ["entity_id", "ts", "hora", "es_festivo", "value_lag_1h",
                  "value_lag_24h", "value_roll3h_mean", "target_h1", "target_h6"]:
            self.assertIn(c, p.columns)


if __name__ == "__main__":
    unittest.main()
