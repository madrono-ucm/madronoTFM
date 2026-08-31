"""FIL_51 — tests de `grafo.exportar_grafo`.

`construir()` toca AWS (vía `grafo.extract`) → no se ejercita aquí. Se
validan las funciones puras (`_redondear`, `_contar`), el lector `cargar()`
y la coherencia del artefacto versionado `grafo/_data/grafo_urbano.json.gz`.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from grafo.exportar_grafo import _contar, _redondear, cargar

_GZ = Path(__file__).resolve().parents[1] / "_data" / "grafo_urbano.json.gz"


class PurasTests(unittest.TestCase):
    def test_contar(self):
        self.assertEqual(
            _contar([{"tipo": "a"}, {"tipo": "a"}, {"tipo": "b"}, {}], "tipo"),
            {"a": 2, "b": 1, "?": 1},
        )

    def test_redondear(self):
        g = {
            "relaciones": {"PROXIMO_A": [{"distancia_m": 123.4567}]},
            "nodos": {"L": [{"ubicacion": {"lat": 40.123456789, "lon": -3.98765432}}]},
        }
        _redondear(g)
        self.assertEqual(g["relaciones"]["PROXIMO_A"][0]["distancia_m"], 123)
        self.assertEqual(g["nodos"]["L"][0]["ubicacion"]["lat"], 40.123457)


class ArtefactoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _GZ.exists():
            raise unittest.SkipTest("falta grafo/_data/grafo_urbano.json.gz — corre `python -m grafo.exportar_grafo`")
        cls.g = cargar()

    def test_labels_y_relaciones(self):
        self.assertEqual(set(self.g["nodos"]), {"Distrito", "Barrio", "EstacionMedida", "ParadaTransporte", "Lugar"})
        self.assertEqual(set(self.g["relaciones"]), {"PERTENECE_A", "UBICADO_EN", "PROXIMO_A", "CONECTADO_CON"})
        self.assertEqual(len(self.g["nodos"]["Distrito"]), 21)
        self.assertEqual(len(self.g["nodos"]["Barrio"]), len(self.g["relaciones"]["PERTENECE_A"]))
        self.assertGreater(len(self.g["nodos"]["EstacionMedida"]), 1000)
        self.assertGreater(len(self.g["relaciones"]["PROXIMO_A"]), 5000)
        self.assertGreater(len(self.g["relaciones"]["CONECTADO_CON"]), 1000)

    def test_relaciones_referencian_nodos_reales(self):
        ids = {n["id"] for lab in ("EstacionMedida", "ParadaTransporte", "Lugar") for n in self.g["nodos"][lab]}
        barrios = {b["codigo"] for b in self.g["nodos"]["Barrio"]}
        for r in self.g["relaciones"]["PROXIMO_A"][:500]:
            self.assertIn(r["origen_id"], ids)
            self.assertIn(r["destino_id"], ids)
            self.assertIsInstance(r["distancia_m"], int)
        for r in self.g["relaciones"]["UBICADO_EN"][:500]:
            self.assertIn(r["barrio_codigo"], barrios)
        distritos = {d["codigo"] for d in self.g["nodos"]["Distrito"]}
        for r in self.g["relaciones"]["PERTENECE_A"]:
            self.assertIn(r["distrito_codigo"], distritos)

    def test_meta(self):
        m = self.g["_meta"]
        self.assertIn("generado", m)
        self.assertEqual(m["conteos_nodos"]["Distrito"], 21)
        self.assertIsInstance(m["tipos_estacion"], dict)


if __name__ == "__main__":
    unittest.main()
