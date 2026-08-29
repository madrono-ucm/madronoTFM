import unittest

import numpy as np
import pandas as pd

from modelado.features import exogenas, panel


class HaversineTests(unittest.TestCase):
    def test_distancia_conocida(self):
        # Puerta del Sol -> Atocha, ~1.4 km en línea recta.
        d = exogenas.haversine_m(40.4168, -3.7038, 40.4076, -3.6926)
        self.assertTrue(1200 < d < 1600, d)

    def test_vectorizado(self):
        d = exogenas.haversine_m(40.0, -3.7, np.array([40.0, 41.0]), np.array([-3.7, -3.7]))
        self.assertAlmostEqual(d[0], 0.0, places=3)
        self.assertGreater(d[1], 100_000)


class NearestStationTests(unittest.TestCase):
    def test_elige_la_mas_cercana(self):
        entidades = {"E1": (40.40, -3.70), "E2": (40.50, -3.60)}
        estaciones = {"S_norte": (40.51, -3.61), "S_centro": (40.41, -3.71)}
        mapa = exogenas.nearest_station_map(entidades, estaciones)
        self.assertEqual(mapa, {"E1": "S_centro", "E2": "S_norte"})

    def test_omite_entidades_sin_coordenadas(self):
        mapa = exogenas.nearest_station_map(
            {"E1": (40.4, -3.7), "E2": (np.nan, np.nan)},
            {"S": (40.4, -3.7)},
        )
        self.assertEqual(list(mapa), ["E1"])

    def test_sin_estaciones(self):
        self.assertEqual(exogenas.nearest_station_map({"E1": (40.4, -3.7)}, {}), {})


def _meteo_row(station_id, ts, magnitude, value, lat, lon):
    return {
        "station_id": station_id, "ts": pd.Timestamp(ts), "magnitude": magnitude,
        "avg_value": value, "lat": lat, "lon": lon,
    }


class WeatherPanelTests(unittest.TestCase):
    def setUp(self):
        # S_centro pega a E1; S_norte pega a E2. Solo S_centro mide presión.
        rows = []
        for h in range(3):
            ts = f"2026-08-15 0{h}:00"
            rows += [
                _meteo_row("S_centro", ts, "temperature_c", 20 + h, 40.41, -3.71),
                _meteo_row("S_norte", ts, "temperature_c", 30 + h, 40.51, -3.61),
                _meteo_row("S_centro", ts, "pressure_mb", 940 + h, 40.41, -3.71),
            ]
        self.meteo = pd.DataFrame(rows)
        self.entidades = {"E1": (40.40, -3.70), "E2": (40.50, -3.60)}

    def test_une_cada_magnitud_a_su_estacion_mas_cercana(self):
        w = exogenas.weather_panel(self.meteo, self.entidades)
        self.assertEqual(set(w.columns), {"entity_id", "ts", "meteo_temperature_c", "meteo_pressure_mb"})
        e1 = w[w.entity_id == "E1"].sort_values("ts")
        e2 = w[w.entity_id == "E2"].sort_values("ts")
        # temperatura: cada entidad a su estación pegada
        self.assertEqual(list(e1["meteo_temperature_c"]), [20, 21, 22])
        self.assertEqual(list(e2["meteo_temperature_c"]), [30, 31, 32])
        # presión: solo la mide S_centro -> las dos entidades caen en ella
        # (más cercana *entre las que reportan esa magnitud*), no se pierde
        self.assertEqual(list(e1["meteo_pressure_mb"]), [940, 941, 942])
        self.assertEqual(list(e2["meteo_pressure_mb"]), [940, 941, 942])

    def test_valor_es_el_de_esa_hora_sin_fuga(self):
        w = exogenas.weather_panel(self.meteo, self.entidades)
        fila = w[(w.entity_id == "E1") & (w.ts == pd.Timestamp("2026-08-15 01:00"))]
        self.assertEqual(fila["meteo_temperature_c"].iloc[0], 21)

    def test_encaja_en_build_panel(self):
        ts = pd.date_range("2026-08-15 00:00", periods=6, freq="h")
        gold = pd.DataFrame({"entity_id": "E1", "ts": ts, "value": range(6)})
        w = exogenas.weather_panel(self.meteo, self.entidades)
        p = panel.build_panel(gold, lags=[1], rolling_windows=[3], horizons=[1], weather_df=w)
        self.assertIn("meteo_temperature_c", p.columns)


