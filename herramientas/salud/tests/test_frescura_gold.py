"""Tests de `herramientas.salud.frescura_gold` (`FIL_16`).

Mockea `run_athena_query` (sin credenciales ni red) devolviendo la marca
temporal por tabla; el foco es la clasificación fresca / estancada /
descontinuada y la semántica de código de salida con el pipeline congelado.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from herramientas.salud import frescura_gold as fg

_AHORA = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def _fake_marcas(por_tabla: "dict[str, str | None]", defecto: "str | None"):
    """Devuelve un stub de `run_athena_query` que lee el nombre de tabla del
    SQL (`FROM "<tabla>"`) y responde su marca."""

    def _stub(sql, database, *, athena_client=None):
        tabla = sql.split('FROM "', 1)[1].split('"', 1)[0]
        valor = por_tabla.get(tabla, defecto)
        return [{"marca": valor}]

    return _stub


class ParseMarcaTests(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(
            fg._parse_marca("2026-08-29"),
            datetime(2026, 8, 29, tzinfo=timezone.utc),
        )
        self.assertEqual(
            fg._parse_marca("2026-08-29T10:15:00Z").hour, 10
        )
        self.assertEqual(fg._parse_marca("2026-08-29T09:00:00+02:00").hour, 7)
        self.assertIsNone(fg._parse_marca(None))
        self.assertIsNone(fg._parse_marca("no-es-fecha"))


class EvaluarTablaTests(unittest.TestCase):
    def test_horaria_reciente_es_fresca(self):
        with patch.object(fg, "run_athena_query", _fake_marcas({}, "2026-08-30")):
            r = fg.evaluar_tabla("trafico_por_punto_hora", fg.HORARIA, "date", _AHORA)
        self.assertEqual(r["estado"], "fresca")
        self.assertFalse(r["alerta_en_produccion"])

    def test_horaria_vieja_es_estancada_y_alertaria(self):
        with patch.object(fg, "run_athena_query", _fake_marcas({}, "2026-08-25")):
            r = fg.evaluar_tabla("trafico_por_punto_hora", fg.HORARIA, "date", _AHORA)
        self.assertEqual(r["estado"], "estancada")
        self.assertTrue(r["alerta_en_produccion"])
        self.assertGreater(r["edad_horas"], fg.UMBRAL_HORAS[fg.HORARIA])

    def test_sin_datos(self):
        with patch.object(fg, "run_athena_query", _fake_marcas({}, None)):
            r = fg.evaluar_tabla("ruido_por_estacion_periodo_fecha", fg.DIARIA, "date", _AHORA)
        self.assertEqual(r["estado"], "sin_datos")
        self.assertTrue(r["alerta_en_produccion"])

    def test_descontinuada_vieja_es_ok(self):
        with patch.object(fg, "run_athena_query", _fake_marcas({}, "2024-06-29")):
            r = fg.evaluar_tabla(
                "aforos_peatones_bicicletas_por_estacion_modo_hora", fg.DESCONTINUADA, "date", _AHORA
            )
        self.assertEqual(r["estado"], "descontinuada_ok")
        self.assertFalse(r["alerta_en_produccion"])

    def test_descontinuada_con_datos_nuevos_es_anomalo(self):
        with patch.object(fg, "run_athena_query", _fake_marcas({}, "2026-08-30")):
            r = fg.evaluar_tabla(
                "aforos_peatones_bicicletas_por_estacion_modo_hora", fg.DESCONTINUADA, "date", _AHORA
            )
        self.assertEqual(r["estado"], "descontinuada_con_datos_nuevos")
        self.assertTrue(r["alerta_en_produccion"])


class BuildReportTests(unittest.TestCase):
    def test_ordena_alertas_primero_y_cuenta(self):
        marcas = {t: "2026-08-30" for t in fg.TABLAS}
        marcas["trafico_por_punto_hora"] = "2026-08-01"  # estancada
        marcas["aforos_peatones_bicicletas_por_estacion_modo_hora"] = "2024-06-29"  # ok
        with patch.object(fg, "run_athena_query", _fake_marcas(marcas, "2026-08-30")):
            rep = fg.build_report(ahora=_AHORA)
        self.assertEqual(rep["tablas"][0]["tabla"], "trafico_por_punto_hora")
        self.assertEqual(rep["n_alertarian_en_produccion"], 1)
        self.assertIn("trafico_por_punto_hora", fg.format_table(rep))


def _report(n_alertas: int, con_descontinuada_anomala: bool = False) -> dict:
    tablas = [
        {"tabla": f"t{i}", "cadencia": fg.HORARIA, "marca": "2026-08-01",
         "edad_horas": 700.0, "umbral_horas": 30.0, "estado": "estancada",
         "alerta_en_produccion": True}
        for i in range(n_alertas)
    ]
    if con_descontinuada_anomala:
        tablas.append({
            "tabla": "aforos", "cadencia": fg.DESCONTINUADA, "marca": "2026-08-30",
            "edad_horas": 0.0, "umbral_horas": None,
            "estado": "descontinuada_con_datos_nuevos", "alerta_en_produccion": True,
        })
    return {
        "generado_en": _AHORA.isoformat(), "tablas": tablas,
        "n_alertarian_en_produccion": len(tablas),
    }


class MainExitCodeTests(unittest.TestCase):
    def test_congelado_todo_estancado_exit_0_y_avisa(self):
        with patch.object(fg, "build_report", return_value=_report(8)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = fg.main(["--pipeline-congelado"])
        self.assertEqual(rc, 0)
        self.assertIn("pipeline congelado", buf.getvalue())

    def test_produccion_con_estancada_exit_1(self):
        with patch.object(fg, "build_report", return_value=_report(3)):
            with redirect_stdout(io.StringIO()):
                rc = fg.main([])
        self.assertEqual(rc, 1)

    def test_produccion_todo_fresco_exit_0(self):
        with patch.object(fg, "build_report", return_value=_report(0)):
            with redirect_stdout(io.StringIO()):
                rc = fg.main([])
        self.assertEqual(rc, 0)

    def test_congelado_pero_descontinuada_con_datos_exit_1(self):
        with patch.object(fg, "build_report", return_value=_report(2, con_descontinuada_anomala=True)):
            with redirect_stdout(io.StringIO()):
                rc = fg.main(["--pipeline-congelado", "--formato", "json"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
