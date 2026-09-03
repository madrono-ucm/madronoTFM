"""Tests del router HTTP `/trafico-cercano` (tarea 081).

Mockea `asistente.mcp_agent.tools.run_neo4j_query` y
`asistente.mcp_agent.tools.run_athena_query` (los puntos de entrada que usa
`tools._trafico_cercano_impl` cuando no se le inyecta un cliente/driver
explícito) para no depender de credenciales/conexión real -- mismo criterio
que `asistente/tests/test_calidad_aire_router.py`.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente.main import create_app


class TraficoCercanoRouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_lugar_con_estacion_cercana_devuelve_respuesta_trazable(self):
        neo4j_rows = [
            {"lugar_id": "poi:1", "lugar_nombre": "Parque del Retiro", "estacion_id": "trafico:4260", "distancia_m": 120.5}
        ]
        gold_rows = [
            {
                "point_id": "4260",
                "hour": 14,
                "avg_intensity_vph": 300.0,
                "avg_occupancy_ratio": 0.2,
                "avg_load_ratio": 0.15,
                "avg_intensity_ratio": 0.3,
                "avg_service_level": 1.0,
            }
        ]
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=neo4j_rows), patch(
            "asistente.mcp_agent.tools.run_athena_query", return_value=gold_rows
        ):
            response = self.client.get(
                "/trafico-cercano",
                params={"lugar": "Retiro", "momento": "2026-08-20T14:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["veredicto"], "favorable")
        self.assertEqual(body["fiabilidad"], "alta")
        self.assertEqual(len(body["fuentes"]), 2)
        self.assertIn("trafico_por_punto_hora", body["fuentes"][1]["dataset"])

    def test_lugar_sin_estaciones_cercanas_devuelve_baja_fiabilidad_sin_error(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=[]):
            response = self.client.get(
                "/trafico-cercano",
                params={"lugar": "Zona Que No Existe", "momento": "2026-08-20T14:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["fiabilidad"], "baja")
        self.assertEqual(body["veredicto"], "con_precaucion")

    def test_lugar_con_estaciones_pero_sin_dato_de_gold_no_dice_que_no_encontro_el_lugar(self):
        """Regresión: el grafo sí resuelve `lugar` y encuentra estaciones,
        pero Gold no tiene fila para la fecha/hora consultada (p.ej. una
        fecha sin datos de tráfico) -- la explicación no debe decir "no se
        ha encontrado ningún lugar" (verificado como bug real en producción:
        Puerta del Sol resolvía 6 estaciones reales pero el mensaje afirmaba
        que no se había encontrado ningún lugar)."""
        neo4j_rows = [
            {"lugar_id": "poi:1", "lugar_nombre": "Puerta del Sol", "estacion_id": "trafico:10608", "distancia_m": 207.6}
        ]
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=neo4j_rows), patch(
            "asistente.mcp_agent.tools.run_athena_query", return_value=[]
        ):
            response = self.client.get(
                "/trafico-cercano",
                params={"lugar": "Puerta del Sol", "momento": "2026-09-04T09:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["fiabilidad"], "baja")
        self.assertEqual(body["veredicto"], "con_precaucion")
        self.assertIn("Se han encontrado 1 estación", body["explicacion"])
        self.assertNotIn("no se ha encontrado ningún lugar", body["explicacion"])


if __name__ == "__main__":
    unittest.main()
