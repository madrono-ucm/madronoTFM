"""FIL_34 (M3) — valida los artefactos de `viz/build_mapa_animado.py`
(`viz/mapa/*.json` + `index.html` + la tira PNG) sin abrir un navegador.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

_MAPA = Path(__file__).resolve().parents[1] / "viz" / "mapa"
_PNG = Path(__file__).resolve().parents[1] / "viz" / "mapa_frames.png"


class MapaArtefactosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for f in ("meta.json", "data.json", "weather.json", "index.html"):
            if not (_MAPA / f).exists():
                raise unittest.SkipTest(f"falta viz/mapa/{f} — corre `python -m viz.build_mapa_animado`")
        cls.meta = json.loads((_MAPA / "meta.json").read_text(encoding="utf-8"))
        cls.data = json.loads((_MAPA / "data.json").read_text(encoding="utf-8"))
        cls.wx = json.loads((_MAPA / "weather.json").read_text(encoding="utf-8"))
        cls.html = (_MAPA / "index.html").read_text(encoding="utf-8")

    def test_meta_coherente(self):
        self.assertEqual(self.meta["n_nodos"], 1798)
        self.assertEqual(len(self.meta["coords"]), 1798)
        self.assertEqual(len(self.meta["distrito"]), 1798)
        self.assertTrue(1 <= len(self.meta["arcs"]) <= 15)
        self.assertEqual(self.meta["distritos_geojson"]["type"], "FeatureCollection")
        for m in ("salud", "trafico", "no2", "o3"):
            self.assertIn(m, self.meta["metricas"])

    def test_frames_forma(self):
        self.assertEqual(sorted(self.data), sorted(self.meta["dias"]))
        for dia, md in self.data.items():
            for k in ("salud", "trafico", "no2", "o3", "traf_now", "traf_h1", "traf_h1_act"):
                self.assertEqual(len(md[k]), 24, f"{dia}/{k} != 24 h")
                self.assertEqual(len(md[k][0]), 1798)

    def test_weather_por_dia_y_hora(self):
        for dia in self.meta["dias"]:
            self.assertIn(dia, self.wx)
            algun = next(iter(self.wx[dia].values()))
            self.assertIn("temp_c", algun)

    def test_html_autonomo_salvo_deckgl(self):
        self.assertIn("deck.gl@", self.html)  # única dependencia externa
        self.assertIn('fetch("./meta.json")', self.html)
        self.assertNotIn("mapbox", self.html.lower())  # sin tiles/token
        self.assertIn("<title>", self.html)

    def test_capas_ricas_presentes(self):
        # E2 ghost, E4 panel glass-box de nodo, E6 pulso de distrito, E3 ruta
        for marca in ("id=\"ghost\"", "pane-a", "id=\"pulse\"", "edgePane", "ArcLayer",
                      "traf_h1_act", "routeLayers", "PathLayer", 'fetch("./rutas.json")'):
            self.assertIn(marca, self.html, f"falta {marca} en el HTML")

    def test_meta_lookups_para_paneles(self):
        self.assertEqual(len(self.meta["node_id"]), 1798)
        self.assertIsInstance(self.meta["distrito_nombre"], dict)
        # todo id de distrito de un nodo tiene nombre
        for did in set(self.meta["distrito"]):
            self.assertIn(did, self.meta["distrito_nombre"])

    def test_png_existe(self):
        self.assertTrue(_PNG.exists())
        self.assertGreater(_PNG.stat().st_size, 20_000)


if __name__ == "__main__":
    unittest.main()
