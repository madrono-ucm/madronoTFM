"""Tests del router HTTP `/afluencia-estimada` (tarea 089).

Mockea `asistente.mcp_agent.tools.run_neo4j_query`/`run_athena_query` con
`side_effect` (lista de retornos, uno por llamada) en vez de `return_value`
fijo -- `afluencia_estimada` hace hasta 4 llamadas a cada uno (una por
señal, en orden: tráfico, ruido, calidad del aire, bicimad para Neo4j;
tráfico, ruido, bicimad, calidad del aire para Athena, ver
`tools._afluencia_estimada_impl`), así que un único valor fijo no basta
para simular varias señales a la vez -- mismo motivo que
`asistente/tests/test_afluencia_estimada.py` no reutiliza los fakes
compartidos de `test_mcp_tools.py`.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente.main import create_app


class AfluenciaEstimadaRouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_lugar_sin_ninguna_senal_cercana_devuelve_baja_fiabilidad_sin_error(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=[]):
            response = self.client.get(
                "/afluencia-estimada",
                params={"lugar": "Zona Que No Existe", "momento": "2026-08-20T14:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["fiabilidad"], "baja")
        self.assertEqual(body["veredicto"], "con_precaucion")

    def test_lugar_con_senal_de_trafico_devuelve_respuesta_trazable(self):
        neo4j_trafico = [
            {"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "trafico:100", "distancia_m": 50.0}
        ]
        gold_trafico = [
            {"point_id": "100", "hour": 10, "avg_intensity_vph": 100.0, "avg_occupancy_ratio": 0.1, "avg_service_level": 1.0}
        ]
        with patch(
            "asistente.mcp_agent.tools.run_neo4j_query",
            side_effect=[neo4j_trafico, [], [], []],  # tráfico, ruido, calidad_aire, bicimad
        ), patch(
            "asistente.mcp_agent.tools.run_athena_query",
            side_effect=[gold_trafico],  # solo tráfico tiene nodos, solo 1 llamada real a Athena
        ):
            response = self.client.get(
                "/afluencia-estimada",
                params={"lugar": "Sol", "momento": "2026-08-20T10:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["veredicto"], "favorable")
        self.assertEqual(body["fiabilidad"], "alta")
        self.assertIn("trafico_por_punto_hora", body["fuentes"][1]["dataset"])


if __name__ == "__main__":
    unittest.main()
