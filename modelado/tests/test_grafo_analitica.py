"""FIL_52 — tests de `modelado.grafo_analitica.analisis`.

`main()` corre betweenness sobre ~3k nodos (~30 s) → no se ejercita aquí.
Se prueban las funciones sobre un grafo sintético mínimo + se valida que
los artefactos versionados existen y tienen forma.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import networkx as nx

from modelado.grafo_analitica.analisis import (
    centralidad_transporte,
    comunidades_vs_barrios,
    resumen_centralidad,
    construir_grafos,
    curva_robustez,
    kcore_resumen,
    nombres_transporte,
    puentes_por_linea,
    puntos_de_articulacion,
    resiliencia_transporte,
)

_ART = Path(__file__).resolve().parents[2] / "modelado" / "evaluation" / "artifacts"

_G = {
    "nodos": {
        "Distrito": [{"codigo": "01", "nombre": "Centro"}],
        "Barrio": [{"codigo": "011", "nombre": "A", "distrito_codigo": "01"},
                   {"codigo": "012", "nombre": "B", "distrito_codigo": "01"}],
        "EstacionMedida": [{"id": "trafico:1", "tipo": "trafico", "ubicacion": {"lat": 40.4, "lon": -3.7}},
                           {"id": "ruido:1", "tipo": "ruido", "ubicacion": {"lat": 40.4, "lon": -3.7}}],
        "ParadaTransporte": [{"id": "crtm_red_transporte_madrid:par_1", "nombre": "SOL",
                              "tipo": "metro", "ubicacion": {"lat": 40.417, "lon": -3.703}}],
        "Lugar": [{"id": "poi:1", "tipo": "poi", "ubicacion": {"lat": 40.4, "lon": -3.7}}],
    },
    "relaciones": {
        "PERTENECE_A": [{"barrio_codigo": "011", "distrito_codigo": "01"},
                        {"barrio_codigo": "012", "distrito_codigo": "01"}],
        "UBICADO_EN": [{"nodo_id": "trafico:1", "barrio_codigo": "011"},
                       {"nodo_id": "ruido:1", "barrio_codigo": "011"},
                       {"nodo_id": "poi:1", "barrio_codigo": "012"}],
        "PROXIMO_A": [{"origen_id": "trafico:1", "destino_id": "ruido:1", "distancia_m": 10},
                      {"origen_id": "ruido:1", "destino_id": "poi:1", "distancia_m": 20}],
        "CONECTADO_CON": [{"origen": {"id": "crtm_red_transporte_madrid:9", "tipo": "metro",
                                      "ubicacion": {"lat": 40.417, "lon": -3.703}},
                           "destino": {"id": "crtm_red_transporte_madrid:8", "tipo": "metro",
                                       "ubicacion": {"lat": 40.42, "lon": -3.70}},
                           "modo": "metro", "linea": "1"}],
    },
}


class FuncionesTests(unittest.TestCase):
    def test_construir_grafos(self):
        gp, gc = construir_grafos(_G)
        self.assertEqual(gp.number_of_edges(), 2)
        self.assertEqual(gc.number_of_edges(), 1)
        self.assertEqual(gp.nodes["trafico:1"]["tipo"], "trafico")
        self.assertIn("pos", gc.nodes["crtm_red_transporte_madrid:9"])

    def test_nombres_por_coordenadas(self):
        _, gc = construir_grafos(_G)
        nm = nombres_transporte(_G, gc)
        self.assertEqual(nm["crtm_red_transporte_madrid:9"], "Sol")  # casa por <60 m

    def test_centralidad_df(self):
        _, gc = construir_grafos(_G)
        df = centralidad_transporte(gc, nombres_transporte(_G, gc))
        self.assertEqual(
            set(df.columns),
            {"nodo", "parada", "modo", "grado", "intermediacion", "cercania", "pagerank"},
        )
        # FIL_81: PageRank es una distribución (suma ~1 en la componente mayor)
        self.assertAlmostEqual(df["pagerank"].sum(), 1.0, places=4)

    def test_resumen_centralidad(self):
        gp, gc = construir_grafos(_G)
        cent = centralidad_transporte(gc, nombres_transporte(_G, gc))
        com = comunidades_vs_barrios(_G, gp)
        r = resumen_centralidad(cent, com, top=3)
        self.assertIn("_nota", r)
        self.assertLessEqual(len(r["top_pagerank"]), 3)
        self.assertLessEqual(len(r["top_intermediacion"]), 3)
        self.assertAlmostEqual(r["pagerank_suma"], 1.0, places=4)
        self.assertIn("modularidad", r["comunidades"])

    def test_comunidades_devuelve_ari_nmi(self):
        gp, _ = construir_grafos(_G)
        c = comunidades_vs_barrios(_G, gp)
        for k in ("ARI", "NMI", "modularidad", "n_comunidades", "n_barrios"):
            self.assertIn(k, c)

    def test_centralidad_acepta_betweenness_precalculado(self):  # FIL_85
        """`bet_inicial` da exactamente el mismo resultado que dejar que
        `centralidad_transporte` lo calcule por su cuenta -- confirma que
        reusarlo (para no repetir el cálculo O(V·E) en `curva_robustez`,
        `main()`) no cambia ninguna cifra."""
        import networkx as nx

        _, gc = construir_grafos(_G)
        nm = nombres_transporte(_G, gc)
        comp = max(nx.connected_components(gc), key=len)
        H = gc.subgraph(comp).copy()
        bet = nx.betweenness_centrality(H, normalized=True, seed=42)

        df_normal = centralidad_transporte(gc, nm)
        df_con_bet = centralidad_transporte(gc, nm, bet_inicial=bet)

        self.assertEqual(
            df_normal.sort_values("nodo").reset_index(drop=True)["intermediacion"].tolist(),
            df_con_bet.sort_values("nodo").reset_index(drop=True)["intermediacion"].tolist(),
        )


class ResilienciaTests(unittest.TestCase):
    """FIL_64. Grafo `CONECTADO_CON` sintético: dos "líneas" en cadena
    (A-B-C-D y D-E-F) unidas por la parada D → D es punto de articulación y
    cada tramo es un puente; más un triángulo C-C1-C2-C para que exista un
    2-core no trivial."""

    def _g(self):
        def stop(i):
            return {"id": f"crtm_red_transporte_madrid:{i}", "tipo": "metro",
                    "ubicacion": {"lat": 40.4 + ord(i[-1]) / 10000, "lon": -3.7}}

        tramos = [("A", "B", "1"), ("B", "C", "1"), ("C", "D", "1"),
                  ("D", "E", "2"), ("E", "F", "2"),
                  ("C", "C1", "3"), ("C1", "C2", "3"), ("C2", "C", "3")]
        rels = [{"origen": stop(u), "destino": stop(v), "modo": "metro", "linea": ln}
                for u, v, ln in tramos]
        return {"nodos": {"Distrito": [], "Barrio": [], "EstacionMedida": [],
                          "ParadaTransporte": [], "Lugar": []},
                "relaciones": {"PERTENECE_A": [], "UBICADO_EN": [], "PROXIMO_A": [],
                               "CONECTADO_CON": rels}}

    def test_puntos_de_articulacion_detecta_D(self):
        _, gc = construir_grafos(self._g())
        art = puntos_de_articulacion(gc, top=10)
        paradas = {a["parada"] for a in art}
        self.assertIn("crtm_red_transporte_madrid:D", paradas)
        for a in art:
            self.assertGreaterEqual(a["componentes_tras_quitar"], 2)

    def test_puentes_por_linea(self):
        _, gc = construir_grafos(self._g())
        p = puentes_por_linea(gc)
        # los 3 tramos del triángulo (linea "3") NO son puentes; el resto sí
        self.assertEqual(p["n_puentes"], 5)
        lineas = {(f["modo"], f["linea"]): f for f in p["por_linea_top"]}
        self.assertEqual(lineas[("metro", "3")]["tramos_puente"], 0)
        self.assertEqual(lineas[("metro", "1")]["frac_puentes"], 1.0)

    def test_kcore_resumen(self):
        _, gc = construir_grafos(self._g())
        kc = kcore_resumen(gc)
        self.assertEqual(kc["k_max"], 2)  # el triángulo
        self.assertGreaterEqual(kc["n_en_nucleo"], 3)

    def test_curva_robustez_monotona_y_dirigido_peor(self):
        _, gc = construir_grafos(self._g())
        r = curva_robustez(gc, frac_max=0.5, recalc_cada=1, reps_aleatorio=3)
        self.assertEqual(r["dirigido"][0], (0.0, 1.0))
        fracs = [f for f, _ in r["dirigido"]]
        self.assertEqual(fracs, sorted(fracs))
        # el ataque dirigido nunca deja un fragmento mayor que el fallo aleatorio
        self.assertLessEqual(r["frag_mayor_al_5pct"]["dirigido"],
                             r["frag_mayor_al_5pct"]["aleatorio"] + 1e-9)

    def test_curva_robustez_documenta_el_sesgo_del_recalc_por_lotes(self):  # FIL_86
        _, gc = construir_grafos(self._g())
        r = curva_robustez(gc, frac_max=0.5, recalc_cada=3, reps_aleatorio=1)
        self.assertIn("_nota_dirigido", r)
        self.assertIn("3", r["_nota_dirigido"])  # cita el recalc_cada real usado
        self.assertIn("FIL_86", r["_nota_dirigido"])

    def test_resiliencia_transporte_agrega(self):
        _, gc = construir_grafos(self._g())
        res = resiliencia_transporte(gc)
        for k in ("n_puntos_articulacion", "puntos_articulacion_top", "puentes", "kcore", "robustez"):
            self.assertIn(k, res)

    def test_curva_robustez_bet_inicial_no_recalcula_el_paso_0(self):  # FIL_85
        """Con `bet_inicial` dado, el paso 0 del ataque dirigido no debe
        llamar a `nx.betweenness_centrality` -- verifica que la reutilización
        realmente evita el cálculo duplicado, no solo que da el mismo
        número."""
        import networkx as nx
        from unittest.mock import patch

        _, gc = construir_grafos(self._g())
        H0 = gc.subgraph(max(nx.connected_components(gc), key=len)).copy()
        bet = nx.betweenness_centrality(H0, normalized=True, seed=42)

        with patch(
            "modelado.grafo_analitica.analisis.nx.betweenness_centrality",
            wraps=nx.betweenness_centrality,
        ) as spy:
            r_con_bet = curva_robustez(gc, frac_max=0.5, recalc_cada=1, reps_aleatorio=1, bet_inicial=bet)
            llamadas_con_bet = spy.call_count

        with patch(
            "modelado.grafo_analitica.analisis.nx.betweenness_centrality",
            wraps=nx.betweenness_centrality,
        ) as spy:
            r_sin_bet = curva_robustez(gc, frac_max=0.5, recalc_cada=1, reps_aleatorio=1)
            llamadas_sin_bet = spy.call_count

        self.assertEqual(llamadas_con_bet, llamadas_sin_bet - 1)
        self.assertEqual(r_con_bet["dirigido"], r_sin_bet["dirigido"])


class ArtefactosTests(unittest.TestCase):
    def test_artefactos_versionados(self):
        for f in ("grafo_centralidad_transporte.csv", "grafo_centralidad.json", "grafo_comunidades.json",
                  "grafo_stats.json", "grafo_stgnn_vs_conectividad.json", "grafo_analitica.png",
                  "grafo_resiliencia.json", "grafo_resiliencia.png"):
            p = _ART / f
            if not p.exists():
                self.skipTest(f"falta {f} — corre `python -m modelado.grafo_analitica.analisis`")
            self.assertGreater(p.stat().st_size, 200)
        com = json.loads((_ART / "grafo_comunidades.json").read_text(encoding="utf-8"))
        self.assertTrue(0 <= com["NMI"] <= 1)
        self.assertGreater(com["n_comunidades"], 1)
        cen = json.loads((_ART / "grafo_centralidad.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(cen["pagerank_suma"], 1.0, places=4)
        self.assertTrue(0 <= cen["comunidades"]["modularidad"] < 1)
        self.assertTrue(cen["top_pagerank"] and "parada" in cen["top_pagerank"][0])


if __name__ == "__main__":
    unittest.main()
