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

    # --- FIL_47: legibilidad ---
    def test_meta_legibilidad(self):
        self.assertEqual(len(self.meta["distrito_centroide"]), 21)
        for c in self.meta["distrito_centroide"]:
            lon, lat = c["pos"]
            self.assertTrue(-4 < lon < -3 and 40 < lat < 41)
            self.assertTrue(c["nombre"])
        self.assertEqual(len(self.meta["hitos"]), 14)
        nombres = {h["nombre"] for h in self.meta["hitos"]}
        self.assertIn("Plaza Elíptica", nombres)
        (a, b), (c, d) = self.meta["bbox"]
        self.assertTrue(a < c and b < d)
        self.assertGreaterEqual(len(self.meta["ejes_geojson"]["features"]), 5)
        self.assertGreaterEqual(len(self.meta["parques_geojson"]["features"]), 10)
        pq = {f["properties"]["nombre"] for f in self.meta["parques_geojson"]["features"]}
        self.assertTrue(any("Retiro" in n for n in pq))
        self.assertTrue(any("Casa de Campo" in n for n in pq))

    def test_html_legibilidad(self):
        for marca in ("TextLayer", "WebMercatorViewport", "getTooltip", "fitBounds",
                      'id="v2d"', 'id="v3d"', 'id="fit"', 'id="l-ejes"', 'id="l-parques"',
                      'id="r-od"', 'id="r-perfil"', "<details", "titulo-sub",
                      'characterSet:"auto"', "focus-visible", 'lang="es"'):
            self.assertIn(marca, self.html, f"falta {marca} en el HTML (FIL_47)")

    def test_html_pulido_y_clic(self):
        # FIL_48: clic en nodo restaurado + anillo de selección + vista limpia
        for marca in ("onClick:onNode", "const onNode = info", 'id:"sel"', 'id="clean"',
                      "state.clean", "nodeRmin"):
            self.assertIn(marca, self.html, f"falta {marca} en el HTML (FIL_48)")
        self.assertNotIn('id="l-tex" checked', self.html)  # textura off por defecto

    def test_html_barras_y_resumen(self):
        # FIL_49: ColumnLayer (barras 3D) + selector de representación + panel de resumen
        for marca in ("ColumnLayer", "nodeElev", "usaBarras", 'class="rp"',
                      'id="resumen"', "function resumen()", 'id="rs-city"', 'id="rs-distr"'):
            self.assertIn(marca, self.html, f"falta {marca} en el HTML (FIL_49)")

    def test_meta_tex_es_el_grafo_completo(self):
        # FIL_49: la capa "textura" pasa a ser TODAS las aristas del grafo
        self.assertGreater(len(self.meta["tex"]), 8000)

    # --- FIL_45: capa social ---
    def test_meta_capa_social(self):
        self.assertEqual(len(self.meta["perfiles"]), 9)
        for w in self.meta["perfiles"].values():
            self.assertEqual(set(w), {"traf", "no2", "o3", "noise"})
        self.assertIn("asma_epoc", self.meta["perfiles"])
        self.assertIn("movilidad_reducida", self.meta["perfiles"])
        for k in ("no2", "o3", "salud"):
            u = self.meta["umbrales"][k]
            self.assertEqual(len(u["cortes"]) + 1, len(u["bandas"]))
        self.assertEqual(len(self.meta["idw_dist"]), 1798)
        self.assertEqual(len(self.meta["ruido_distrito"]), 21)

    def test_html_capa_social(self):
        for marca in ("salud_perfil", "dosis_no2", "dosis_o3", 'id="perfiles"',
                      'data-e="bandas"', 'id="l-idw"', "mejorHoraPerfil", "BANDAS_PAL",
                      "consejo médico", 'id="mejor-hora"'):
            self.assertIn(marca, self.html, f"falta {marca} en el HTML (FIL_45)")


if __name__ == "__main__":
    unittest.main()
