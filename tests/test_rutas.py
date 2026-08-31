"""FIL_37 (M6) — `viz/rutas.py`: enrutado saludable multi-objetivo sobre el
grafo de Madrid. Sin red ni credenciales (grafo + parquet del repo).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from viz.rutas import LUGARES, PERFILES, _grafo_nx, mejor_hora, ruta

_DIA = "2026-08-26"
_RUTAS_JSON = Path(__file__).resolve().parents[1] / "viz" / "mapa" / "rutas.json"


class GrafoTests(unittest.TestCase):
    def test_componente_conexa_grande(self):
        g, _ = _grafo_nx()
        # coords-knn8 deja ~137 nodos sueltos; la mayor debe cubrir casi todo
        self.assertGreater(g.number_of_nodes(), 1500)
        for a, b in list(g.edges())[:50]:
            self.assertIn("length_m", g[a][b])


class RutaTests(unittest.TestCase):
    def test_ruta_sana_vs_rapida(self):
        r = ruta("Atocha", "Moncloa", "ciclista", dia=_DIA, hora=8)
        self.assertGreaterEqual(len(r["ruta_sana"]["path"]), 2)
        self.assertEqual(r["ruta_sana"]["path"][0], r["nodo_origen"])
        self.assertEqual(r["ruta_sana"]["path"][-1], r["nodo_destino"])
        # la ruta rápida nunca es más larga que la sana
        self.assertLessEqual(r["ruta_rapida"]["dist_m"], r["ruta_sana"]["dist_m"] + 1.0)
        # coords son [lon, lat]
        lon, lat = r["ruta_sana"]["coords"][0]
        self.assertTrue(-4 < lon < -3 and 40 < lat < 41)

    def test_perfil_invalido(self):
        with self.assertRaises(ValueError):
            ruta("Sol", "Retiro", "supersonico", dia=_DIA, hora=8)

    def test_ciclista_desvia_mas_que_general(self):
        # sobre varios pares, el desvío medio del ciclista >= el del general
        pares = [("Atocha", "Moncloa"), ("Legazpi", "Bernabéu"), ("Plaza Elíptica", "Cibeles")]
        dc = dg = 0.0
        for o, d in pares:
            dc += ruta(o, d, "ciclista", dia=_DIA, hora=14)["delta_dist_pct"]
            dg += ruta(o, d, "general", dia=_DIA, hora=14)["delta_dist_pct"]
        self.assertGreaterEqual(dc, dg)

    def test_mejor_hora_en_ventana(self):
        mh = mejor_hora("Sol", "Chamartín", "sensible_aire", dia=_DIA, ventana=range(6, 11))
        self.assertIn(mh["mejor_hora"], range(6, 11))


class ArtefactoTests(unittest.TestCase):
    def test_rutas_json_al_dia(self):
        if not _RUTAS_JSON.exists():
            self.skipTest("falta viz/mapa/rutas.json — corre `python -m viz.rutas`")
        d = json.loads(_RUTAS_JSON.read_text(encoding="utf-8"))
        self.assertIn("rutas", d)
        self.assertIn("pareto", d)
        for ru in d["rutas"]:
            self.assertEqual(len(ru["por_hora"]), 24)
            self.assertIn(ru["perfil"], PERFILES)
            self.assertIn(ru["origen"], LUGARES)


if __name__ == "__main__":
    unittest.main()
