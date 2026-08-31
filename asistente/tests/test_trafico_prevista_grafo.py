"""Tests de la tool `trafico_prevista_grafo` y su router (`FIL_31`).

Mockea `run_neo4j_query` + `run_athena_query`; el modelo ONNX + `meta.json`
son los reales vendidos en `asistente/modelos/` (`stgnn_trafico.*`).
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
    (Path(prevision_grafo.__file__).resolve().parent / "modelos" / "stgnn_trafico.meta.json")
    .read_text(encoding="utf-8")
)
_NODOS = list(_META["node_index"])
_AHORA = datetime(2026, 8, 28, 12)
# un punto que aparece en la importancia de aristas del meta
_PID_TOP = _META["importancia_aristas"][0]["a"]
_PID_ALGUNO = _NODOS[0]

_GRAFO = [{"estacion_id": f"trafico:{_PID_TOP}", "distancia_m": 70.0}]


def _gold(instante: datetime, n=40):
    base = instante.replace(minute=0, second=0, microsecond=0)
    filas = []
    for pid in _NODOS:
        for k in range(n):
            t = base - timedelta(hours=k)
            filas.append({
                "point_id": pid,
                "date": t.date().isoformat(), "hour": t.hour,
                "avg_service_level": 1.0 + (hash(pid) % 30) * 0.1 + (k % 5) * 0.2,
            })
    return filas


class ToolTests(unittest.TestCase):
    def test_devuelve_prevision_de_grafo(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold(_AHORA)):
            r = tools.trafico_prevista_grafo("retiro", 3, 300.0, _AHORA)
        self.assertTrue(r.disponible)
        self.assertEqual(r.punto_id, _PID_TOP)
        self.assertIsNotNone(r.valor_previsto)
        self.assertEqual(r.unidad, "avg_service_level")
        self.assertIn(r.nivel_previsto, ("fluido", "denso", "congestionado"))
        self.assertEqual(r.n_nodos_grafo, len(_META["node_index"]))
        self.assertIn("stgnn_trafico.onnx", r.modelo)
        self.assertEqual(r.momento_objetivo, r.momento + timedelta(hours=3))
        # _PID_TOP es extremo de la arista más importante -> tiene vecino
        self.assertTrue(r.vecinos_influyentes)
        self.assertEqual(r.vecinos_influyentes[0].nodo, _META["importancia_aristas"][0]["b"])

    def test_horizonte_invalido(self):
        with self.assertRaises(ValueError):
            tools.trafico_prevista_grafo("retiro", 4, 300.0, _AHORA)

    def test_lugar_no_en_grafo_del_stgnn(self):
        # el grafo urbano devuelve un punto que NO está en el grafo del STGNN
        with patch("asistente.mcp_agent.tools.run_neo4j_query",
                   return_value=[{"estacion_id": "trafico:ZZZ999", "distancia_m": 50.0}]):
            r = tools.trafico_prevista_grafo("retiro", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("grafo del STGNN", r.motivo)

    def test_neo4j_caido_degrada(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", side_effect=RuntimeError("boom Neo4j")):
            r = tools.trafico_prevista_grafo("retiro", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("Neo4j", r.motivo)

    def test_athena_caido_degrada(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", side_effect=RuntimeError("boom Athena")):
            r = tools.trafico_prevista_grafo("retiro", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("Athena", r.motivo)

    def test_gold_vacio_degrada(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", return_value=[]):
            r = tools.trafico_prevista_grafo("retiro", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIsNone(r.valor_previsto)

    def test_modelo_ausente_degrada(self):
        with patch("asistente.prevision_grafo.disponible", return_value=False):
            r = tools.trafico_prevista_grafo("retiro", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("modelo de grafo de tráfico", r.motivo)

    def test_stgnn_revienta_en_inferencia_degrada(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold(_AHORA)), \
             patch("asistente.mcp_agent.tools.prevision_grafo.predecir",
                   side_effect=RuntimeError("onnxruntime boom")):
            r = tools.trafico_prevista_grafo("retiro", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("STGNN de tráfico", r.motivo)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_endpoint_ok(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
             patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold(_AHORA)):
            resp = self.client.get(
                "/trafico-prevista-grafo",
                params={"lugar": "retiro", "horizonte_horas": 3, "momento": _AHORA.isoformat()},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["fiabilidad"], "baja")  # tope a propósito (§7.4)
        self.assertIn("grafo STGNN", body["fuentes"][1]["dataset"])

    def test_endpoint_sin_datos(self):
        with patch("asistente.mcp_agent.tools.run_neo4j_query", side_effect=RuntimeError("x")):
            resp = self.client.get("/trafico-prevista-grafo", params={"lugar": "zzz"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["fiabilidad"], "baja")


if __name__ == "__main__":
    unittest.main()
