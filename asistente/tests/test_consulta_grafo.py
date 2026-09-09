"""Tests de la tool `consulta_grafo` y su router (FIL_67).

Sin AWS, sin Neo4j, sin red: se inyecta un driver falso o se fuerza el
fallo, y se comprueba el contrato de degradación (`FIL_15`).
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from asistente.main import create_app
from asistente.mcp_agent import tools
from asistente.mcp_agent.tools import _consulta_grafo_impl


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def run(self, query, params):
        return _FakeResult(self._rows)


class _FakeDriver:
    def __init__(self, rows):
        self._rows = rows

    def session(self, database=None, **kw):
        return _FakeSession(self._rows)


class ToolTests(unittest.TestCase):
    def test_plantilla_desconocida_degrada(self):
        r = tools.consulta_grafo("no_existe", lugar="Sol")
        self.assertFalse(r.disponible)
        self.assertIn("desconocida", r.motivo)
        self.assertIn("vecindario", r.plantillas_disponibles)

    def test_faltan_parametros_degrada(self):
        r = tools.consulta_grafo("aire_que_mide", lugar="Sol")  # falta `contaminante`
        self.assertFalse(r.disponible)
        self.assertIn("contaminante", r.motivo)

    def test_neo4j_caido_degrada_sin_excepcion(self):
        class _Boom:
            def session(self, *a, **k):
                raise RuntimeError("connection refused")

        r = _consulta_grafo_impl("vecindario", "Sol", 300.0, "", "", "", "", neo4j_driver=_Boom())
        self.assertFalse(r.disponible)
        self.assertIn("Neo4j", r.motivo)

    def test_camino_feliz_con_driver_falso(self):
        rows = [
            {"categoria": "EstacionMedida", "subtipo": "calidad_aire", "id": "calidad_aire:1",
             "nombre": "X", "distancia_m": 120, "contaminantes": ["NO2", "O3"], "magnitudes": None,
             "altitud_m": None, "subarea": None, "anclajes_totales": None, "plazas_totales": None},
        ]
        r = _consulta_grafo_impl("vecindario", "Sol", 300.0, "", "", "", "",
                                 neo4j_driver=_FakeDriver(rows))
        self.assertTrue(r.disponible)
        self.assertEqual(r.n_filas, 1)
        # las claves con valor None se limpian
        self.assertNotIn("magnitudes", r.filas[0])
        self.assertEqual(r.filas[0]["contaminantes"], ["NO2", "O3"])
        self.assertEqual(r.parametros, {"lugar": "Sol"})


class RouterTests(unittest.TestCase):
    def test_router_degradado_devuelve_respuesta_asistente(self):
        client = TestClient(create_app())
        resp = client.get("/consulta-grafo", params={"plantilla": "no_existe", "lugar": "Sol"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["veredicto"], "con_precaucion")
        self.assertIn("Plantillas disponibles", body["explicacion"])


if __name__ == "__main__":
    unittest.main()
