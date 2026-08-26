"""Tests del router HTTP `/eventos-cercanos` (tarea 095).

Mockea `asistente.mcp_agent.tools.run_neo4j_query` y `...run_athena_query`
(los puntos de entrada que usa `tools._eventos_cercanos_impl` cuando no se
le inyecta un driver/cliente explícito) para no depender de credenciales/
conexión real, mismo criterio que `test_trafico_cercano_router.py`.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente.main import create_app


class EventosCercanosRouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_lugar_con_evento_cercano_devuelve_favorable_y_trazable(self):
        lugar_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Retiro", "lat": 40.415, "lon": -3.684}]
        evento_rows = [
            {
                "event_id": "ev1",
                "title": "Concierto en el Retiro",
                "venue_name": "Auditorio Retiro",
                "lat": 40.415,
                "lon": -3.684,
                "start_datetime": "2026-08-25T20:00:00+02:00",
            }
        ]
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=lugar_rows), patch(
            "asistente.mcp_agent.tools.run_athena_query", return_value=evento_rows
        ):
            response = self.client.get(
                "/eventos-cercanos",
                params={"lugar": "Retiro", "momento": "2026-08-20T14:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["veredicto"], "favorable")
        self.assertEqual(body["fiabilidad"], "alta")
        self.assertEqual(len(body["fuentes"]), 1)
        self.assertIn("agenda_eventos", body["fuentes"][0]["dataset"])
        self.assertIn("Concierto en el Retiro", body["explicacion"])

    def test_lugar_sin_eventos_cercanos_devuelve_baja_fiabilidad_sin_error(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=[]), patch(
            "asistente.mcp_agent.tools.run_athena_query", return_value=[]
        ):
            response = self.client.get(
                "/eventos-cercanos",
                params={"lugar": "Zona Que No Existe", "momento": "2026-08-20T14:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["fiabilidad"], "baja")
        self.assertEqual(body["veredicto"], "con_precaucion")


if __name__ == "__main__":
    unittest.main()
