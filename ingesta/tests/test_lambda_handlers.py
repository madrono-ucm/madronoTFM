"""Tests de los `lambda_handler` añadidos en la tarea 026.

Cada handler delega la captura real en una función ya existente y probada
por su propio módulo (`capture_all`, `fetch_forecast`, `sweep_premieres`...);
estos tests no repiten esa cobertura. Se centran en el código nuevo de esta
tarea: que el handler llama a la función de captura completa correcta, que
escribe el resultado en Bronze (`BronzeWriter`, en modo local con un
directorio temporal — sin red ni S3 reales) con el nombre de dataset
esperado, y que el `dict` de retorno es coherente. Por eso cada test
sustituye la función de captura de más alto nivel por un doble en memoria,
en vez de mockear peticiones HTTP: la lógica de red/parseo ya está cubierta
en `test_<modulo>.py`.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ingesta.capturas import (
    aemet_prevision_avisos,
    afluencia_lugares_madrid,
    aforos_peatones_bicicletas_madrid,
    agenda_eventos_madrid,
    aparcamientos_madrid,
    bicimad,
    bluesky_menciones_madrid,
    calidad_aire_madrid,
    cams_calidad_aire_madrid,
    cartelera_cines_madrid,
    meteorologia_madrid,
    ruido_madrid,
    trafico_madrid,
    transporte_publico_madrid,
)


class TraficoLambdaHandlerTests(unittest.TestCase):
    def test_writes_full_capture_to_bronze(self):
        records = [{"point_id": "1"}, {"point_id": "2"}]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ", {"BRONZE_BASE_PATH": tmp}
        ), patch.object(trafico_madrid, "capture_once") as mock_capture:
            mock_capture.return_value = Path(tmp) / "trafico" / "fecha=2026-01-01" / "hora=00" / "x.json"
            result = trafico_madrid.lambda_handler({}, None)
        mock_capture.assert_called_once()
        self.assertEqual(result["dataset"], "trafico")


def _run_handler_writing_records(module, handler_kwargs_patch_target, records, dataset_attr="DATASET_NAME"):
    """Ejecuta `module.lambda_handler` con `patch_target` devolviendo `records`,
    apuntando `BRONZE_BASE_PATH` a un directorio temporal. Devuelve (result, out_path)."""
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


class MeteorologiaLambdaHandlerTests(unittest.TestCase):
    def test_writes_full_capture_to_bronze(self):
        records = [{"station_id": "28079102"}]
        result, written, mock_fn = _run_handler_writing_records(
            meteorologia_madrid, "capture_all", records
        )
        mock_fn.assert_called_once()
        self.assertEqual(result["dataset"], "meteorologia")
        self.assertEqual(written, records)


class RuidoLambdaHandlerTests(unittest.TestCase):
    def test_writes_full_capture_to_bronze(self):
        records = [{"station_id": "RF-01", "period": "D"}]
        result, written, mock_fn = _run_handler_writing_records(ruido_madrid, "capture_all", records)
        mock_fn.assert_called_once()
        self.assertEqual(result["dataset"], "ruido")
        self.assertEqual(written, records)


class AfluenciaLugaresLambdaHandlerTests(unittest.TestCase):
    def test_writes_typical_pattern_only_to_bronze(self):
        records = [{"query": "Puerta del Sol, Madrid", "live_pct": None, "typical_by_hour": {}}]
        result, written, mock_fn = _run_handler_writing_records(
            afluencia_lugares_madrid, "capture_typical_patterns", records
        )
        mock_fn.assert_called_once()
        self.assertEqual(result["dataset"], "afluencia_lugares_patron_tipico")
        self.assertEqual(written, records)

    def test_normalize_record_forces_live_pct_none_when_include_live_false(self):
        from datetime import datetime, timezone

        raw = {
            "id": "abc",
            "name": "Puerta del Sol",
            "coordinates": {"lat": 40.4, "lng": -3.7},
            "current_popularity": 87,
            "populartimes": [],
        }
        record = afluencia_lugares_madrid.normalize_record(
            raw, "Puerta del Sol, Madrid", datetime.now(timezone.utc), include_live=False
        )
        self.assertIsNone(record["live_pct"])


class AforosLambdaHandlerTests(unittest.TestCase):
    def test_checks_for_newer_resources_without_failing_and_captures(self):
        records = [{"station_id": "PERM_PEA01", "mode": "peatones"}]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"BRONZE_BASE_PATH": tmp}):
                with patch.object(
                    aforos_peatones_bicicletas_madrid, "check_for_newer_resources"
                ) as mock_check, patch.object(
                    aforos_peatones_bicicletas_madrid, "capture_all"
                ) as mock_capture:
                    mock_capture.return_value = records
                    result = aforos_peatones_bicicletas_madrid.lambda_handler({}, None)
        mock_check.assert_called_once()
        mock_capture.assert_called_once()
        self.assertEqual(result["dataset"], "aforos_peatones_bicicletas")

    def test_check_for_newer_resources_logs_warning_instead_of_raising_on_network_failure(self):
        import requests

        config = aforos_peatones_bicicletas_madrid.CaptureConfig.from_env()
        with patch.object(
            aforos_peatones_bicicletas_madrid.requests,
            "get",
            side_effect=requests.RequestException("boom"),
        ):
            aforos_peatones_bicicletas_madrid.check_for_newer_resources(config)  # no debe lanzar


class BlueskyLambdaHandlerTests(unittest.TestCase):
    def test_uses_full_district_and_event_term_lists(self):
        records = [{"mode": "distrito_sweep", "match_term": "Centro"}]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"BRONZE_BASE_PATH": tmp}):
                with patch.object(bluesky_menciones_madrid, "search_district_sweep") as mock_sweep:
                    mock_sweep.return_value = records
                    result = bluesky_menciones_madrid.lambda_handler({}, None)
        mock_sweep.assert_called_once()
        call_args = mock_sweep.call_args
        districts_arg = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("districts")
        self.assertEqual(districts_arg, bluesky_menciones_madrid.DEFAULT_DISTRICTS)
        self.assertEqual(call_args.kwargs.get("event_terms"), bluesky_menciones_madrid.DEFAULT_EVENT_TERMS)
        self.assertEqual(result["dataset"], "bluesky_menciones")


class AgendaEventosLambdaHandlerTests(unittest.TestCase):
    def test_writes_full_capture_to_bronze(self):
        records = [{"source": "agenda_eventos_madrid_municipal"}, {"source": "agenda_turismo_esmadrid"}]
        result, written, mock_fn = _run_handler_writing_records(
            agenda_eventos_madrid, "capture_all", records
        )
        mock_fn.assert_called_once()
        self.assertEqual(result["dataset"], "agenda_eventos")
        self.assertEqual(written, records)


class AemetLambdaHandlerTests(unittest.TestCase):
    def _run(self, event, patch_target):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"BRONZE_BASE_PATH": tmp, "AEMET_API_KEY": "fake-key"}):
                with patch.object(aemet_prevision_avisos, patch_target) as mock_fn:
                    mock_fn.return_value = [{"dummy": True}]
                    result = aemet_prevision_avisos.lambda_handler(event, None)
        return result, mock_fn

    def test_default_tipo_captures_prediccion(self):
        result, mock_fn = self._run({}, "fetch_prediccion")
        mock_fn.assert_called_once()
        self.assertEqual(result["dataset"], "aemet_prevision")

    def test_tipo_avisos_captures_avisos(self):
        result, mock_fn = self._run({"tipo": "avisos"}, "fetch_avisos")
        mock_fn.assert_called_once()
        self.assertEqual(result["dataset"], "aemet_avisos")

    def test_unknown_tipo_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"BRONZE_BASE_PATH": tmp, "AEMET_API_KEY": "fake-key"}):
                with self.assertRaises(ValueError):
                    aemet_prevision_avisos.lambda_handler({"tipo": "algo-raro"}, None)

    def test_missing_api_key_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"BRONZE_BASE_PATH": tmp, "AEMET_API_KEY": ""}):
                with self.assertRaises(RuntimeError):
                    aemet_prevision_avisos.lambda_handler({}, None)


class CamsLambdaHandlerTests(unittest.TestCase):
    def test_writes_full_capture_to_bronze(self):
        records = [{"pollutant": "NO2"}]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                "os.environ", {"BRONZE_BASE_PATH": tmp, "CAMS_ADS_API_KEY": "fake-token"}
            ):
                with patch.object(cams_calidad_aire_madrid, "fetch_forecast") as mock_fn:
                    mock_fn.return_value = records
                    result = cams_calidad_aire_madrid.lambda_handler({}, None)
        mock_fn.assert_called_once()
        self.assertEqual(result["dataset"], "cams_calidad_aire")

    def test_missing_api_key_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"BRONZE_BASE_PATH": tmp, "CAMS_ADS_API_KEY": ""}):
                with self.assertRaises(RuntimeError):
                    cams_calidad_aire_madrid.lambda_handler({}, None)


class CarteleraLambdaHandlerTests(unittest.TestCase):
    def test_uses_sweep_premieres_without_limit(self):
        records = [{"record_type": "estreno_semana"}]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"BRONZE_BASE_PATH": tmp}):
                with patch.object(cartelera_cines_madrid, "sweep_premieres") as mock_fn:
                    mock_fn.return_value = records
                    result = cartelera_cines_madrid.lambda_handler({}, None)
        mock_fn.assert_called_once()
        _, kwargs = mock_fn.call_args
        self.assertNotIn("limit", kwargs)
        self.assertEqual(result["dataset"], "cartelera_cines_estrenos")


if __name__ == "__main__":
    unittest.main()
