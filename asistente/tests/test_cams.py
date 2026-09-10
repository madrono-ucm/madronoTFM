"""FIL_80 — `calidad_aire_cams` + contraste `referencia_cams` en la previsión.

Sin red: `run_athena_query` mockeado.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from asistente.mcp_agent import tools


def _row(pollutant, fecha, avg, mx, lt="[1, 3, 6]"):
    return {
        "pollutant": pollutant, "pollutant_code": pollutant.upper(), "unit": "µg/m³",
        "fecha_validez": fecha, "avg_value": avg, "max_value": mx,
        "leadtime_hours": lt, "last_forecast_issued_at": "2026-08-29T00:00:00Z",
    }


class CamsTests(unittest.TestCase):
    def test_ultima_fecha_sin_fecha_explicita(self):
        filas = [_row("no2", "2026-08-28", 30.0, 45.0), _row("no2", "2026-08-30", 22.0, 40.0)]
        with patch.object(tools, "run_athena_query", return_value=filas):
            r = tools.calidad_aire_cams("NO2")
        self.assertTrue(r.disponible)
        self.assertEqual(r.fecha_validez, "2026-08-30")  # la más reciente
        self.assertEqual(r.avg_ugm3, 22.0)
        self.assertEqual(r.leadtime_horas, [1, 3, 6])
        self.assertEqual(r.n_fechas_disponibles, 2)
        self.assertIn("pausado", r.motivo)

    def test_fecha_explicita(self):
        filas = [_row("no2", "2026-08-28", 30.0, 45.0), _row("no2", "2026-08-30", 22.0, 40.0)]
        with patch.object(tools, "run_athena_query", return_value=filas):
            r = tools.calidad_aire_cams("no2", "2026-08-28")
        self.assertEqual(r.fecha_validez, "2026-08-28")
        self.assertEqual(r.avg_ugm3, 30.0)
        self.assertIsNone(r.motivo)

    def test_sin_datos_degrada(self):
        with patch.object(tools, "run_athena_query", return_value=[]):
            r = tools.calidad_aire_cams("ozono")
        self.assertFalse(r.disponible)
        self.assertIn("no tiene previsión", r.motivo)

    def test_normaliza_contaminante(self):
        self.assertEqual(tools._cams_token("O₃"), "o3")
        self.assertEqual(tools._cams_token("ozono"), "o3")
        self.assertEqual(tools._cams_token("PM2.5"), "pm2")

    def test_leadtime_ya_lista(self):
        filas = [_row("o3", "2026-08-30", 60.0, 90.0, lt=[1, 6])]
        with patch.object(tools, "run_athena_query", return_value=filas):
            r = tools.calidad_aire_cams("O3", "2026-08-30")
        self.assertEqual(r.leadtime_horas, [1, 6])


if __name__ == "__main__":
    unittest.main()
