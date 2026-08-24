"""Tests de las `tools` MCP: firma, docstring, registro, y (tarea 079) la
lógica real de `calidad_aire` mockeando Athena -- mismo criterio que
`grafo/tests/test_extract.py`: sin ninguna llamada ni credencial real,
`FakeAthenaClient` responde `start_query_execution`/`get_query_execution`/
`get_query_results` como lo haría Athena para una consulta ya `SUCCEEDED`.
"""

import asyncio
import inspect
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from asistente.mcp_agent import tools
from asistente.mcp_agent.server import mcp

TOOL_FUNCTIONS = [
    tools.afluencia_prevista,
    tools.calidad_aire,
    tools.opciones_movilidad,
    tools.disponibilidad_aparcamiento,
    tools.eventos_cercanos,
]

# `calidad_aire` es la única con lógica real (tarea 079) -- el resto siguen
# levantando NotImplementedError.
NOT_IMPLEMENTED_TOOL_FUNCTIONS = [
    tools.afluencia_prevista,
    tools.opciones_movilidad,
    tools.disponibilidad_aparcamiento,
    tools.eventos_cercanos,
]


class ToolSignatureTests(unittest.TestCase):
    def test_every_tool_has_a_docstring(self):
        for fn in TOOL_FUNCTIONS:
            with self.subTest(tool=fn.__name__):
                self.assertTrue(fn.__doc__ and fn.__doc__.strip())

    def test_every_tool_parameter_and_return_is_typed(self):
        for fn in TOOL_FUNCTIONS:
            with self.subTest(tool=fn.__name__):
                sig = inspect.signature(fn)
                self.assertIsNot(sig.return_annotation, inspect.Signature.empty)
                for name, param in sig.parameters.items():
                    self.assertIsNot(param.annotation, inspect.Signature.empty, name)

    def test_remaining_tools_raise_not_implemented(self):
        for fn in NOT_IMPLEMENTED_TOOL_FUNCTIONS:
            with self.subTest(tool=fn.__name__):
                sig = inspect.signature(fn)
                kwargs = {
                    name: "x"
                    for name, param in sig.parameters.items()
                    if param.default is inspect.Parameter.empty
                }
                with self.assertRaises(NotImplementedError):
                    fn(**kwargs)


class MCPServerRegistrationTests(unittest.TestCase):
    def test_all_tools_are_registered_on_the_mcp_server(self):
        registered = asyncio.run(mcp.list_tools())
        names = {tool.name for tool in registered}
        expected = {fn.__name__ for fn in TOOL_FUNCTIONS}
        self.assertEqual(expected, names)


def _column(name: str, athena_type: str) -> dict:
    return {"Name": name, "Type": athena_type}


def _row(*values) -> dict:
    return {"Data": [({"VarCharValue": v} if v is not None else {}) for v in values]}


class FakeAthenaClient:
    def __init__(self, columns: "list[dict]", data_rows: "list[dict]", final_state: str = "SUCCEEDED"):
        self.columns = columns
        self.data_rows = data_rows
        self.final_state = final_state
        self.start_query_execution_calls: "list[dict]" = []

    def start_query_execution(self, QueryString, QueryExecutionContext, WorkGroup):
        self.start_query_execution_calls.append(
            {"QueryString": QueryString, "QueryExecutionContext": QueryExecutionContext, "WorkGroup": WorkGroup}
        )
        return {"QueryExecutionId": "fake-execution-id"}

    def get_query_execution(self, QueryExecutionId):
        return {"QueryExecution": {"Status": {"State": self.final_state}}}

    def get_query_results(self, QueryExecutionId, NextToken=None):
        header = _row(*[c["Name"] for c in self.columns])
        return {
            "ResultSet": {
                "ResultSetMetadata": {"ColumnInfo": self.columns},
                "Rows": [header] + self.data_rows,
            }
        }


_COLUMNS = [
    _column("station_id", "varchar"),
    _column("station_name", "varchar"),
    _column("pollutant", "varchar"),
    _column("pollutant_name", "varchar"),
    _column("unit", "varchar"),
    _column("hour", "integer"),
    _column("avg_value", "double"),
    _column("max_value", "double"),
    _column("min_value", "double"),
    _column("samples_count", "bigint"),
]

_MADRID = ZoneInfo("Europe/Madrid")


