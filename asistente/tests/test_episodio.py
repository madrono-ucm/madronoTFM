"""FIL_79 — `calidad_aire_episodio`: probabilidad de superar el umbral OMS/UE.

Sin red: se mockea `_calidad_aire_prevista_impl` para no tocar Athena.
"""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from asistente.mcp_agent import tools
from asistente.models.herramientas import CalidadAirePrevista


def _prev(valor, *, contaminante="NO2", disponible=True, motivo=None):
    return CalidadAirePrevista(
        zona="Retiro", momento=datetime(2026, 8, 30, 12, 0),
        momento_objetivo=datetime(2026, 8, 30, 18, 0), horizonte_horas=6,
        disponible=disponible, estacion="Retiro", contaminante=contaminante,
        valor_previsto=valor, valor_actual=(valor - 5) if valor else None,
        unidad="µg/m³", nivel_previsto="regular", data_completeness=0.9,
        modelo="calidad_aire_h6.onnx", fuente_dataset="gold.calidad_aire", motivo=motivo,
    )


class ProbSuperacionTests(unittest.TestCase):
    def test_logistica_monotona_y_acotada(self):
        u = 40.0
        ps = [tools._prob_superacion(y, u) for y in range(0, 120, 5)]
        self.assertTrue(all(0.0 < p < 1.0 for p in ps))
        self.assertEqual(ps, sorted(ps), "P debe crecer con ŷ")
        self.assertAlmostEqual(tools._prob_superacion(u, u), 0.5, places=6)

    def test_por_debajo_y_por_encima(self):
        u = 40.0
        self.assertLess(tools._prob_superacion(20.0, u), 0.5)
        self.assertGreater(tools._prob_superacion(70.0, u), 0.5)


class EpisodioTests(unittest.TestCase):
    def test_supera_umbral(self):
        with patch.object(tools, "_calidad_aire_prevista_impl", return_value=_prev(260.0)):
            r = tools.calidad_aire_episodio("Retiro", 6)
        self.assertTrue(r.disponible)
        self.assertEqual(r.veredicto, "supera")
        self.assertEqual(r.umbral, 200.0)  # límite horario UE de NO2
        self.assertGreater(r.prob_superacion, 0.5)
        self.assertEqual(r.margen, 60.0)

    def test_no_supera_umbral(self):
        with patch.object(tools, "_calidad_aire_prevista_impl", return_value=_prev(120.0)):
            r = tools.calidad_aire_episodio("Retiro", 3)
        self.assertTrue(r.disponible)
        self.assertEqual(r.veredicto, "no supera")
        self.assertLess(r.prob_superacion, 0.5)

    def test_sin_prevision_degrada(self):
        with patch.object(
            tools, "_calidad_aire_prevista_impl",
            return_value=_prev(None, disponible=False, motivo="ninguna estación coincide"),
        ):
            r = tools.calidad_aire_episodio("Nowhere", 6)
        self.assertFalse(r.disponible)
        self.assertEqual(r.veredicto, "sin_datos")
        self.assertIn("ninguna estación", r.motivo)
        self.assertIsNone(r.prob_superacion)

    def test_contaminante_sin_umbral(self):
        with patch.object(tools, "_calidad_aire_prevista_impl", return_value=_prev(5.0, contaminante="C6H6")):
            r = tools.calidad_aire_episodio("Retiro", 6)
        # C6H6 (benceno) no está en _LIMITES_REFERENCIA_UGM3 -> sin_datos, pero con valor_previsto
        self.assertFalse(r.disponible)
        self.assertEqual(r.veredicto, "sin_datos")
        self.assertEqual(r.valor_previsto, 5.0)


if __name__ == "__main__":
    unittest.main()
