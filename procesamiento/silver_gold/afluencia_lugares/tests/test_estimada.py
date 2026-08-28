import unittest
from datetime import datetime

from procesamiento.silver_gold.afluencia_lugares.estimada import (
    fila_gold,
    sensores_por_tipo,
)

_PA = datetime(2026, 8, 28, 15, 0, 0)


class SensoresPorTipoTests(unittest.TestCase):
    def test_agrupa_y_quita_prefijo_fuente(self):
        filas = [
            {"id": "trafico:PM001", "tipo": "trafico", "distancia_m": 50.0},
            {"id": "trafico:PM001", "tipo": "trafico", "distancia_m": 30.0},  # más cerca -> gana
            {"id": "bicimad:12", "tipo": "bicimad", "distancia_m": 80.0},
            {"id": "ruido:R7", "tipo": "ruido", "distancia_m": None},  # sin dist -> fuera
            {"id": "sin_prefijo", "tipo": "trafico", "distancia_m": 5.0},  # sin ":" -> fuera
        ]
        out = sensores_por_tipo(filas)
        self.assertEqual(out["trafico"], {"PM001": 30.0})
        self.assertEqual(out["bicimad"], {"12": 80.0})
        self.assertEqual(out["ruido"], {})
        self.assertEqual(out["calidad_aire"], {})


class FilaGoldTests(unittest.TestCase):
    def _fila(self, sensores, valores_gold):
        return fila_gold(
            lugar={"id": "parques_jardines:5", "tipo": "parque", "lat": 40.4, "lon": -3.7},
            sensores=sensores,
            valores_gold=valores_gold,
            fecha="2026-08-28",
            hora=15,
            processed_at=_PA,
        )

    def test_sin_ningun_sensor(self):
        f = self._fila({"trafico": {}, "ruido": {}, "calidad_aire": {}, "bicimad": {}}, {})
        self.assertEqual(f["nivel_estimado"], "sin_datos")
        self.assertEqual(f["data_completeness"], 0)
        self.assertEqual(f["lugar_id"], "parques_jardines:5")
        self.assertIsNone(f["avg_laeq_db"])

    def test_combina_trafico_y_ruido(self):
        sensores = {
            "trafico": {"PM001": 40.0},
            "ruido": {"R1": 60.0},
            "calidad_aire": {},
            "bicimad": {},
        }
        valores = {
            "trafico": {"PM001": {"avg_service_level": 4.0}},  # denso/alto
            "ruido": {"R1": {"avg_laeq_db": 45.0}},  # bajo
        }
        f = self._fila(sensores, valores)
        # severidad tráfico 2 (alto) + ruido 0 -> media 1.0 -> "medio"
        self.assertEqual(f["nivel_estimado"], "medio")
        self.assertEqual(f["n_trafico"], 1)
        self.assertEqual(f["n_ruido"], 1)
        self.assertEqual(f["data_completeness"], 2)
        self.assertAlmostEqual(f["avg_service_level"], 4.0)
        self.assertAlmostEqual(f["avg_laeq_db"], 45.0)

    def test_sensor_cercano_pero_sin_valor_gold_no_cuenta(self):
        sensores = {"trafico": {"PM001": 40.0}, "ruido": {}, "calidad_aire": {}, "bicimad": {}}
        f = self._fila(sensores, {"trafico": {}})  # PM001 sin fila Gold
        self.assertEqual(f["n_trafico"], 0)
        self.assertEqual(f["data_completeness"], 0)
        self.assertEqual(f["nivel_estimado"], "sin_datos")

    def test_fallback_a_occupancy_cuando_no_hay_service_level(self):
        sensores = {"trafico": {"PM001": 10.0}, "ruido": {}, "calidad_aire": {}, "bicimad": {}}
        valores = {"trafico": {"PM001": {"avg_occupancy_ratio": 0.7}}}  # alto
        f = self._fila(sensores, valores)
        self.assertEqual(f["nivel_estimado"], "alto")
        self.assertEqual(f["n_trafico"], 1)


if __name__ == "__main__":
    unittest.main()
