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
    construir_grafos,
    nombres_transporte,
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
        self.assertEqual(set(df.columns), {"parada", "modo", "grado", "intermediacion", "cercania"})

    def test_comunidades_devuelve_ari_nmi(self):
        gp, _ = construir_grafos(_G)
        c = comunidades_vs_barrios(_G, gp)
        for k in ("ARI", "NMI", "modularidad", "n_comunidades", "n_barrios"):
            self.assertIn(k, c)


class ArtefactosTests(unittest.TestCase):
    def test_artefactos_versionados(self):
        for f in ("grafo_centralidad_transporte.csv", "grafo_comunidades.json",
                  "grafo_stats.json", "grafo_stgnn_vs_conectividad.json", "grafo_analitica.png"):
            p = _ART / f
            if not p.exists():
                self.skipTest(f"falta {f} — corre `python -m modelado.grafo_analitica.analisis`")
            self.assertGreater(p.stat().st_size, 200)
        com = json.loads((_ART / "grafo_comunidades.json").read_text(encoding="utf-8"))
        self.assertTrue(0 <= com["NMI"] <= 1)
        self.assertGreater(com["n_comunidades"], 1)


if __name__ == "__main__":
    unittest.main()
