"""FIL_83/VIC_43 -- la caché no cambia el contrato: una `tool` real debe
devolver exactamente la misma respuesta con `ASSISTANT_CACHE_TTL` activada
o desactivada. Sin esto, un TTL mal aplicado podría enmascarar un bug (dos
llamadas iguales que en realidad deberían dar resultados distintos) sin que
ningún test lo note.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from asistente.athena import run_athena_query
from asistente.mcp_agent import tools

_MADRID = ZoneInfo("Europe/Madrid")

_COLUMNS = [
    {"Name": "station_id", "Type": "varchar"},
    {"Name": "station_name", "Type": "varchar"},
    {"Name": "pollutant", "Type": "varchar"},
    {"Name": "pollutant_name", "Type": "varchar"},
    {"Name": "unit", "Type": "varchar"},
    {"Name": "hour", "Type": "integer"},
    {"Name": "avg_value", "Type": "double"},
    {"Name": "max_value", "Type": "double"},
    {"Name": "min_value", "Type": "double"},
    {"Name": "samples_count", "Type": "bigint"},
]


def _row(*values) -> dict:
    return {"Data": [({"VarCharValue": v} if v is not None else {}) for v in values]}


class FakeAthenaClient:
    def __init__(self, columns, data_rows):
        self.columns = columns
        self.data_rows = data_rows

    def start_query_execution(self, QueryString, QueryExecutionContext, WorkGroup):
        return {"QueryExecutionId": "fake-execution-id"}

    def get_query_execution(self, QueryExecutionId):
        return {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}

    def get_query_results(self, QueryExecutionId, NextToken=None):
        header = _row(*[c["Name"] for c in self.columns])
        return {
            "ResultSet": {
                "ResultSetMetadata": {"ColumnInfo": self.columns},
                "Rows": [header] + self.data_rows,
            }
        }


class ParidadCacheTests(unittest.TestCase):
    def setUp(self):
        # partir de una caché limpia -- el resto de la suite nunca activa
        # ASSISTANT_CACHE_TTL para las funciones reales, pero no lo demos
        # por hecho.
        run_athena_query.cache_clear()

    def tearDown(self):
        run_athena_query.cache_clear()

    def _consultar(self):
        rows = [
            _row("28079008", "Escuelas Aguirre", "no2", "Dióxido de nitrógeno", "µg/m³", 10, "42.5", "50.1", "35.0", "1"),
        ]
        client = FakeAthenaClient(_COLUMNS, rows)
        momento = datetime(2026, 8, 20, 10, tzinfo=_MADRID)
        return tools._calidad_aire_impl("Escuelas Aguirre", momento, athena_client=client)

    def test_misma_respuesta_con_cache_desactivada_y_activada(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ASSISTANT_CACHE_TTL", None)
            resultado_sin_cache = self._consultar()

        with patch.dict(os.environ, {"ASSISTANT_CACHE_TTL": "900"}):
            resultado_con_cache_miss = self._consultar()
            resultado_con_cache_hit = self._consultar()  # 2a llamada, mismo proceso -> hit

        self.assertEqual(resultado_sin_cache, resultado_con_cache_miss)
        self.assertEqual(resultado_sin_cache, resultado_con_cache_hit)


if __name__ == "__main__":
    unittest.main()
