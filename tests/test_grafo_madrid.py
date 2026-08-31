"""FIL_32 — valida el grafo canónico de Madrid (`viz/build_grafo_madrid.py`)
y el artefacto `viz/grafo_madrid.json` versionado.

Sin credenciales ni red: `construir()` es función pura sobre ficheros del
repo (los `meta.json` vendorizados + el GeoJSON de distritos + el slice
congelado de ruido).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from viz.build_grafo_madrid import construir

_RAIZ = Path(__file__).resolve().parents[1]
_ARTEFACTO = _RAIZ / "viz" / "grafo_madrid.json"
_META_TRAFICO = json.loads(
    (_RAIZ / "asistente" / "modelos" / "stgnn_trafico.meta.json").read_text(encoding="utf-8")
)


class ConstruirTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = construir()

    def test_un_nodo_por_entrada_de_node_index(self):
        self.assertEqual(self.g["n_nodos"], len(_META_TRAFICO["node_index"]))
        self.assertEqual(len(self.g["nodos"]), 1798)
        ids = {n["id"] for n in self.g["nodos"]}
        self.assertEqual(ids, set(_META_TRAFICO["node_index"]))

    def test_todo_nodo_tiene_coords_y_distrito(self):
        for n in self.g["nodos"]:
            self.assertIsInstance(n["lat"], float)
            self.assertIsInstance(n["lon"], float)
            self.assertIsNotNone(n["distrito"], f"nodo {n['id']} sin distrito")

    def test_aristas_no_dirigidas_referencian_nodos_validos(self):
        ids = {n["id"] for n in self.g["nodos"]}
        vistas = set()
        for e in self.g["aristas"]:
            self.assertIn(e["a"], ids)
            self.assertIn(e["b"], ids)
            self.assertLess(e["a"], e["b"], "arista no canónica (a<b)")
            self.assertNotIn((e["a"], e["b"]), vistas, "arista duplicada")
            vistas.add((e["a"], e["b"]))
            self.assertGreater(e["length_m"], 0.0)
        # 17.516 dirigidas simétricas -> ~la mitad no dirigidas
        self.assertLessEqual(self.g["n_aristas"], len(_META_TRAFICO["edge_weight"]))
        self.assertGreater(self.g["n_aristas"], len(_META_TRAFICO["edge_weight"]) // 3)

    def test_importancia_aristas_endpoints_en_el_grafo(self):
        ids = {n["id"] for n in self.g["nodos"]}
        self.assertTrue(self.g["importancia_aristas"])
        for e in self.g["importancia_aristas"]:
            self.assertIn(e["a"], ids)
            self.assertIn(e["b"], ids)

    def test_lookups(self):
        ids = {n["id"] for n in self.g["nodos"]}
        for est in self.g["estaciones_aire"].values():
            self.assertIn(est["nodo_mas_cercano"], ids)
        total = sum(len(v) for v in self.g["distrito_a_nodos"].values())
        self.assertEqual(total, self.g["n_nodos"])
        self.assertNotIn("sin_distrito", self.g["distrito_a_nodos"])


class ArtefactoTests(unittest.TestCase):
    def test_artefacto_versionado_al_dia(self):
        self.assertTrue(_ARTEFACTO.exists(), "falta viz/grafo_madrid.json — corre `python -m viz.build_grafo_madrid`")
        guardado = json.loads(_ARTEFACTO.read_text(encoding="utf-8"))
        fresco = construir()
        self.assertEqual(guardado["n_nodos"], fresco["n_nodos"])
        self.assertEqual(guardado["n_aristas"], fresco["n_aristas"])
        self.assertEqual(
            [n["id"] for n in guardado["nodos"]],
            [n["id"] for n in fresco["nodos"]],
        )


if __name__ == "__main__":
    unittest.main()
