"""Tests del router HTTP `/opciones-movilidad` (tarea 096).

Mockea `asistente.mcp_agent.tools.run_neo4j_query` y `...run_athena_query`
(los puntos de entrada que usa `tools._opciones_movilidad_impl` cuando no
se le inyecta un driver/cliente explícito) para no depender de
credenciales/conexión real, mismo criterio que `test_eventos_cercanos_router.py`.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente.main import create_app


class OpcionesMovilidadRouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_origen_y_destino_con_datos_devuelve_las_tres_opciones(self):
        lugar_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Retiro"}]
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=lugar_rows), patch(
            "asistente.mcp_agent.tools.run_athena_query", return_value=[]
        ):
            response = self.client.get(
                "/opciones-movilidad",
                params={"origen": "Retiro", "destino": "Sol", "momento": "2026-08-20T14:00:00+02:00"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["fiabilidad"], "media")
        self.assertEqual(len(body["fuentes"]), 3)
        modos = {f["dataset"] for f in body["fuentes"]}
        self.assertTrue(any("trafico" in m for m in modos))
        self.assertTrue(any("bicimad" in m for m in modos))
        self.assertTrue(any("transporte_publico_emt" in m for m in modos))

    def test_ni_origen_ni_destino_coinciden_devuelve_baja_fiabilidad_sin_error(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=[]), patch(
            "asistente.mcp_agent.tools.run_athena_query", return_value=[]
        ):
            response = self.client.get(
                "/opciones-movilidad",
                params={"origen": "Zona A Inexistente", "destino": "Zona B Inexistente"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["fiabilidad"], "baja")
        self.assertEqual(body["veredicto"], "con_precaucion")


if __name__ == "__main__":
    unittest.main()
