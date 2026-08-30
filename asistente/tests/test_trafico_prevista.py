"""Tests de la tool `trafico_prevista` y su router (`FIL_13`).

Mockea `run_athena_query` y `run_neo4j_query` en `asistente.mcp_agent.tools`
(no depende de credenciales ni de Neo4j). El modelo ONNX es el real vendido
en `asistente/modelos/` (`trafico_h{1,3,6}.onnx`).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente import prevision
from asistente.main import create_app
from asistente.mcp_agent import tools

_GRAFO = [{"estacion_id": "trafico:PM10001", "distancia_m": 90.0}]


def _gold_mock(instante: datetime, *, point_id="PM10001", n=25, base_sl=2.0):
    filas = []
    b = instante.replace(minute=0, second=0, microsecond=0)
    for k in range(n):
        t = b - timedelta(hours=k)
        filas.append({
            "point_id": point_id,
            "date": t.date().isoformat(), "hour": t.hour,
            "avg_service_level": base_sl + (k % 3) * 0.3,
            "lat": 40.42, "lon": -3.70,
        })
    return filas


class PrevisionTargetTests(unittest.TestCase):
    def test_target_trafico_modelo_disponible_y_finito(self):
        self.assertTrue(prevision.modelo_disponible(3, target="trafico"))
        vec, _ = prevision.construir_features(
            2.0, {k: 2.0 for k in range(1, 25)},
            instante=datetime(2026, 8, 20, 8), lat=40.42, lon=-3.70,
        )
        y = prevision.predecir(vec, horizonte=3, target="trafico")
        self.assertIsInstance(y, float)
        self.assertGreaterEqual(y, -1.0)
        self.assertLess(y, 10.0)

    def test_target_desconocido_falla(self):
        with self.assertRaises(ValueError):
            prevision.predecir([0.0] * 19, horizonte=1, target="afluencia")


class ToolTests(unittest.TestCase):
    def test_devuelve_prevision_real_desde_onnx(self):
        ahora = datetime(2026, 8, 20, 10)
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold_mock(ahora)):
            r = tools.trafico_prevista("retiro", 3, 300.0, ahora)
        self.assertEqual(r.punto_id, "PM10001")
        self.assertIsNotNone(r.valor_previsto)
        self.assertIsNotNone(r.valor_actual)
        self.assertIn(r.nivel_previsto, ("fluido", "denso", "congestionado"))
        self.assertGreater(r.data_completeness, 0.5)
        self.assertIn("trafico_h3.onnx", r.modelo)
        self.assertIsNotNone(r.ventana_datos)

    def test_horizonte_invalido(self):
        with self.assertRaises(ValueError):
            tools.trafico_prevista("retiro", 4, 300.0, datetime(2026, 8, 20, 10))

    def test_sin_punto_en_grafo_devuelve_sin_datos(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=[]):
            r = tools.trafico_prevista("no-existe", 6, 300.0, datetime(2026, 8, 20, 10))
        self.assertEqual(r.nivel_previsto, "sin_datos")
        self.assertIsNone(r.valor_previsto)

    def test_grafo_ok_pero_gold_vacio_devuelve_sin_datos(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", return_value=[]):
            r = tools.trafico_prevista("retiro", 6, 300.0, datetime(2026, 8, 20, 10))
        self.assertEqual(r.nivel_previsto, "sin_datos")


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_endpoint_construye_respuesta_trazable(self):
        ahora = datetime(2026, 8, 20, 10)
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold_mock(ahora)):
            resp = self.client.get(
                "/trafico-prevista",
                params={"lugar": "retiro", "horizonte_horas": 3, "momento": ahora.isoformat()},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn(body["veredicto"], ["favorable", "desfavorable", "con_precaucion"])
        self.assertTrue(body["fuentes"])
        self.assertIn("h3.onnx", body["fuentes"][0]["resumen"])

    def test_endpoint_sin_datos(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=[]):
            resp = self.client.get("/trafico-prevista", params={"lugar": "zzz"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["fiabilidad"], "baja")


if __name__ == "__main__":
    unittest.main()
