"""Tests de la tool `calidad_aire_prevista_grafo` y su router (`FIL_26`).

Mockea `run_athena_query`; el modelo ONNX + `meta.json` son los reales
vendidos en `asistente/modelos/` (`stgnn_calidad_aire.*`).
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente import prevision_grafo
from asistente.main import create_app
from asistente.mcp_agent import tools

_META = json.loads(
    (Path(prevision_grafo.__file__).resolve().parent / "modelos" / "stgnn_calidad_aire.meta.json")
    .read_text(encoding="utf-8")
)
_NODOS = list(_META["node_index"])
_ESTACIONES = sorted({n.split("__", 1)[0] for n in _NODOS})
_AHORA = datetime(2026, 8, 28, 12)

_NOMBRES = {
    "28079004": "Plaza de España", "28079035": "Pza. del Carmen",
    "28079049": "Retiro", "28079050": "Barrio del Pilar",
}


def _gold(instante: datetime, n=40):
    """Una lectura por (nodo del grafo, hora) durante `n` horas."""
    base = instante.replace(minute=0, second=0, microsecond=0)
    filas = []
    for nodo in _NODOS:
        sid, pol = nodo.split("__", 1)
        for k in range(n):
            t = base - timedelta(hours=k)
            filas.append({
                "station_id": sid, "station_name": _NOMBRES.get(sid, sid),
                "pollutant": pol, "unit": "µg/m³",
                "date": t.date().isoformat(), "hour": t.hour,
                "avg_value": 45.0 + (hash(nodo) % 25) + (k % 6) * 2.0,
            })
    return filas


class ToolTests(unittest.TestCase):
    def test_devuelve_prevision_de_grafo_con_vecinos(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold(_AHORA)):
            r = tools.calidad_aire_prevista_grafo("España", 3, _AHORA)
        self.assertTrue(r.disponible)
        self.assertIsNotNone(r.valor_previsto)
        self.assertEqual(r.nodo.split("__", 1)[0], "28079004")
        self.assertEqual(r.n_nodos_grafo, len(_META["node_index"]))
        self.assertIn("stgnn_calidad_aire.onnx", r.modelo)
        self.assertEqual(r.momento_objetivo, r.momento + timedelta(hours=3))
        self.assertIn(r.grafo, ("coords-knn8",))
        # vecinos: puede haber 0 si el nodo elegido no aparece en el top-15,
        # pero el campo existe y es una lista de VecinoGrafo
        self.assertIsInstance(r.vecinos_influyentes, list)

    def test_nodo_con_aristas_en_el_top_devuelve_vecinos(self):
        # 28079035__O3 es un extremo de la arista más importante del meta
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold(_AHORA)):
            r = tools.calidad_aire_prevista_grafo("Carmen", 3, _AHORA)
        self.assertEqual(r.estacion, "Pza. del Carmen")
        if r.nodo == "28079035__O3":
            self.assertTrue(r.vecinos_influyentes)
            self.assertEqual(r.vecinos_influyentes[0].contaminante, "O3")

    def test_horizonte_invalido(self):
        with self.assertRaises(ValueError):
            tools.calidad_aire_prevista_grafo("España", 4, _AHORA)

    def test_sin_estacion_coincidente(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold(_AHORA)):
            r = tools.calidad_aire_prevista_grafo("no-existe-zzz", 3, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("no-existe-zzz", r.motivo)

    def test_athena_caido_degrada(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", side_effect=RuntimeError("boom Athena")):
            r = tools.calidad_aire_prevista_grafo("España", 3, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("Athena", r.motivo)

    def test_gold_vacio_degrada(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=[]):
            r = tools.calidad_aire_prevista_grafo("España", 3, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIsNone(r.valor_previsto)

    def test_modelo_ausente_degrada(self):
        with patch("asistente.prevision_grafo.disponible", return_value=False):
            r = tools.calidad_aire_prevista_grafo("España", 3, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("modelo de grafo", r.motivo)

    def test_meta_corrupto_degrada_sin_excepcion(self):
        # disponible=True (los ficheros existen) pero cargar el meta revienta
        with patch("asistente.prevision_grafo.disponible", return_value=True), \
             patch("asistente.mcp_agent.tools.prevision_grafo.info",
                   side_effect=ValueError("meta.feature_cols no casa")):
            r = tools.calidad_aire_prevista_grafo("España", 3, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("no se pudo cargar el modelo de grafo", r.motivo)

    def test_stgnn_revienta_en_inferencia_degrada(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold(_AHORA)), \
             patch("asistente.mcp_agent.tools.prevision_grafo.predecir",
                   side_effect=RuntimeError("onnxruntime boom")):
            r = tools.calidad_aire_prevista_grafo("España", 3, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("fallo corriendo el STGNN", r.motivo)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_endpoint_ok(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold(_AHORA)):
            resp = self.client.get(
                "/calidad-aire-prevista-grafo",
                params={"zona": "España", "horizonte_horas": 3, "momento": _AHORA.isoformat()},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["fiabilidad"], "baja")   # tope a propósito (§7.4)
        self.assertIn("grafo", body["fuentes"][1]["dataset"])

    def test_endpoint_sin_datos(self):
        with patch("asistente.mcp_agent.tools.run_athena_query", return_value=[]):
            resp = self.client.get("/calidad-aire-prevista-grafo", params={"zona": "zzz"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["fiabilidad"], "baja")


if __name__ == "__main__":
    unittest.main()
