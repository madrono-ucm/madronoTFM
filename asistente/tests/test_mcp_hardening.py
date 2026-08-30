"""Contrato de respuesta y degradación elegante de las tools `*_prevista`
(`FIL_15`).

- Ambas devuelven una subclase de `RespuestaPrevision` con el mismo
  envoltorio (`disponible`/`momento`/`momento_objetivo`/`motivo`/`modelo`/
  `data_completeness`/`ventana_datos`/`generado_en`).
- Ningún fallo de backend (Athena/Neo4j caídos, `.onnx` ausente, Gold sin
  lags) produce excepción: se devuelve el objeto con `disponible=False` y un
  `motivo` legible.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from asistente import prevision
from asistente.mcp_agent import tools
from asistente.models.respuesta import RespuestaPrevision

_AHORA = datetime(2026, 8, 17, 10)


def _aire(instante: datetime, n=25):
    base = instante.replace(minute=0, second=0, microsecond=0)
    return [
        {
            "station_id": "28079008", "station_name": "Ramón y Cajal",
            "pollutant": "NO2", "unit": "µg/m³",
            "date": (base - timedelta(hours=k)).date().isoformat(),
            "hour": (base - timedelta(hours=k)).hour,
            "avg_value": 40.0 + k * 0.5, "lat": 40.45, "lon": -3.68,
        }
        for k in range(n)
    ]


_GRAFO = [{"estacion_id": "trafico:PM10001", "distancia_m": 90.0}]


def _trafico(instante: datetime, n=25):
    base = instante.replace(minute=0, second=0, microsecond=0)
    return [
        {
            "point_id": "PM10001",
            "date": (base - timedelta(hours=k)).date().isoformat(),
            "hour": (base - timedelta(hours=k)).hour,
            "avg_service_level": 2.0 + (k % 3) * 0.3, "lat": 40.42, "lon": -3.70,
        }
        for k in range(n)
    ]


class EnvoltorioComunTests(unittest.TestCase):
    def test_ambas_son_respuestaprevision(self):
        self.assertTrue(issubclass(tools.CalidadAirePrevista, RespuestaPrevision))
        self.assertTrue(issubclass(tools.TraficoPrevista, RespuestaPrevision))

    def test_calidad_aire_ok_rellena_el_envoltorio(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_aire(_AHORA)):
            r = tools.calidad_aire_prevista("cajal", 3, _AHORA)
        self.assertTrue(r.disponible)
        self.assertIsNotNone(r.valor_previsto)
        self.assertEqual(r.momento_objetivo, r.momento + timedelta(hours=3))
        self.assertIsNone(r.motivo)
        self.assertIn("calidad_aire_h3.onnx", r.modelo)
        self.assertRegex(r.ventana_datos, r"\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}")
        self.assertGreater(r.data_completeness, 0.5)
        self.assertIsNotNone(r.generado_en)

    def test_trafico_ok_rellena_el_envoltorio(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", return_value=_trafico(_AHORA)):
            r = tools.trafico_prevista("retiro", 6, 300.0, _AHORA)
        self.assertTrue(r.disponible)
        self.assertEqual(r.momento_objetivo, r.momento + timedelta(hours=6))
        self.assertIsNone(r.motivo)
        self.assertEqual(r.unidad, "avg_service_level")


class DegradacionCalidadAireTests(unittest.TestCase):
    def test_athena_caido_devuelve_objeto_no_excepcion(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", side_effect=RuntimeError("boom Athena")):
            r = tools.calidad_aire_prevista("cajal", 6, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIsNone(r.valor_previsto)
        self.assertEqual(r.nivel_previsto, "sin_datos")
        self.assertIn("Athena", r.motivo)
        self.assertIsNone(r.momento_objetivo)

    def test_sin_estaciones_pone_motivo(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=[]):
            r = tools.calidad_aire_prevista("no-existe", 6, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("no-existe", r.motivo)

    def test_sin_onnx_conserva_lectura_actual_y_explica(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_aire(_AHORA)), \
             patch("asistente.mcp_agent.tools.prevision.modelo_disponible", return_value=False):
            r = tools.calidad_aire_prevista("cajal", 6, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIsNone(r.valor_previsto)
        self.assertEqual(r.valor_actual, 40.0)          # sí hay lectura real
        self.assertIn("calidad_aire_h6.onnx", r.motivo)
        self.assertIsNotNone(r.momento_objetivo)         # hubo anclaje


class DegradacionTraficoTests(unittest.TestCase):
    def test_neo4j_caido_devuelve_objeto_no_excepcion(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", side_effect=RuntimeError("boom Neo4j")):
            r = tools.trafico_prevista("retiro", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("Neo4j", r.motivo)

    def test_grafo_vacio_pone_motivo(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=[]):
            r = tools.trafico_prevista("zzz", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("zzz", r.motivo)

    def test_gold_vacio_pone_motivo(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", return_value=[]):
            r = tools.trafico_prevista("retiro", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("trafico_por_punto_hora", r.motivo)

    def test_athena_caido_tras_grafo_ok(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", side_effect=RuntimeError("boom")):
            r = tools.trafico_prevista("retiro", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("Athena", r.motivo)

    def test_sin_onnx_trafico_conserva_lectura_actual(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", return_value=_trafico(_AHORA)), \
             patch("asistente.mcp_agent.tools.prevision.modelo_disponible", return_value=False):
            r = tools.trafico_prevista("retiro", 6, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIsNone(r.valor_previsto)
        self.assertIsNotNone(r.valor_actual)
        self.assertIn("trafico_h6.onnx", r.motivo)


if __name__ == "__main__":
    unittest.main()
