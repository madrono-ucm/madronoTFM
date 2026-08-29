"""Tests de la tool `calidad_aire_prevista` y su router (tarea `ML_09`).

Mockea `asistente.mcp_agent.tools.run_athena_query` (no depende de
credenciales). El modelo ONNX es el real vendido en `asistente/modelos/`.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente import prevision
from asistente.main import create_app
from asistente.mcp_agent import tools


def _filas_mock(instante: datetime, *, station="28079008", pollutant="NO2", n=25):
    """`n` horas de lecturas terminando en la hora de `instante`."""
    filas = []
    base = instante.replace(minute=0, second=0, microsecond=0)
    for k in range(n):
        t = base - timedelta(hours=k)
        filas.append({
            "station_id": station, "station_name": "Ramón y Cajal",
            "pollutant": pollutant, "unit": "µg/m³",
            "date": t.date().isoformat(), "hour": t.hour,
            "avg_value": 40.0 + k * 0.5, "lat": 40.45, "lon": -3.68,
        })
    return filas


class ConstruirFeaturesTests(unittest.TestCase):
    def test_orden_y_longitud(self):
        vec, comp = prevision.construir_features(
            50.0, {1: 48.0, 2: 47.0, 3: 46.0, 24: 30.0},
            instante=datetime(2026, 8, 17, 14), lat=40.4, lon=-3.7,
        )
        self.assertEqual(len(vec), len(prevision.FEATURES))
        d = dict(zip(prevision.FEATURES, vec))
        self.assertEqual(d["value"], 50.0)
        self.assertEqual(d["value_lag_1h"], 48.0)
        self.assertEqual(d["value_lag_24h"], 30.0)
        self.assertEqual(d["hora"], 14.0)
        self.assertEqual(d["dia_semana"], 0.0)  # 2026-08-17 es lunes
        self.assertEqual(d["es_finde"], 0.0)
        self.assertAlmostEqual(d["value_roll3h_mean"], (48 + 47 + 46) / 3)
        self.assertEqual(comp, 1.0)  # actual + 4 lags presentes

    def test_completeness_baja_con_huecos(self):
        vec, comp = prevision.construir_features(
            None, {1: 48.0}, instante=datetime(2026, 8, 15, 9), lat=None, lon=None,
        )
        self.assertEqual(comp, 1 / 5)  # solo el lag 1h
        self.assertEqual(dict(zip(prevision.FEATURES, vec))["value"], 0.0)  # NaN -> 0

    def test_finde(self):
        vec = dict(zip(prevision.FEATURES, prevision.construir_features(
            10.0, {}, instante=datetime(2026, 8, 15, 12), lat=0, lon=0)[0]))
        self.assertEqual(vec["es_finde"], 1.0)  # 2026-08-15 es sábado


class PredecirOnnxTests(unittest.TestCase):
    def test_modelo_real_devuelve_finito(self):
        self.assertTrue(prevision.modelo_disponible(6))
        vec, _ = prevision.construir_features(
            45.0, {k: 45.0 for k in range(1, 25)},
            instante=datetime(2026, 8, 17, 8), lat=40.45, lon=-3.68,
        )
        y = prevision.predecir(vec, horizonte=6)
        self.assertIsInstance(y, float)
        self.assertGreater(y, 0.0)
        self.assertLess(y, 500.0)


class ToolTests(unittest.TestCase):
    def test_devuelve_prevision_real_desde_onnx(self):
        ahora = datetime(2026, 8, 17, 10)
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_filas_mock(ahora)):
            r = tools.calidad_aire_prevista("cajal", 6, ahora)
        self.assertEqual(r.contaminante, "NO2")
        self.assertIsNotNone(r.valor_previsto)
        self.assertEqual(r.valor_actual, 40.0)
        self.assertIn(r.nivel_previsto, ("buena", "regular", "mala", "muy mala"))
        self.assertGreater(r.data_completeness, 0.5)
        self.assertIn("calidad_aire_h6.onnx", r.modelo)

    def test_horizonte_invalido(self):
        with self.assertRaises(ValueError):
            tools.calidad_aire_prevista("cajal", 4, datetime(2026, 8, 17, 10))

    def test_sin_estacion_devuelve_sin_datos(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=[]):
            r = tools.calidad_aire_prevista("no-existe", 6, datetime(2026, 8, 17, 10))
        self.assertEqual(r.nivel_previsto, "sin_datos")
        self.assertIsNone(r.valor_previsto)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_endpoint_construye_respuesta_trazable(self):
        ahora = datetime(2026, 8, 17, 10)
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_filas_mock(ahora)):
            resp = self.client.get(
                "/calidad-aire-prevista",
                params={"zona": "cajal", "horizonte_horas": 6, "momento": ahora.isoformat()},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn(body["veredicto"], ["favorable", "desfavorable", "con_precaucion"])
        self.assertEqual(body["fiabilidad"], "media")  # completeness alta, tope MEDIA
        self.assertTrue(body["fuentes"])
        self.assertIn("h6.onnx", body["fuentes"][0]["resumen"])

    def test_endpoint_sin_datos(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=[]):
            resp = self.client.get("/calidad-aire-prevista", params={"zona": "zzz"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["fiabilidad"], "baja")


if __name__ == "__main__":
    unittest.main()
