import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from modelado.features import build


class CargarFestivosTests(unittest.TestCase):
    def test_muestra_real_solo_dias_festivos(self):
        festivos = build._cargar_festivos(build._DEFAULT_FESTIVOS)
        # La muestra commiteada es el año 2026 entero (365 registros); solo
        # deben salir los ~14 festivos, no todo el calendario.
        self.assertLess(len(festivos), 20)
        self.assertIn(date(2026, 8, 15), festivos)   # Asunción (dentro de la ventana de datos)
        self.assertIn(date(2026, 1, 1), festivos)
        self.assertNotIn(date(2026, 8, 16), festivos)  # domingo normal

    def test_tolera_is_holiday_string_y_day_type(self):
        self.assertTrue(build._es_festivo({"is_holiday": "true"}))
        self.assertTrue(build._es_festivo({"day_type": "festivo"}))
        self.assertFalse(build._es_festivo({"is_holiday": False}))
        self.assertFalse(build._es_festivo({"day_type": "laborable"}))

    def test_formato_envuelto_en_dias(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        f = Path(td.name) / "cal.json"
        f.write_text(json.dumps({"dias": [
            {"fecha": "2026-03-19", "is_holiday": True},
            {"fecha": "2026-03-20", "is_holiday": False},
        ]}), encoding="utf-8")
        self.assertEqual(build._cargar_festivos(f), {date(2026, 3, 19)})

    def test_fichero_ausente_no_rompe(self):
        self.assertEqual(build._cargar_festivos(Path("no", "existe.json")), set())
        self.assertEqual(build._cargar_festivos(None), set())


if __name__ == "__main__":
    unittest.main()
