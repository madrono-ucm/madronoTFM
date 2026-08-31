"""Tests de la tool `contexto_urbano` y su router (`FIL_53`).

Usa el artefacto real vendorizado `asistente/modelos/grafo_urbano.json.gz`
(reconstrucción del grafo de Neo4j). Sin AWS, sin Neo4j, sin red.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente import contexto_urbano as cu
from asistente.main import create_app
from asistente.mcp_agent import tools


class ToolTests(unittest.TestCase):
    def test_camino_feliz_multisalto(self):
        r = tools.contexto_urbano("Retiro")
        self.assertTrue(r.disponible)
        self.assertEqual(r.distrito, "Retiro")
        self.assertTrue(r.barrio)
        # al menos un tipo de estación a 1 salto
        self.assertTrue(sum(len(v) for v in r.estaciones_1_salto.values()) >= 1)
        for lst in r.estaciones_1_salto.values():
            self.assertTrue(all(e.distancia_m >= 0 for e in lst))
        # transporte alcanzable a <=2 saltos
        self.assertIsNotNone(r.transporte)
        self.assertGreater(r.transporte.alcanzables_2_saltos, 0)

    def test_lugar_desconocido_degrada(self):
        r = tools.contexto_urbano("Chihuahua Norte 42")
        self.assertFalse(r.disponible)
        self.assertIn("Lugar", r.motivo)

    def test_sin_artefacto_degrada(self):
        with patch("asistente.contexto_urbano.disponible", return_value=False):
            r = tools.contexto_urbano("Retiro")
        self.assertFalse(r.disponible)
        self.assertIn("grafo_urbano.json.gz", r.motivo)

    def test_jerarquia_real_no_pip(self):
        # el barrio/distrito salen de UBICADO_EN->PERTENECE_A, no de un
        # point-in-polygon al vuelo
        st = cu._cargar()
        lid = cu._resolver_lugar(st, "Retiro")
        self.assertIsNotNone(lid)
        self.assertIn(lid, st["barrio_de"])


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_endpoint_ok(self):
        resp = self.client.get("/contexto-urbano", params={"lugar": "Retiro"})
        self.assertEqual(resp.status_code, 200)
        b = resp.json()
        self.assertEqual(b["fiabilidad"], "media")
        self.assertIn("distrito Retiro", b["explicacion"])

    def test_endpoint_desconocido(self):
        resp = self.client.get("/contexto-urbano", params={"lugar": "zzzz"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["fiabilidad"], "baja")


class ModuloTests(unittest.TestCase):
    def test_bfs(self):
        adj = {"a": ["b", "c"], "b": ["d"], "c": [], "d": ["e"]}
        self.assertEqual(set(cu._bfs(adj, "a", 2)), {"a", "b", "c", "d"})
        self.assertEqual(set(cu._bfs(adj, "a", 1)), {"a", "b", "c"})

    def test_meta(self):
        m = cu.meta()
        self.assertIn("conteos_nodos", m)


if __name__ == "__main__":
    unittest.main()
