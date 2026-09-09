"""FIL_67 Parte 3 — valida `viz/build_grafo_explorador.py`.

Sin credenciales ni red: `construir()` es función pura sobre
`grafo/_data/grafo_urbano.json.gz` (reconstrucción del grafo de Neo4j).
"""

from __future__ import annotations

import json
import re
import unittest

from viz.build_grafo_explorador import _compactar, construir


class CompactarTests(unittest.TestCase):
    _G = {
        "nodos": {
            "Distrito": [{"codigo": "01", "nombre": "Centro"}],
            "Barrio": [{"codigo": "011", "nombre": "Sol", "distrito_codigo": "01"}],
            "EstacionMedida": [
                {"id": "calidad_aire:1", "tipo": "calidad_aire", "nombre": "Plaza X",
                 "ubicacion": {"lat": 40.41, "lon": -3.70}, "contaminantes": ["NO2", "O3"]},
                {"id": "meteorologia:1", "tipo": "meteo", "nombre": "Retiro",
                 "ubicacion": {"lat": 40.41, "lon": -3.68},
                 "magnitudes": ["temperature_c"], "altitud_m": 667},
                {"id": "trafico:1", "tipo": "trafico", "nombre": None,
                 "ubicacion": {"lat": 40.42, "lon": -3.70}, "subarea": "M30"},
            ],
            "ParadaTransporte": [],
            "Lugar": [
                {"id": "agenda_eventos:teatro", "tipo": "recinto", "nombre": "Teatro",
                 "ubicacion": {"lat": 40.415, "lon": -3.70}},
                {"id": "cartelera_cines_estrenos:x", "tipo": "cine", "nombre": "Cine",
                 "ubicacion": None},  # sin coords -> se descarta
            ],
        },
        "relaciones": {
            "UBICADO_EN": [{"nodo_id": "calidad_aire:1", "barrio_codigo": "011"}],
            "PROXIMO_A": [
                {"origen_id": "calidad_aire:1", "destino_id": "trafico:1", "distancia_m": 120.4},
                {"origen_id": "calidad_aire:1", "destino_id": "meteorologia:1", "distancia_m": 90.1},
            ],
            "CONECTADO_CON": [
                {"origen": {"id": "p1", "tipo": "metro", "ubicacion": {"lat": 40.4, "lon": -3.7}},
                 "destino": {"id": "p2", "tipo": "metro", "ubicacion": {"lat": 40.41, "lon": -3.71}},
                 "modo": "metro", "linea": "6"},
            ],
            "PERTENECE_A": [{"barrio_codigo": "011", "distrito_codigo": "01"}],
        },
    }

    def test_descarta_nodos_sin_coords(self):
        d = _compactar(self._G)
        self.assertNotIn("cartelera_cines_estrenos:x", d["nodos"])
        self.assertIn("agenda_eventos:teatro", d["nodos"])

    def test_barrio_distrito_real_y_atributos(self):
        d = _compactar(self._G)
        aire = d["nodos"]["calidad_aire:1"]
        self.assertEqual((aire["barrio"], aire["distrito"]), ("Sol", "Centro"))
        self.assertEqual(aire["attrs"]["contaminantes"], ["NO2", "O3"])
        self.assertEqual(d["nodos"]["meteorologia:1"]["attrs"]["altitud_m"], 667)
        self.assertEqual(d["nodos"]["trafico:1"]["attrs"]["subarea"], "M30")

    def test_proximo_a_bidireccional_y_conectado_con(self):
        d = _compactar(self._G)
        self.assertEqual({v[0] for v in d["prox"]["calidad_aire:1"]}, {"trafico:1", "meteorologia:1"})
        self.assertIn("calidad_aire:1", d["prox"]["trafico:1"][0])  # la relación va en ambos sentidos
        self.assertEqual(len(d["conn"]), 1)
        # paradas de CONECTADO_CON que no eran nodos se añaden desde la arista
        self.assertIn("p1", d["nodos"])
        self.assertEqual(d["lineas_de"]["p1"], ["metro 6"])


class ConstruirArtefactoTests(unittest.TestCase):
    def test_html_valido_con_datos_embebidos(self):
        html = construir()
        self.assertTrue(html.startswith("<!doctype html>"))
        for ph in ("__DATA__", "__COLORES__", "__LIVE__", "__ENDPOINT__"):
            self.assertNotIn(ph, html)
        self.assertIn("const LIVE = false;", html)
        m = re.search(r"let G = (\{.*?\});\nlet N", html, re.S)
        self.assertIsNotNone(m)
        d = json.loads(m.group(1))
        self.assertGreater(len(d["nodos"]), 5000)
        self.assertIn("prox", d)
        self.assertIn("conn", d)
        tipos = {n["tipo"] for n in d["nodos"].values()}
        self.assertIn("meteo", tipos)  # FIL_65
        self.assertIn("recinto", tipos)

    def test_variante_live_sin_datos_embebidos(self):  # FIL_67 Parte 3 (live)
        html = construir(live=True, endpoint="/grafo/explorador")
        self.assertIn("const LIVE = true;", html)
        self.assertIn('const ENDPOINT = "/grafo/explorador";', html)
        self.assertIn("let G = {};", html)  # nada embebido
        self.assertIn('fetch(ENDPOINT + "/data")', html)
        self.assertIn('fetch(ENDPOINT + "/vecindario?id="', html)
        self.assertLess(len(html), 40_000, "la variante live no debe llevar el grafo embebido")


if __name__ == "__main__":
    unittest.main()
