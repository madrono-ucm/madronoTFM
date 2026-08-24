"""Tests del router HTTP `/calidad-aire` (tarea 079).

Mockea `asistente.mcp_agent.tools.run_athena_query` (el punto de entrada a
Athena que usa `tools._calidad_aire_impl` cuando no se le inyecta un cliente
explícito) para no depender de credenciales/conexión real, mismo criterio
que `asistente/tests/test_mcp_tools.py`.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente.main import create_app


class CalidadAireRouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_zona_con_datos_devuelve_respuesta_favorable_y_trazable(self):
        filas = [
            {
                "station_id": "28079008",
                "station_name": "Ramón y Cajal",
                "pollutant": "NO2",
                "pollutant_name": "Dióxido de Nitrógeno",
                "unit": "µg/m³",
                "hour": 14,
                "avg_value": 45.5,
                "max_value": 60.0,
                "min_value": 30.0,
                "samples_count": 4,
            }
        ]
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=filas):
            response = self.client.get(
                "/calidad-aire",
                params={"zona": "Ramón y Cajal", "momento": "2026-08-20T14:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["veredicto"], "favorable")
        self.assertEqual(body["fiabilidad"], "alta")
        self.assertEqual(len(body["fuentes"]), 1)
        self.assertIn("calidad_aire_por_estacion_contaminante_hora", body["fuentes"][0]["dataset"])
        self.assertIn("NO2", body["explicacion"])

    def test_zona_sin_estaciones_coincidentes_devuelve_baja_fiabilidad_sin_error(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=[]):
            response = self.client.get(
                "/calidad-aire",
                params={"zona": "Zona Que No Existe", "momento": "2026-08-20T14:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["fiabilidad"], "baja")
        self.assertEqual(body["veredicto"], "con_precaucion")


if __name__ == "__main__":
    unittest.main()
