"""Tests de la tool `mejor_hora_zona` y su router (`FIL_46`).

Usa el artefacto real vendorizado en `asistente/modelos/grafo_ruta.json`
(sin Neo4j, sin Athena, sin red).
"""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente import mejor_hora_zona as mhz
from asistente.main import create_app
from asistente.mcp_agent import tools


class ModuloTests(unittest.TestCase):
    def test_21_distritos(self):
        zonas = mhz.zonas_disponibles()
        self.assertEqual(len(zonas), 21)
        self.assertIn("Centro", zonas)
        self.assertIn("Retiro", zonas)

    def test_resuelve_por_nombre_id_y_alias(self):
        g = mhz._ruta._cargar(mhz._ruta._ARTEFACTO)
        self.assertEqual(mhz._resolver_zona(g, "Centro")[1], "Centro")
        self.assertEqual(mhz._resolver_zona(g, "13")[1], "Puente de Vallecas")
        self.assertEqual(mhz._resolver_zona(g, "distrito de salamanca")[1], "Salamanca")
        self.assertEqual(mhz._resolver_zona(g, "moncloa")[1], "Moncloa - Aravaca")
        self.assertEqual(mhz._resolver_zona(g, "san blas")[1], "San Blas - Canillejas")

    def test_vallecas_es_ambiguo(self):
        g = mhz._ruta._cargar(mhz._ruta._ARTEFACTO)
        with self.assertRaises(ValueError) as cm:
            mhz._resolver_zona(g, "Vallecas")
        self.assertIn("Puente de Vallecas", str(cm.exception))
        self.assertIn("Villa de Vallecas", str(cm.exception))

    def test_zona_desconocida(self):
        g = mhz._ruta._cargar(mhz._ruta._ARTEFACTO)
        with self.assertRaises(ValueError) as cm:
            mhz._resolver_zona(g, "Gotham")
        self.assertIn("Centro", str(cm.exception))  # lista los distritos

    def test_barrido_forma_y_orden(self):
        r = mhz.mejor_hora_zona("Centro", "asma_epoc")
        self.assertEqual(len(r["serie_horaria"]), 24)
        self.assertEqual(r["distrito"], "Centro")
        self.assertEqual(r["dia"], mhz.dias()[-1])
        self.assertIn(r["mejor_hora"], range(24))
        self.assertIn(r["peor_hora"], range(24))
        # la mejor hora es un mínimo de la serie; la peor un máximo
        self.assertEqual(r["serie_horaria"][r["mejor_hora"]], min(r["serie_horaria"]))
        self.assertEqual(r["serie_horaria"][r["peor_hora"]], max(r["serie_horaria"]))
        self.assertLessEqual(r["franja_inicio"], r["franja_fin"])
        self.assertGreaterEqual(r["reduccion_vs_peor_pct"], 0.0)
        self.assertGreater(r["n_nodos_zona"], 0)

    def test_el_perfil_cambia_la_serie(self):
        gen = mhz.mejor_hora_zona("Centro", "general")["serie_horaria"]
        asma = mhz.mejor_hora_zona("Centro", "asma_epoc")["serie_horaria"]
        self.assertNotEqual(gen, asma)


class ToolTests(unittest.TestCase):
    def test_camino_feliz(self):
        r = tools.mejor_hora_zona("Chamberí", "mayor", datetime(2026, 8, 26, 8))
        self.assertTrue(r.disponible)
        self.assertEqual(r.distrito, "Chamberí")
        self.assertEqual(r.dia, "2026-08-26")
        self.assertEqual(len(r.serie_horaria), 24)
        self.assertIn(r.mejor_hora, range(24))
        self.assertIsNotNone(r.franja_inicio)
        self.assertIn("consejo médico", r.nota)

    def test_momento_none_usa_ultimo_dia_curado(self):
        r = tools.mejor_hora_zona("Retiro")
        self.assertTrue(r.disponible)
        self.assertEqual(r.dia, mhz.dias()[-1])

    def test_perfil_invalido_degrada(self):
        r = tools.mejor_hora_zona("Centro", "supersonico")
        self.assertFalse(r.disponible)
        self.assertIn("perfil", r.motivo)

    def test_zona_ambigua_degrada_con_lista(self):
        r = tools.mejor_hora_zona("Vallecas", "general")
        self.assertFalse(r.disponible)
        self.assertIn("Puente de Vallecas", r.motivo)
        self.assertIn("Centro", r.zonas_disponibles)

    def test_zona_desconocida_degrada(self):
        r = tools.mejor_hora_zona("Gotham City", "general")
        self.assertFalse(r.disponible)
        self.assertEqual(len(r.zonas_disponibles), 21)

    def test_sin_artefacto_degrada(self):
        with patch("asistente.mejor_hora_zona.disponible", return_value=False):
            r = tools.mejor_hora_zona("Centro", "general")
        self.assertFalse(r.disponible)
        self.assertIn("grafo_ruta.json", r.motivo)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_endpoint_ok(self):
        resp = self.client.get(
            "/mejor-hora-zona",
            params={"zona": "Centro", "perfil": "asma_epoc", "momento": "2026-08-26T08:00:00"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["fiabilidad"], "baja")  # tope §7.4
        self.assertIn("franja más limpia", body["explicacion"])

    def test_endpoint_zona_mala(self):
        resp = self.client.get("/mejor-hora-zona", params={"zona": "zzz"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["fiabilidad"], "baja")


if __name__ == "__main__":
    unittest.main()
