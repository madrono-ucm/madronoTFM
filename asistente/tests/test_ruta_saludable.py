"""Tests de la tool `ruta_saludable` y su router (`FIL_37`).

Usa el artefacto real vendorizado en `asistente/modelos/grafo_ruta.json`
(sin Neo4j, sin Athena, sin red).
"""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente import ruta_saludable as rs
from asistente.main import create_app
from asistente.mcp_agent import tools


class ToolTests(unittest.TestCase):
    def test_camino_feliz(self):
        r = tools.ruta_saludable("Atocha", "Moncloa", "ciclista", datetime(2026, 8, 26, 8))
        self.assertTrue(r.disponible)
        self.assertEqual(r.dia, "2026-08-26")
        self.assertEqual(r.hora, 8)
        self.assertGreaterEqual(r.ruta_sana.n_nodos, 2)
        self.assertEqual(r.ruta_sana.nodos[0], r.ruta_rapida.nodos[0])
        self.assertEqual(r.ruta_sana.nodos[-1], r.ruta_rapida.nodos[-1])
        # la rápida nunca es más larga que la sana
        self.assertLessEqual(r.ruta_rapida.dist_m, r.ruta_sana.dist_m + 1.0)
        self.assertIn(r.mejor_hora_salida, range(24))
        self.assertIn("traf", r.reduccion_exposicion_pct)

    def test_perfil_invalido_degrada(self):
        r = tools.ruta_saludable("Sol", "Retiro", "supersonico")
        self.assertFalse(r.disponible)
        self.assertIn("perfil", r.motivo)

    def test_lugar_desconocido_degrada_con_opciones(self):
        r = tools.ruta_saludable("Narnia", "Moncloa", "general")
        self.assertFalse(r.disponible)
        self.assertIn("Atocha", r.lugares_disponibles)

    def test_sin_artefacto_degrada(self):
        with patch("asistente.ruta_saludable.disponible", return_value=False):
            r = tools.ruta_saludable("Atocha", "Sol", "general")
        self.assertFalse(r.disponible)
        self.assertIn("grafo_ruta.json", r.motivo)

    def test_momento_none_usa_dia_laborable(self):
        r = tools.ruta_saludable("Sol", "Chamartín", "sensible_aire", None)
        self.assertTrue(r.disponible)
        self.assertEqual(r.hora, 8)

    def test_ciclista_desvia_al_menos_como_general(self):
        c = tools.ruta_saludable("Legazpi", "Bernabéu", "ciclista", datetime(2026, 8, 26, 14))
        g = tools.ruta_saludable("Legazpi", "Bernabéu", "general", datetime(2026, 8, 26, 14))
        self.assertGreaterEqual(c.delta_distancia_pct, g.delta_distancia_pct - 1e-6)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_endpoint_ok(self):
        resp = self.client.get(
            "/ruta-saludable",
            params={"origen": "Atocha", "destino": "Moncloa", "perfil": "ciclista",
                    "momento": "2026-08-26T08:00:00"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["fiabilidad"], "baja")  # tope §7.4
        self.assertIn("Ruta saludable", body["explicacion"])

    def test_endpoint_lugar_malo(self):
        resp = self.client.get("/ruta-saludable", params={"origen": "zzz", "destino": "Sol"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["fiabilidad"], "baja")


class ModuloTests(unittest.TestCase):
    def test_dias_y_lugares(self):
        self.assertEqual(len(rs.dias()), 3)
        self.assertIn("Retiro", rs.lugares())

    def test_no_hay_camino_o_mismo_punto(self):
        # origen == destino -> ruta trivial de 1 nodo
        r = rs.ruta("Sol", "Sol", "general", dia=rs.dias()[0], hora=8)
        self.assertEqual(r["ruta_sana"]["n_nodos"], 1)


if __name__ == "__main__":
    unittest.main()
