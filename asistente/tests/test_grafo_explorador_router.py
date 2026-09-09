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

    def test_analisis_ensambla_cobertura_y_ficheros(self):
        ge._analisis_cache["data"] = None
        ge._analisis_cache["t"] = 0.0
        _COB = [{"id": "trafico:1", "con_aire": True}, {"id": "trafico:2", "con_aire": False}]
        _DIST = [{"distrito": "Centro", "n": 40, "trafico": 30, "aire": 3}]

        def _run(query, params, **kw):
            if "calidad_aire" in query and "EXISTS" in query:
                return _COB
            if "PERTENECE_A" in query:
                return _DIST
            return []

        with patch("asistente.routers.grafo_explorador.run_neo4j_query", side_effect=_run):
            r = self.client.get("/grafo/explorador/analisis")
        self.assertEqual(r.status_code, 200)
        a = r.json()
        self.assertEqual(a["cobertura_aire"]["sin_aire_cerca"], 1)
        self.assertEqual(a["cobertura_aire"]["ids_con_aire"], ["trafico:1"])
        self.assertEqual(a["sensores_por_distrito"][0]["distrito"], "Centro")
        # los ficheros vendorizados existen -> deben venir poblados
        self.assertGreaterEqual(len(a["stgnn_aristas_influyentes"]), 10)
        self.assertIn("n_puntos_articulacion", a["resiliencia"])

    def test_ruta_proximo_y_transporte(self):
        _RP = [{"metros": 812.4, "saltos": 3,
                "nodos": [{"id": "a", "tipo": "poi_turistico", "nombre": "A", "lat": 40.41, "lon": -3.70},
                          {"id": "m", "tipo": "trafico", "nombre": None, "lat": 40.42, "lon": -3.70},
                          {"id": "b", "tipo": "recinto", "nombre": "B", "lat": 40.43, "lon": -3.70}]}]
        _RT = [{"saltos": 2,
                "nodos": [{"id": "p1", "tipo": "metro", "nombre": "Sol", "lat": 40.41, "lon": -3.70},
                          {"id": "p2", "tipo": "metro", "nombre": "GV", "lat": 40.42, "lon": -3.70}],
                "tramos": [{"modo": "metro", "linea": "1"}]}]

        def _run(query, params, **kw):
            return _RT if "shortestPath" in query else _RP

        with patch("asistente.routers.grafo_explorador.run_neo4j_query", side_effect=_run):
            r1 = self.client.get("/grafo/explorador/ruta", params={"a": "a", "b": "b"})
            r2 = self.client.get("/grafo/explorador/ruta", params={"a": "p1", "b": "p2", "modo": "transporte"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["metros"], 812)
        self.assertEqual(len(r1.json()["nodos"]), 3)
        self.assertEqual(r2.json()["lineas"], ["metro 1"])

    def test_ruta_sin_camino_da_404(self):
        with patch("asistente.routers.grafo_explorador.run_neo4j_query", return_value=[]):
            r = self.client.get("/grafo/explorador/ruta", params={"a": "x", "b": "y"})
        self.assertEqual(r.status_code, 404)

    def test_ui_sirve_el_html_o_500(self):
        r = self.client.get("/grafo/explorador")
        # el HTML live se genera con `python -m viz.build_grafo_explorador --live`
        self.assertIn(r.status_code, (200, 500))
        if r.status_code == 200:
            self.assertIn("text/html", r.headers["content-type"])


if __name__ == "__main__":
    unittest.main()
