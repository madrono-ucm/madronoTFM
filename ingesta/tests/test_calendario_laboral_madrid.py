"""Tests de la carga batch puntual del calendario laboral y festivos de Madrid.

No hacen ninguna llamada de red: usan el fixture
`fixtures/calendario_laboral_madrid_sample.csv`, un extracto de 9 filas
reales del CSV completo descargado en vivo durante esta sesión (no filas
inventadas), elegidas para cubrir laborable/sábado/domingo, los tres ámbitos
de festivo (nacional/regional/local), un traslado regional sin nombre de
festividad, y los dos casos reales de la fuente en los que un día está
marcado como festivo pero `Tipo de Festivo` viene vacío (15/05/2016 y
02/05/2023) — ver el módulo bajo prueba para más detalle sobre estas
inconsistencias de la fuente.

También verifica que la muestra commiteada en
`ingesta/capturas/samples/calendario_laboral_madrid_sample.json` cumple el
esquema esperado.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingesta.capturas.calendario_laboral_madrid import (
    normalize_day_record,
    parse_csv_rows,
    select_year,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CSV_PATH = FIXTURES_DIR / "calendario_laboral_madrid_sample.csv"
SAMPLE_PATH = Path(__file__).parent.parent / "capturas" / "samples" / "calendario_laboral_madrid_sample.json"

INGESTED_AT = datetime(2026, 8, 13, 22, 0, 0, tzinfo=timezone.utc)


def _load_rows() -> list[dict]:
    return parse_csv_rows(CSV_PATH.read_text(encoding="utf-8-sig"))


def _normalize_all() -> list[dict]:
    return [normalize_day_record(row, INGESTED_AT) for row in _load_rows()]


class ParseCsvRowsTests(unittest.TestCase):
    def test_parses_all_fixture_rows(self):
        rows = _load_rows()
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[0]["Dia"], "01/01/2013")
        self.assertEqual(rows[0]["Festividad"], "Año Nuevo")


class NormalizeDayRecordTests(unittest.TestCase):
    def test_normalizes_national_holiday(self):
        records = _normalize_all()
        record = records[0]
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["source"], "madrid_calendario_laboral")
        self.assertEqual(record["date"], "2013-01-01")
        self.assertEqual(record["weekday"], "martes")
        self.assertEqual(record["day_type"], "festivo")
        self.assertTrue(record["is_holiday"])
        self.assertEqual(record["holiday_type"], "nacional")
        self.assertEqual(record["holiday_type_raw"], "Festivo nacional")
        self.assertEqual(record["holiday_name"], "Año Nuevo")
        self.assertEqual(record["ingested_at"], "2026-08-14T00:00:00+02:00")

    def test_normalizes_working_day_without_holiday_fields(self):
        record = _normalize_all()[1]
        self.assertEqual(record["date"], "2013-01-02")
        self.assertEqual(record["day_type"], "laborable")
        self.assertFalse(record["is_holiday"])
        self.assertIsNone(record["holiday_type"])
        self.assertIsNone(record["holiday_type_raw"])
        self.assertIsNone(record["holiday_name"])

    def test_normalizes_saturday_and_sunday_day_types(self):
        records = _normalize_all()
        self.assertEqual(records[2]["day_type"], "sabado")
        self.assertFalse(records[2]["is_holiday"])
        self.assertEqual(records[3]["day_type"], "domingo")
        self.assertFalse(records[3]["is_holiday"])

    def test_normalizes_regional_and_local_holidays(self):
        records = _normalize_all()
        regional = records[4]
        self.assertEqual(regional["holiday_type"], "regional")
        self.assertEqual(regional["holiday_type_raw"], "Festivo de la Comunidad de Madrid")
        self.assertEqual(regional["holiday_name"], "Traslado de la festividad de San José")

        local = records[5]
        self.assertEqual(local["holiday_type"], "local")
        self.assertEqual(local["holiday_type_raw"], "Festivo local de la ciudad de Madrid")
        self.assertEqual(local["holiday_name"], "San Isidro Labrador")

    def test_normalizes_regional_transfer_without_holiday_name(self):
        record = _normalize_all()[6]
        self.assertEqual(record["date"], "2021-05-03")
        self.assertTrue(record["is_holiday"])
        self.assertEqual(record["holiday_type"], "regional")
        self.assertEqual(record["holiday_type_raw"], "Traslado de la fiesta de la Comunidad de Madrid")
        self.assertIsNone(record["holiday_name"])

    def test_handles_source_rows_missing_holiday_type(self):
        # Dos inconsistencias reales de la fuente: el día está marcado
        # "festivo" pero "Tipo de Festivo" viene vacío. No se infiere ningún
        # valor: holiday_type/holiday_type_raw quedan a None.
        records = _normalize_all()
        without_name = records[7]
        self.assertEqual(without_name["date"], "2016-05-15")
        self.assertTrue(without_name["is_holiday"])
        self.assertIsNone(without_name["holiday_type"])
        self.assertIsNone(without_name["holiday_type_raw"])
        self.assertIsNone(without_name["holiday_name"])

        with_name = records[8]
        self.assertEqual(with_name["date"], "2023-05-02")
        self.assertTrue(with_name["is_holiday"])
        self.assertIsNone(with_name["holiday_type"])
        self.assertIsNone(with_name["holiday_type_raw"])
        self.assertEqual(with_name["holiday_name"], "Dos de Mayo. Fiesta de la Comunidad de Madrid")


class SelectYearTests(unittest.TestCase):
    def test_filters_records_to_the_requested_year(self):
        records = _normalize_all()
        selected = select_year(records, 2013)
        self.assertEqual(len(selected), 6)
        self.assertTrue(all(r["date"].startswith("2013-") for r in selected))

    def test_defaults_to_the_most_recent_year_present(self):
        records = _normalize_all()
        selected = select_year(records, None)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["date"], "2023-05-02")

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(select_year([], 2013), [])


class CommittedSampleTests(unittest.TestCase):
    EXPECTED_KEYS = {
        "schema_version",
        "source",
        "date",
        "weekday",
        "day_type",
        "is_holiday",
        "holiday_type",
        "holiday_type_raw",
        "holiday_name",
        "ingested_at",
    }
    VALID_DAY_TYPES = {"laborable", "festivo", "sabado", "domingo"}
    VALID_HOLIDAY_TYPES = {"nacional", "regional", "local"}

    def test_sample_matches_schema_and_is_a_single_full_year(self):
        records = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(records), 365)

        years = {r["date"][:4] for r in records}
        self.assertEqual(years, {"2026"})

        dates = sorted(r["date"] for r in records)
        self.assertEqual(dates[0], "2026-01-01")
        self.assertEqual(dates[-1], "2026-12-31")
        self.assertEqual(len(set(dates)), 365)

        holiday_count = 0
        for record in records:
            self.assertEqual(set(record.keys()), self.EXPECTED_KEYS)
            self.assertEqual(record["source"], "madrid_calendario_laboral")
            self.assertIn(record["day_type"], self.VALID_DAY_TYPES)
            self.assertEqual(record["is_holiday"], record["day_type"] == "festivo")
            if record["holiday_type"] is not None:
                self.assertIn(record["holiday_type"], self.VALID_HOLIDAY_TYPES)
                self.assertTrue(record["is_holiday"])
            if record["is_holiday"]:
                holiday_count += 1

        # 2026 real: 14 festivos conocidos en el momento de esta captura
        # (incluye el Jueves Santo y su traslado, ver el docstring del
        # módulo para la lista completa).
        self.assertEqual(holiday_count, 14)


if __name__ == "__main__":
    unittest.main()
