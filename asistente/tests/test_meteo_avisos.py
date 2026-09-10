"""FIL_82 — `meteo_cercana` + `avisos_meteo`. Sin red (Athena/Neo4j mockeados)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from asistente.mcp_agent import tools


class MeteoCercanaTests(unittest.TestCase):
    def _meteo_rows(self):
        return [
            {"magnitude": "temperature_c", "hour": 14, "avg_value": 31.2, "date": "2026-08-29", "station_name": "Retiro"},
            {"magnitude": "temperature_c", "hour": 13, "avg_value": 30.0, "date": "2026-08-29", "station_name": "Retiro"},
            {"magnitude": "wind_speed_ms", "hour": 14, "avg_value": 2.1, "date": "2026-08-29", "station_name": "Retiro"},
            {"magnitude": "humidity_pct", "hour": 14, "avg_value": None, "date": "2026-08-29", "station_name": "Retiro"},
        ]

    def test_ultima_hora_por_magnitud(self):
        graph = [{"estacion_id": "meteo:3195", "estacion_nombre": "Retiro", "magnitudes": ["temperature_c"], "distancia_m": 210.0}]
        with patch.object(tools, "run_neo4j_query", return_value=graph), \
             patch.object(tools, "run_athena_query", return_value=self._meteo_rows()):
            r = tools.meteo_cercana("Retiro")
        self.assertTrue(r.disponible)
        self.assertEqual(r.estacion_id, "3195")
        mags = {l.magnitud: l for l in r.lecturas}
        self.assertEqual(mags["temperature_c"].valor, 31.2)  # la hora 14, no la 13
        self.assertEqual(mags["temperature_c"].hora, 14)
        self.assertNotIn("humidity_pct", mags)  # avg_value None -> excluida

    def test_sin_estacion_meteo_cerca(self):
        with patch.object(tools, "run_neo4j_query", return_value=[]):
            r = tools.meteo_cercana("Quinta del Berro", 300)
        self.assertFalse(r.disponible)
        self.assertIn("ninguna estación", r.motivo)

    def test_estacion_pero_sin_lecturas(self):
        graph = [{"estacion_id": "meteo:9", "estacion_nombre": "X", "distancia_m": 100.0}]
        with patch.object(tools, "run_neo4j_query", return_value=graph), \
             patch.object(tools, "run_athena_query", return_value=[]):
            r = tools.meteo_cercana("X")
        self.assertFalse(r.disponible)
        self.assertIn("no tiene lecturas", r.motivo)


class AvisosMeteoTests(unittest.TestCase):
    def _rows(self):
        return [
            {"zone": "Madrid capital", "level": "amarillo", "phenomena": "[calor]",
             "first_effective_from": "2026-08-29T10:00", "last_effective_until": "2026-08-29T21:00", "fecha": "2026-08-29"},
            {"zone": "Sierra", "level": "naranja", "phenomena": "[calor, tormentas]",
             "first_effective_from": "2026-08-29T12:00", "last_effective_until": "2026-08-29T20:00", "fecha": "2026-08-29"},
            {"zone": "Madrid capital", "level": "verde", "phenomena": "[]",
             "first_effective_from": "2026-08-27T00:00", "last_effective_until": "2026-08-27T23:59", "fecha": "2026-08-27"},
        ]

    def test_nivel_mas_alto_del_ultimo_dia(self):
        with patch.object(tools, "run_athena_query", return_value=self._rows()):
            r = tools.avisos_meteo()
        self.assertTrue(r.disponible)
        self.assertEqual(r.fecha, "2026-08-29")
        self.assertEqual(r.nivel, "naranja")  # naranja > amarillo
        self.assertEqual(set(r.fenomenos), {"calor", "tormentas"})
        self.assertIn("último día", r.motivo)

    def test_filtro_zona_y_fecha(self):
        with patch.object(tools, "run_athena_query", return_value=self._rows()):
            r = tools.avisos_meteo("capital", "2026-08-27")
        self.assertEqual(r.fecha, "2026-08-27")
        self.assertEqual(r.nivel, "verde")
        self.assertIsNone(r.motivo)

    def test_sin_avisos(self):
        with patch.object(tools, "run_athena_query", return_value=[]):
            r = tools.avisos_meteo("nowhere")
        self.assertFalse(r.disponible)

    def test_rank_niveles(self):
        self.assertLess(tools._NIVEL_AVISO_RANK["amarillo"], tools._NIVEL_AVISO_RANK["rojo"])
        self.assertLess(tools._NIVEL_AVISO_RANK["verde"], tools._NIVEL_AVISO_RANK["naranja"])


if __name__ == "__main__":
    unittest.main()
