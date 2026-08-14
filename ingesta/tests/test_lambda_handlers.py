"""Tests de los `lambda_handler` añadidos en la tarea 026 (lote 1/3: tráfico,
transporte público EMT, BiciMAD, aparcamientos, calidad del aire).

Cada handler delega la captura real en una función ya existente y probada
por su propio módulo (`capture_once`/`capture_all`); estos tests no repiten
esa cobertura. Se centran en el código nuevo de esta tarea: que el handler
llama a la función de captura completa correcta, que escribe el resultado
en Bronze (`BronzeWriter`, en modo local con un directorio temporal — sin
red ni S3 reales) con el nombre de dataset esperado, y que el `dict` de
retorno es coherente. Por eso cada test sustituye la función de captura de
más alto nivel por un doble en memoria, en vez de mockear peticiones HTTP:
la lógica de red/parseo ya está cubierta en `test_<modulo>.py`.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ingesta.capturas import (
    aparcamientos_madrid,
    bicimad,
    calidad_aire_madrid,
    trafico_madrid,
    transporte_publico_madrid,
)


class TraficoLambdaHandlerTests(unittest.TestCase):
    def test_writes_full_capture_to_bronze(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ", {"BRONZE_BASE_PATH": tmp}
        ), patch.object(trafico_madrid, "capture_once") as mock_capture:
            mock_capture.return_value = Path(tmp) / "trafico" / "fecha=2026-01-01" / "hora=00" / "x.json"
            result = trafico_madrid.lambda_handler({}, None)
        mock_capture.assert_called_once()
        self.assertEqual(result["dataset"], "trafico")


def _run_handler_writing_records(module, handler_kwargs_patch_target, records):
    """Ejecuta `module.lambda_handler` con `patch_target` devolviendo `records`,
    apuntando `BRONZE_BASE_PATH` a un directorio temporal. Devuelve (result, written, mock_fn)."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict("os.environ", {"BRONZE_BASE_PATH": tmp}):
            with patch.object(module, handler_kwargs_patch_target) as mock_fn:
                mock_fn.return_value = records
                result = module.lambda_handler({}, None)
        out_path = Path(result["location"])
        written = json.loads(out_path.read_text(encoding="utf-8"))
        return result, written, mock_fn


class TransportePublicoLambdaHandlerTests(unittest.TestCase):
    def test_writes_full_capture_to_bronze(self):
        records = [{"stop_id": "71", "line": "1"}]
        result, written, mock_fn = _run_handler_writing_records(
            transporte_publico_madrid, "capture_all", records
        )
        mock_fn.assert_called_once()
        self.assertEqual(result["dataset"], "transporte_publico_emt")
        self.assertEqual(result["records_written"], 1)
        self.assertEqual(written, records)


class BicimadLambdaHandlerTests(unittest.TestCase):
    def test_writes_full_capture_to_bronze(self):
        records = [{"station_id": "1"}, {"station_id": "2"}]
        result, written, mock_fn = _run_handler_writing_records(bicimad, "capture_all", records)
        mock_fn.assert_called_once()
        self.assertEqual(result["dataset"], "bicimad")
        self.assertEqual(written, records)


class AparcamientosLambdaHandlerTests(unittest.TestCase):
    def test_writes_full_capture_to_bronze(self):
        records = [{"parking_id": "1"}]
        result, written, mock_fn = _run_handler_writing_records(
            aparcamientos_madrid, "capture_all", records
        )
        mock_fn.assert_called_once()
        self.assertEqual(result["dataset"], "aparcamientos")
        self.assertEqual(written, records)


class CalidadAireLambdaHandlerTests(unittest.TestCase):
    def test_writes_full_capture_to_bronze(self):
        records = [{"station_id": "28079011"}]
        result, written, mock_fn = _run_handler_writing_records(
            calidad_aire_madrid, "capture_all", records
        )
        mock_fn.assert_called_once()
        self.assertEqual(result["dataset"], "calidad_aire")
        self.assertEqual(written, records)


if __name__ == "__main__":
    unittest.main()
