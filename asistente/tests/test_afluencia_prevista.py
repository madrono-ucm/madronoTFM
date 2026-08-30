"""Tests de la tool derivada `afluencia_prevista` y su router (`FIL_14`).

`afluencia_prevista` no habla con backends directamente: compone
`_trafico_prevista_impl` (único subcomponente con modelo) y
`_afluencia_estimada_impl` (nivel actual + persistencia de ruido/BiciMAD).
Aquí se mockean esos dos `_impl` para probar la fusión y la degradación de
forma aislada; ambos tienen sus propios tests contra Athena/Neo4j mockeados.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from asistente.main import create_app
from asistente.mcp_agent import tools
from asistente.models.herramientas import (
    AfluenciaEstimada,
    EstacionRuidoCercana,
    ParadaBicimadCercana,
    TraficoPrevista,
)
from asistente.models.respuesta import RespuestaPrevision

_AHORA = datetime(2026, 8, 17, 10)
_ANCLA = datetime(2026, 8, 17, 9)


def _tp(disponible=True, valor=2.0, motivo=None):
    return TraficoPrevista(
        lugar="retiro", horizonte_horas=3,
        momento=_ANCLA,
        momento_objetivo=_ANCLA + timedelta(hours=3) if disponible else None,
        disponible=disponible,
        valor_previsto=valor if disponible else None,
        valor_actual=1.8,
        nivel_previsto="denso" if disponible else "sin_datos",
        data_completeness=0.8, ventana_datos="2026-08-16..2026-08-17",
        modelo="trafico_h3.onnx (ML_07 / madrono-trafico-h3)" if disponible else None,
        motivo=motivo,
        fuente_dataset="gold.trafico_por_punto_hora",
    )


def _est(nivel="alto", con_persistencia=True):
    return AfluenciaEstimada(
        lugar="retiro", momento=_AHORA, radio_m=300.0, nivel_estimado=nivel,
        ruido=[EstacionRuidoCercana(station_id="R1", distancia_m=50.0, avg_laeq_db=60.0)] if con_persistencia else [],
        bicimad=[ParadaBicimadCercana(station_id="B1", distancia_m=40.0, avg_occupancy_ratio=0.5)] if con_persistencia else [],
        fuente_grafo="neo4j",
        fuentes_gold=["gold.ruido_por_estacion_periodo_fecha"],
    )


class FusionTests(unittest.TestCase):
    def test_es_subclase_de_respuestaprevision(self):
        self.assertTrue(issubclass(tools.AfluenciaPrevista, RespuestaPrevision))

    def test_deriva_nivel_de_trafico_previsto_y_persistencia(self):
        with patch("asistente.mcp_agent.tools._trafico_prevista_impl", return_value=_tp(valor=2.0)), \
             patch("asistente.mcp_agent.tools._afluencia_estimada_impl", return_value=_est()):
            r = tools.afluencia_prevista("retiro", 3, 300.0, _AHORA)
        self.assertTrue(r.disponible)
        # tráfico 2.0 -> "denso" -> sev 1; ruido 60 dB -> sev 1; bicimad 0.5 -> sev 1
        self.assertAlmostEqual(r.valor_previsto, 1.0)
        self.assertEqual(r.nivel_previsto, "medio")
        self.assertEqual(r.nivel_actual, "alto")
        self.assertEqual(len(r.senales_usadas), 3)
        self.assertEqual(r.momento_objetivo, _ANCLA + timedelta(hours=3))
        self.assertIn("derivada", r.modelo)
        self.assertEqual(r.detalle_trafico_previsto, 2.0)

    def test_solo_trafico_cuando_no_hay_persistencia(self):
        with patch("asistente.mcp_agent.tools._trafico_prevista_impl", return_value=_tp(valor=5.0)), \
             patch("asistente.mcp_agent.tools._afluencia_estimada_impl", return_value=_est(nivel="bajo", con_persistencia=False)):
            r = tools.afluencia_prevista("retiro", 3, 300.0, _AHORA)
        self.assertTrue(r.disponible)
        self.assertEqual(r.senales_usadas, ["trafico(previsto)"])
        # 5.0 -> "congestionado" -> sev 2 -> "alto"
        self.assertEqual(r.nivel_previsto, "alto")

    def test_horizonte_invalido(self):
        with self.assertRaises(ValueError):
            tools.afluencia_prevista("retiro", 4, 300.0, _AHORA)


class DegradacionTests(unittest.TestCase):
    def test_sin_prevision_de_trafico_degrada_pero_da_nivel_actual(self):
        with patch("asistente.mcp_agent.tools._trafico_prevista_impl",
                   return_value=_tp(disponible=False, motivo="ningún punto de tráfico cerca")), \
             patch("asistente.mcp_agent.tools._afluencia_estimada_impl", return_value=_est(nivel="alto")):
            r = tools.afluencia_prevista("retiro", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIsNone(r.valor_previsto)
        self.assertEqual(r.nivel_actual, "alto")
        self.assertIn("sin previsión de tráfico", r.motivo)

    def test_trafico_impl_lanza_se_degrada_sin_excepcion(self):
        with patch("asistente.mcp_agent.tools._trafico_prevista_impl", side_effect=RuntimeError("boom")), \
             patch("asistente.mcp_agent.tools._afluencia_estimada_impl", return_value=_est()):
            r = tools.afluencia_prevista("retiro", 3, 300.0, _AHORA)
        self.assertFalse(r.disponible)
        self.assertIn("previsión de tráfico subyacente", r.motivo)
        self.assertEqual(r.nivel_actual, "alto")

    def test_afluencia_estimada_lanza_no_rompe_la_prevision(self):
        with patch("asistente.mcp_agent.tools._trafico_prevista_impl", return_value=_tp(valor=1.0)), \
             patch("asistente.mcp_agent.tools._afluencia_estimada_impl", side_effect=RuntimeError("neo4j caído")):
            r = tools.afluencia_prevista("retiro", 3, 300.0, _AHORA)
        self.assertTrue(r.disponible)          # el tráfico previsto basta
        self.assertIsNone(r.nivel_actual)
        self.assertEqual(r.senales_usadas, ["trafico(previsto)"])


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_endpoint_construye_respuesta_trazable(self):
        with patch("asistente.mcp_agent.tools._trafico_prevista_impl", return_value=_tp(valor=2.0)), \
             patch("asistente.mcp_agent.tools._afluencia_estimada_impl", return_value=_est()):
            resp = self.client.get(
                "/afluencia-prevista",
                params={"lugar": "retiro", "horizonte_horas": 3, "momento": _AHORA.isoformat()},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn(body["veredicto"], ["favorable", "desfavorable", "con_precaucion"])
        self.assertTrue(body["fuentes"])
        self.assertIn("derivada", body["fuentes"][0]["resumen"])

    def test_endpoint_sin_prevision(self):
        with patch("asistente.mcp_agent.tools._trafico_prevista_impl",
                   return_value=_tp(disponible=False, motivo="nada cerca")), \
             patch("asistente.mcp_agent.tools._afluencia_estimada_impl", return_value=_est(nivel="medio")):
            resp = self.client.get("/afluencia-prevista", params={"lugar": "zzz"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["fiabilidad"], "baja")


if __name__ == "__main__":
    unittest.main()
