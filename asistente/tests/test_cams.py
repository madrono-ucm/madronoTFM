"""FIL_80 — `calidad_aire_cams` + contraste `referencia_cams` en la previsión.

Sin red: `run_athena_query` mockeado.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
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


def _aire_mock(instante: datetime, n=25):
    """Filas de `calidad_aire_por_estacion_contaminante_hora` (NO tiene la
    forma de una fila CAMS: sin `fecha_validez`/`max_value`/`leadtime_hours`).
    """
    base = instante.replace(minute=0, second=0, microsecond=0)
    return [
        {
            "station_id": "28079008", "station_name": "Ramón y Cajal",
            "pollutant": "NO2", "unit": "µg/m³",
            "date": (base - timedelta(hours=k)).date().isoformat(),
            "hour": (base - timedelta(hours=k)).hour,
            "avg_value": 40.0 + k * 0.5, "lat": 40.45, "lon": -3.68,
        }
        for k in range(n)
    ]


class ContrasteCamsEnPrevistaTests(unittest.TestCase):
    """VIC_40: `_calidad_aire_prevista_impl` invoca `calidad_aire_cams`
    internamente vía `run_athena_query` sin pasar `athena_client` — el
    `athena_client is None` que guarda ese bloque (comentado como "solo en
    producción, no en los tests con Athena mockeada") no se activa nunca en
    la práctica, porque ningún test llama a `_calidad_aire_prevista_impl`
    directamente con un `athena_client` real: todos mockean `run_athena_query`
    a nivel de módulo (patrón usado en todo el repo), que sigue dejando
    `athena_client=None`. Antes de este ticket, eso significaba que
    `test_calidad_aire_prevista.py`/`test_mcp_hardening.py` ejecutaban de
    verdad el bloque de contraste CAMS contra filas de aire (forma distinta a
    una fila CAMS), produciendo un `referencia_cams`/`delta_vs_cams` sin
    sentido de forma silenciosa (verificado: `referencia_cams=40.0`, la propia
    lectura de NO2 más reciente, no un valor de CAMS). Estos tests aíslan el
    contraste mockeando `calidad_aire_cams` directamente, el punto correcto
    de inyección."""

    def test_delta_con_signo_correcto(self):
        ahora = datetime(2026, 8, 17, 10)
        cams_fake = tools.CalidadAireCams(
            contaminante="NO2", disponible=True, fecha_validez="2026-08-17",
            avg_ugm3=35.0, unidad="µg/m³",
        )
        with patch.object(tools, "run_athena_query", return_value=_aire_mock(ahora)), \
             patch.object(tools, "calidad_aire_cams", return_value=cams_fake):
            r = tools.calidad_aire_prevista("cajal", 6, ahora)
        self.assertIsNotNone(r.valor_previsto)
        self.assertEqual(r.referencia_cams, 35.0)
        # delta = modelo_propio - CAMS (asistente/models/herramientas.py:246)
        self.assertAlmostEqual(r.delta_vs_cams, round(r.valor_previsto - 35.0, 1))

    def test_cams_no_disponible_no_rompe_ni_inventa_valor(self):
        ahora = datetime(2026, 8, 17, 10)
        cams_fake = tools.CalidadAireCams(contaminante="NO2", disponible=False, motivo="sin datos CAMS")
        with patch.object(tools, "run_athena_query", return_value=_aire_mock(ahora)), \
             patch.object(tools, "calidad_aire_cams", return_value=cams_fake):
            r = tools.calidad_aire_prevista("cajal", 6, ahora)
        self.assertTrue(r.disponible)  # la previsión propia no depende de CAMS
        self.assertIsNone(r.referencia_cams)
        self.assertIsNone(r.delta_vs_cams)

    def test_veredicto_no_depende_de_cams(self):
        """El mismo `valor_previsto`/`nivel_previsto` con CAMS disponible o
        no -- `referencia_cams` es contexto, nunca cambia el veredicto."""
        ahora = datetime(2026, 8, 17, 10)
        cams_disponible = tools.CalidadAireCams(
            contaminante="NO2", disponible=True, fecha_validez="2026-08-17", avg_ugm3=999.0,
        )
        cams_no_disponible = tools.CalidadAireCams(contaminante="NO2", disponible=False, motivo="x")
        with patch.object(tools, "run_athena_query", return_value=_aire_mock(ahora)), \
             patch.object(tools, "calidad_aire_cams", return_value=cams_disponible):
            r1 = tools.calidad_aire_prevista("cajal", 6, ahora)
        with patch.object(tools, "run_athena_query", return_value=_aire_mock(ahora)), \
             patch.object(tools, "calidad_aire_cams", return_value=cams_no_disponible):
            r2 = tools.calidad_aire_prevista("cajal", 6, ahora)
        self.assertEqual(r1.valor_previsto, r2.valor_previsto)
        self.assertEqual(r1.nivel_previsto, r2.nivel_previsto)
        self.assertNotEqual(r1.referencia_cams, r2.referencia_cams)  # sí cambia el contexto


if __name__ == "__main__":
    unittest.main()
