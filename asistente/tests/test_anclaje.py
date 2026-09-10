"""FIL_84 — anclaje temporal del asistente (`ASSISTANT_ANCHOR_DATE`).

Sin la env, `ahora_o_ancla()` es `now_madrid()` (comportamiento de siempre).
Con la env, las tools sin `momento` explícito apuntan a un día con datos
reales (la ingesta está congelada desde 2026-08-30).
"""

from __future__ import annotations

import os
import unittest
from datetime import date
from unittest.mock import patch

from asistente import timeutils as tu


class AnclajeTests(unittest.TestCase):
    def test_sin_env_es_ahora(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ASSISTANT_ANCHOR_DATE", None)
            self.assertIsNone(tu.fecha_ancla())
            self.assertEqual(
                tu.ahora_o_ancla().date(), tu.now_madrid().date()
            )

    def test_con_env_ancla_a_esa_fecha_conservando_hora(self):
        with patch.dict(os.environ, {"ASSISTANT_ANCHOR_DATE": "2026-08-26"}):
            self.assertEqual(tu.fecha_ancla(), date(2026, 8, 26))
            a = tu.ahora_o_ancla()
            self.assertEqual((a.year, a.month, a.day), (2026, 8, 26))
            # la hora-del-día sigue siendo la del reloj real
            self.assertEqual(a.hour, tu.now_madrid().hour)
            self.assertEqual(str(a.tzinfo), "Europe/Madrid")

    def test_env_invalida_se_ignora(self):
        with patch.dict(os.environ, {"ASSISTANT_ANCHOR_DATE": "ayer"}):
            self.assertIsNone(tu.fecha_ancla())
            self.assertEqual(tu.ahora_o_ancla().date(), tu.now_madrid().date())

    def test_dia_curado_mas_cercano(self):
        self.assertEqual(tu.dia_curado_mas_cercano("2026-08-20"), "2026-08-19")
        self.assertEqual(tu.dia_curado_mas_cercano("2026-08-24"), "2026-08-23")
        self.assertEqual(tu.dia_curado_mas_cercano(date(2026, 9, 10)), "2026-08-26")

    def test_dias_curados_coinciden_con_el_mapa(self):
        # el mismo trío que viz/build_mapa_animado.py y grafo_ruta.json
        self.assertEqual(tu.DIAS_CURADOS, ("2026-08-19", "2026-08-23", "2026-08-26"))


class ToolsUsanElAnclajeTests(unittest.TestCase):
    def test_calidad_aire_consulta_la_fecha_anclada(self):
        """Con el ancla puesta y sin `momento`, la SQL de `calidad_aire`
        pide la fecha anclada (no la de hoy)."""
        from asistente.mcp_agent import tools

        capt = {}

        def _fake_query(sql, *a, **kw):
            capt["sql"] = sql
            return []

        with patch.dict(os.environ, {"ASSISTANT_ANCHOR_DATE": "2026-08-26"}), \
             patch.object(tools, "run_athena_query", _fake_query):
            tools.calidad_aire("Retiro")
        self.assertIn("2026-08-26", capt["sql"])
        self.assertNotIn(str(tu.now_madrid().date()), capt["sql"])


if __name__ == "__main__":
    unittest.main()
