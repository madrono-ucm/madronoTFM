"""Tests del router `grafo_explorador` (FIL_67 Parte 3, explorador en vivo).

Sin Neo4j real: se parchea `run_neo4j_query`. Cubre el ensamblado de
`/data`, el vecindario y la degradación a 503.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente.main import create_app
from asistente.routers import grafo_explorador as ge

_NODOS = [
    {"label": "EstacionMedida", "id": "calidad_aire:1", "tipo": "calidad_aire", "nombre": "Plaza X",
     "lat": 40.41, "lon": -3.70, "barrio": "Sol", "distrito": "Centro",
     "contaminantes": ["NO2", "O3"], "magnitudes": None, "altitud_m": None, "subarea": None,
     "anclajes_totales": None, "plazas_totales": None},
    {"label": "ParadaTransporte", "id": "p1", "tipo": "metro", "nombre": "Sol",
     "lat": 40.417, "lon": -3.703, "barrio": None, "distrito": None,
     "contaminantes": None, "magnitudes": None, "altitud_m": None, "subarea": None,
     "anclajes_totales": None, "plazas_totales": None},
    {"label": "ParadaTransporte", "id": "p2", "tipo": "metro", "nombre": "Gran Vía",
     "lat": 40.420, "lon": -3.701, "barrio": None, "distrito": None,
     "contaminantes": None, "magnitudes": None, "altitud_m": None, "subarea": None,
     "anclajes_totales": None, "plazas_totales": None},
]
_CONN = [{"a": "p1", "b": "p2", "modo": "metro", "linea": "1"},
         {"a": "p2", "b": "p1", "modo": "metro", "linea": "1"}]  # simétrica -> 1 sola arista
_VECINOS = [
    {"label": "ParadaTransporte", "id": "p1", "tipo": "metro", "nombre": "Sol",
     "lat": 40.417, "lon": -3.703, "distancia_m": 90.4,
     "contaminantes": None, "magnitudes": None, "altitud_m": None, "subarea": None,
     "anclajes_totales": None, "plazas_totales": None},
]


def _fake_run(query, params, **kw):
    if "CONECTADO_CON" in query:
        return _CONN
    if "PROXIMO_A" in query:
        return _VECINOS
    return _NODOS


class RouterTests(unittest.TestCase):
    def setUp(self):
        ge._cache["data"] = None
        ge._cache["t"] = 0.0
        self.client = TestClient(create_app())

    def test_data_ensambla_nodos_conn_y_lineas(self):
        with patch("asistente.routers.grafo_explorador.run_neo4j_query", side_effect=_fake_run):
            r = self.client.get("/grafo/explorador/data")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(set(d["nodos"]), {"calidad_aire:1", "p1", "p2"})
        self.assertEqual(d["nodos"]["calidad_aire:1"]["attrs"]["contaminantes"], ["NO2", "O3"])
        self.assertEqual(d["nodos"]["calidad_aire:1"]["barrio"], "Sol")
        self.assertEqual(len(d["conn"]), 1)  # simétrica plegada
        self.assertEqual(d["lineas_de"]["p1"], ["metro 1"])
        self.assertEqual(d["meta"]["n_nodos"], 3)

    def test_data_cacheada(self):
        with patch("asistente.routers.grafo_explorador.run_neo4j_query", side_effect=_fake_run) as m:
            self.client.get("/grafo/explorador/data")
            self.client.get("/grafo/explorador/data")
        self.assertEqual(m.call_count, 2)  # 1 llamada = nodos + conn; la 2ª petición sale de cache

    def test_vecindario(self):
        with patch("asistente.routers.grafo_explorador.run_neo4j_query", side_effect=_fake_run):
            r = self.client.get("/grafo/explorador/vecindario", params={"id": "calidad_aire:1"})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["n"], 1)
        self.assertEqual(j["vecinos"][0]["id"], "p1")
        self.assertEqual(j["vecinos"][0]["distancia_m"], 90)  # redondeado

    def test_neo4j_caido_da_503(self):
        def _boom(*a, **k):
            raise RuntimeError("connection refused")

        with patch("asistente.routers.grafo_explorador.run_neo4j_query", side_effect=_boom):
            r = self.client.get("/grafo/explorador/data")
        self.assertEqual(r.status_code, 503)
        self.assertIn("Neo4j", r.json()["detail"])

    def test_ui_sirve_el_html_o_500(self):
        r = self.client.get("/grafo/explorador")
        # el HTML live se genera con `python -m viz.build_grafo_explorador --live`
        self.assertIn(r.status_code, (200, 500))
        if r.status_code == 200:
            self.assertIn("text/html", r.headers["content-type"])


if __name__ == "__main__":
    unittest.main()