def _prev_row(valid_date, elaborated_at, tmax, tmin, pp, wind=10.0, hum=60.0):
    return {
        "valid_date": valid_date, "elaborated_at": elaborated_at,
        "temperature_max_c": tmax, "temperature_min_c": tmin,
        "precipitation_probability_pct": pp, "wind_speed_kmh": wind, "humidity_max_pct": hum,
    }


class ForecastPanelTests(unittest.TestCase):
    def test_toma_la_ultima_elaboracion_de_un_dia_anterior(self):
        prev = pd.DataFrame([
            # día 16: dos elaboraciones el 15, una el 16 (esta última tiene fuga)
            _prev_row("2026-08-16", "2026-08-15T10:00:00", 34, 18, 0),
            _prev_row("2026-08-16", "2026-08-15T21:00:00", 35, 19, 5),
            _prev_row("2026-08-16", "2026-08-16T10:00:00", 33, 17, 0),
        ])
        out = exogenas.forecast_panel(prev)
        self.assertEqual(list(out["date"]), ["2026-08-16"])
        row = out.iloc[0]
        self.assertEqual(row["prev_temp_max_c"], 35)   # de la elaboración del 15T21
        self.assertEqual(row["prev_precip_prob_pct"], 5)
        self.assertEqual(row["prev_forecast_age_h"], 3.0)  # 16T00:00 - 15T21:00

    def test_agrega_periodos_del_dia(self):
        prev = pd.DataFrame([
            _prev_row("2026-08-20", "2026-08-19T09:00:00", 30, 20, 10),
            _prev_row("2026-08-20", "2026-08-19T09:00:00", 32, 22, 40),
        ])
        out = exogenas.forecast_panel(prev).iloc[0]
        self.assertEqual(out["prev_temp_max_c"], 32)   # max de los máximos
        self.assertEqual(out["prev_temp_min_c"], 20)   # min de los mínimos
        self.assertEqual(out["prev_precip_prob_pct"], 40)

    def test_descarta_el_primer_dia_sin_prevision_previa(self):
        prev = pd.DataFrame([_prev_row("2026-08-15", "2026-08-15T10:00:00", 32, 18, 0)])
        self.assertTrue(exogenas.forecast_panel(prev).empty)

    def test_encaja_en_build_panel_como_daily_df(self):
        ts = pd.date_range("2026-08-15 00:00", periods=48, freq="h")
        gold = pd.DataFrame({"entity_id": "E1", "ts": ts, "value": range(48)})
        daily = pd.DataFrame([{
            "date": "2026-08-16", "prev_temp_max_c": 35.0, "prev_temp_min_c": 19.0,
            "prev_precip_prob_pct": 5.0, "prev_wind_kmh": 12.0,
            "prev_humidity_max_pct": 70.0, "prev_forecast_age_h": 3.0,
        }])
        p = panel.build_panel(gold, lags=[1], rolling_windows=[3], horizons=[1], daily_df=daily)
        self.assertIn("prev_temp_max_c", p.columns)
        d15 = p[p["ts"].dt.date.astype(str) == "2026-08-15"]
        d16 = p[p["ts"].dt.date.astype(str) == "2026-08-16"]
        self.assertTrue(d15["prev_temp_max_c"].isna().all())
        self.assertTrue((d16["prev_temp_max_c"] == 35.0).all())
        self.assertNotIn("date", p.columns)


if __name__ == "__main__":
    unittest.main()