class CalidadAireToolTests(unittest.TestCase):
    def test_sin_estaciones_coincidentes_devuelve_sin_datos_sin_excepcion(self):
        client = FakeAthenaClient(_COLUMNS, [])

        resultado = tools._calidad_aire_impl(
            "Zona Inexistente",
            datetime(2026, 8, 20, 14, tzinfo=_MADRID),
            athena_client=client,
        )

        self.assertEqual(resultado.indice_calidad, "sin_datos")
        self.assertIsNone(resultado.contaminante_principal)
        self.assertEqual(resultado.zona, "Zona Inexistente")
        self.assertIn("calidad_aire_por_estacion_contaminante_hora", resultado.fuente_dataset)

    def test_una_estacion_coincidente_calcula_indice_y_contaminante_principal(self):
        rows = [
            _row("28079008", "Ramón y Cajal", "NO2", "Dióxido de Nitrógeno", "µg/m³", "14", "45.5", "60.0", "30.0", "4"),
            _row("28079008", "Ramón y Cajal", "O3", "Ozono", "µg/m³", "14", "20.0", "30.0", "10.0", "4"),
        ]
        client = FakeAthenaClient(_COLUMNS, rows)

        resultado = tools._calidad_aire_impl(
            "Ramón y Cajal",
            datetime(2026, 8, 20, 14, tzinfo=_MADRID),
            athena_client=client,
        )

        self.assertEqual(resultado.contaminante_principal, "NO2")
        self.assertAlmostEqual(resultado.valor, 45.5)
        self.assertEqual(resultado.unidad, "µg/m³")
        self.assertEqual(resultado.hora, 14)
        self.assertEqual(resultado.estaciones_consultadas, ["Ramón y Cajal"])
        self.assertEqual(resultado.indice_calidad, "buena")  # 45.5 / 200 (límite NO2) = 0.2275 < 0.5

    def test_varias_estaciones_coincidentes_toma_el_peor_avg_value_por_contaminante(self):
        rows = [
            _row("1", "Plaza del Carmen A", "NO2", "Dióxido de Nitrógeno", "µg/m³", "10", "50.0", "70.0", "40.0", "4"),
            _row("2", "Plaza del Carmen B", "NO2", "Dióxido de Nitrógeno", "µg/m³", "10", "120.0", "140.0", "100.0", "4"),
        ]
        client = FakeAthenaClient(_COLUMNS, rows)

        resultado = tools._calidad_aire_impl(
            "Plaza del Carmen",
            datetime(2026, 8, 20, 10, tzinfo=_MADRID),
            athena_client=client,
        )

        self.assertEqual(resultado.valor, 120.0)
        self.assertEqual(sorted(resultado.estaciones_consultadas), ["Plaza del Carmen A", "Plaza del Carmen B"])

    def test_sin_momento_usa_la_hora_mas_reciente_del_dia(self):
        rows = [
            _row("1", "Retiro", "NO2", "Dióxido de Nitrógeno", "µg/m³", "9", "30.0", "40.0", "20.0", "4"),
            _row("1", "Retiro", "NO2", "Dióxido de Nitrógeno", "µg/m³", "15", "80.0", "90.0", "70.0", "4"),
        ]
        client = FakeAthenaClient(_COLUMNS, rows)

        resultado = tools._calidad_aire_impl("Retiro", None, athena_client=client)

        self.assertEqual(resultado.hora, 15)
        self.assertEqual(resultado.valor, 80.0)

    def test_contaminante_sin_limite_de_referencia_usa_sin_clasificar(self):
        columns = _COLUMNS
        rows = [_row("1", "Retiro", "TOL", "Tolueno", "µg/m³", "10", "5.0", "6.0", "4.0", "4")]
        client = FakeAthenaClient(columns, rows)

        resultado = tools._calidad_aire_impl(
            "Retiro", datetime(2026, 8, 20, 10, tzinfo=_MADRID), athena_client=client
        )

        self.assertEqual(resultado.contaminante_principal, "TOL")
        self.assertEqual(resultado.indice_calidad, "sin_clasificar")

    def test_avg_value_nulo_se_descarta_en_vez_de_devolver_valor_none(self):
        # samples_count=0 (sin ninguna muestra válida) -> avg_value=None en
        # Gold (ver procesamiento/silver_gold/calidad_aire/aggregate.py). No
        # debe convertirse en el "peor caso" ni dejar `valor=None` de cara al
        # router (que formatea `resultado.valor` con `:.1f`).
        rows = [_row("1", "Retiro", "NO2", "Dióxido de Nitrógeno", "µg/m³", "10", None, None, None, "0")]
        client = FakeAthenaClient(_COLUMNS, rows)

        resultado = tools._calidad_aire_impl(
            "Retiro", datetime(2026, 8, 20, 10, tzinfo=_MADRID), athena_client=client
        )

        self.assertEqual(resultado.indice_calidad, "sin_datos")
        self.assertIsNone(resultado.valor)

    def test_momento_en_otra_zona_horaria_se_convierte_a_madrid(self):
        # Gold agrupa `hour` en hora de Madrid (ver aggregate.py). Un
        # `momento` en UTC a las 12:00 es 14:00 en Madrid en agosto (CEST,
        # UTC+2) -- debe filtrar por la hora 14, no por la 12.
        rows = [_row("1", "Retiro", "NO2", "Dióxido de Nitrógeno", "µg/m³", "14", "40.0", "50.0", "30.0", "4")]
        client = FakeAthenaClient(_COLUMNS, rows)

        resultado = tools._calidad_aire_impl(
            "Retiro", datetime(2026, 8, 20, 12, tzinfo=ZoneInfo("UTC")), athena_client=client
        )

        self.assertEqual(resultado.hora, 14)
        self.assertEqual(resultado.valor, 40.0)


if __name__ == "__main__":
    unittest.main()
