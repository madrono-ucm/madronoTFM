"""Tests del router HTTP `/disponibilidad-aparcamiento` (tarea 090).

Mockea `asistente.mcp_agent.tools.run_athena_query` (el punto de entrada a
Athena que usa `tools._disponibilidad_aparcamiento_impl` cuando no se le
inyecta un cliente explícito) para no depender de credenciales/conexión
real, mismo criterio que `test_calidad_aire_router.py`.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente.main import create_app


class DisponibilidadAparcamientoRouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_zona_con_muchas_plazas_libres_devuelve_favorable(self):
        filas = [
            {
                "parking_id": "73",
                "name": "Plaza de Oriente",
                "hour": 4,
                "avg_free_spaces": 189.0,
                "avg_occupancy_ratio": 0.89,
                "total_spaces": 212,
                "samples_count": 1,
            }
        ]
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=filas):
            response = self.client.get(
                "/disponibilidad-aparcamiento",
                params={"zona": "Plaza de Oriente", "momento": "2026-08-26T04:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["veredicto"], "favorable")
        self.assertEqual(body["fiabilidad"], "alta")
        self.assertEqual(len(body["fuentes"]), 1)
        self.assertIn("aparcamientos_por_parking_hora", body["fuentes"][0]["dataset"])
        self.assertIn("189", body["explicacion"])

    def test_zona_sin_plazas_libres_devuelve_desfavorable(self):
        filas = [
            {
                "parking_id": "1",
                "name": "Lleno Total",
                "hour": 10,
                "avg_free_spaces": 0.0,
                "avg_occupancy_ratio": 1.0,
                "total_spaces": 100,
                "samples_count": 1,
            }
        ]
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=filas):
            response = self.client.get(
                "/disponibilidad-aparcamiento",
                params={"zona": "Lleno Total", "momento": "2026-08-26T10:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["veredicto"], "desfavorable")
        self.assertEqual(body["fiabilidad"], "alta")

    def test_zona_sin_aparcamientos_coincidentes_devuelve_baja_fiabilidad_sin_error(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=[]):
            response = self.client.get(
                "/disponibilidad-aparcamiento",
                params={"zona": "Zona Que No Existe", "momento": "2026-08-26T10:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["fiabilidad"], "baja")
        self.assertEqual(body["veredicto"], "con_precaucion")


if __name__ == "__main__":
    unittest.main()
