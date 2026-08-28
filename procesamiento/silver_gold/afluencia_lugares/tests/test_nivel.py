import unittest

from procesamiento.silver_gold.afluencia_lugares.nivel import SIN_DATOS, clasificar, nivel_estimado


class ClasificarTests(unittest.TestCase):
    def test_bandas_ruido(self):
        self.assertEqual(clasificar(40.0, ((55.0, "bajo"), (70.0, "medio"))), "bajo")
        self.assertEqual(clasificar(60.0, ((55.0, "bajo"), (70.0, "medio"))), "medio")
        self.assertEqual(clasificar(80.0, ((55.0, "bajo"), (70.0, "medio"))), "alto")


class NivelEstimadoTests(unittest.TestCase):
    def test_sin_ninguna_senal(self):
        self.assertEqual(nivel_estimado(), SIN_DATOS)
        self.assertEqual(nivel_estimado(service_levels=[], noise_dbs=[None]), SIN_DATOS)

    def test_todo_bajo(self):
        self.assertEqual(
            nivel_estimado(service_levels=[1.0], noise_dbs=[45.0], bicimad_occupancies=[0.1]),
            "bajo",
        )

    def test_todo_alto(self):
        self.assertEqual(
            nivel_estimado(service_levels=[4.0], noise_dbs=[75.0], bicimad_occupancies=[0.9]),
            "alto",
        )

    def test_mezcla_da_medio(self):
        # severidades 0 (tráfico fluido) + 2 (ruido alto) -> media 1.0 -> "medio"
        self.assertEqual(nivel_estimado(service_levels=[1.0], noise_dbs=[75.0]), "medio")

    def test_fallback_occupancy_cuando_no_hay_service_level(self):
        self.assertEqual(nivel_estimado(traffic_occupancies=[0.7]), "alto")
        # con service_levels presente, se ignora occupancy
        self.assertEqual(
            nivel_estimado(service_levels=[1.0], traffic_occupancies=[0.9]), "bajo"
        )

    def test_promedia_varias_estaciones_de_la_misma_senal(self):
        self.assertEqual(nivel_estimado(noise_dbs=[40.0, 50.0]), "bajo")
        self.assertEqual(nivel_estimado(noise_dbs=[40.0, 90.0]), "medio")  # media 65 -> "medio"


if __name__ == "__main__":
    unittest.main()
