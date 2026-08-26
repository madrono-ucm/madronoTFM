"""Tests de las `tools` MCP: firma, docstring, registro, y la lógica real de
`calidad_aire` (tarea 079) y `trafico_cercano` (tarea 081) mockeando
Athena/Neo4j -- mismo criterio que `grafo/tests/test_extract.py`: sin
ninguna llamada ni credencial real, `FakeAthenaClient` responde
`start_query_execution`/`get_query_execution`/`get_query_results` como lo
haría Athena para una consulta ya `SUCCEEDED`, y `FakeNeo4jDriver` responde
`session().run()` como lo haría el driver real para una consulta ya resuelta.
"""

import asyncio
import inspect
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from asistente.mcp_agent import tools
from asistente.mcp_agent.server import mcp

TOOL_FUNCTIONS = [
    tools.afluencia_estimada,
    tools.calidad_aire,
    tools.trafico_cercano,
    tools.opciones_movilidad,
    tools.disponibilidad_aparcamiento,
    tools.eventos_cercanos,
]

# `calidad_aire` (tarea 079), `trafico_cercano` (tarea 081),
# `afluencia_estimada` (tarea 089), `disponibilidad_aparcamiento` (tarea 090)
# y `eventos_cercanos` (tarea 091) son las únicas con lógica real -- solo
# `opciones_movilidad` sigue levantando NotImplementedError.
NOT_IMPLEMENTED_TOOL_FUNCTIONS = [
    tools.opciones_movilidad,
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


_APARCAMIENTOS_COLUMNS = [
    _column("parking_id", "varchar"),
    _column("name", "varchar"),
    _column("hour", "integer"),
    _column("avg_free_spaces", "double"),
    _column("avg_occupancy_ratio", "double"),
    _column("total_spaces", "integer"),
    _column("samples_count", "bigint"),
]


class DisponibilidadAparcamientoToolTests(unittest.TestCase):
    def test_sin_aparcamientos_coincidentes_devuelve_sin_datos_sin_excepcion(self):
        client = FakeAthenaClient(_APARCAMIENTOS_COLUMNS, [])

        resultado = tools._disponibilidad_aparcamiento_impl(
            "Zona Inexistente", datetime(2026, 8, 20, 14, tzinfo=_MADRID), athena_client=client
        )

        self.assertEqual(resultado.aparcamientos_consultados, [])
        self.assertIsNone(resultado.plazas_libres)
        self.assertEqual(resultado.zona, "Zona Inexistente")
        self.assertIn("aparcamientos_por_parking_hora", resultado.fuente_dataset)

    def test_un_aparcamiento_coincidente_devuelve_sus_plazas(self):
        rows = [_row("73", "Plaza de Oriente", "4", "189.0", "0.89", "212", "1")]
        client = FakeAthenaClient(_APARCAMIENTOS_COLUMNS, rows)

        resultado = tools._disponibilidad_aparcamiento_impl(
            "Plaza de Oriente", datetime(2026, 8, 20, 4, tzinfo=_MADRID), athena_client=client
        )

        self.assertEqual(resultado.plazas_libres, 189)
        self.assertEqual(resultado.plazas_totales, 212)
        self.assertEqual(resultado.hora, 4)
        self.assertEqual(resultado.aparcamientos_consultados, ["Plaza de Oriente"])

    def test_varios_aparcamientos_coincidentes_suma_plazas_en_vez_de_tomar_el_peor_caso(self):
        # A diferencia de calidad_aire (peor caso), aquí la capacidad de
        # varios aparcamientos que coinciden con la zona es real y aditiva.
        rows = [
            _row("1", "Chamberí Norte", "10", "50.0", "0.5", "100", "2"),
            _row("2", "Chamberí Sur", "10", "30.0", "0.7", "100", "2"),
        ]
        client = FakeAthenaClient(_APARCAMIENTOS_COLUMNS, rows)

        resultado = tools._disponibilidad_aparcamiento_impl(
            "Chamberí", datetime(2026, 8, 20, 10, tzinfo=_MADRID), athena_client=client
        )

        self.assertEqual(resultado.plazas_libres, 80)
        self.assertEqual(resultado.plazas_totales, 200)
        self.assertEqual(sorted(resultado.aparcamientos_consultados), ["Chamberí Norte", "Chamberí Sur"])

    def test_sin_momento_usa_la_hora_mas_reciente_del_dia(self):
        rows = [
            _row("1", "Retiro", "9", "10.0", "0.9", "100", "1"),
            _row("1", "Retiro", "15", "60.0", "0.4", "100", "1"),
        ]
        client = FakeAthenaClient(_APARCAMIENTOS_COLUMNS, rows)

        resultado = tools._disponibilidad_aparcamiento_impl("Retiro", None, athena_client=client)

        self.assertEqual(resultado.hora, 15)
        self.assertEqual(resultado.plazas_libres, 60)

    def test_avg_free_spaces_nulo_se_excluye_de_la_suma_en_vez_de_contar_como_cero(self):
        rows = [
            _row("1", "Sin Muestras", "10", None, None, "100", "0"),
            _row("2", "Con Muestras", "10", "40.0", "0.6", "100", "2"),
        ]
        client = FakeAthenaClient(_APARCAMIENTOS_COLUMNS, rows)

        resultado = tools._disponibilidad_aparcamiento_impl(
            "a", datetime(2026, 8, 20, 10, tzinfo=_MADRID), athena_client=client
        )

        self.assertEqual(resultado.plazas_libres, 40)
        self.assertEqual(resultado.plazas_totales, 200)

    def test_momento_en_otra_zona_horaria_se_convierte_a_madrid(self):
        rows = [_row("1", "Retiro", "14", "20.0", "0.8", "100", "1")]
        client = FakeAthenaClient(_APARCAMIENTOS_COLUMNS, rows)

        resultado = tools._disponibilidad_aparcamiento_impl(
            "Retiro", datetime(2026, 8, 20, 12, tzinfo=ZoneInfo("UTC")), athena_client=client
        )

        self.assertEqual(resultado.hora, 14)
        self.assertEqual(resultado.plazas_libres, 20)


class FakeNeo4jResult:
    def __init__(self, rows: "list[dict]"):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class FakeNeo4jSession:
    def __init__(self, rows: "list[dict]"):
        self._rows = rows

    def __enter__(self) -> "FakeNeo4jSession":
        return self

    def __exit__(self, *exc_info) -> None:
        return None

    def run(self, query, params):
        return FakeNeo4jResult(self._rows)


class FakeNeo4jDriver:
    """Mismo rol que `FakeAthenaClient` pero para el driver `neo4j`: responde
    `session().run()` con filas ya preparadas, sin ninguna conexión real."""

    def __init__(self, rows: "list[dict]"):
        self._rows = rows

    def session(self, database=None):
        return FakeNeo4jSession(self._rows)


_TRAFICO_COLUMNS = [
    _column("point_id", "varchar"),
    _column("hour", "integer"),
    _column("avg_intensity_vph", "double"),
    _column("avg_occupancy_ratio", "double"),
    _column("avg_load_ratio", "double"),
    _column("avg_intensity_ratio", "double"),
    _column("avg_service_level", "double"),
]


class TraficoCercanoToolTests(unittest.TestCase):
    def test_sin_lugar_coincidente_devuelve_sin_datos_sin_excepcion(self):
        driver = FakeNeo4jDriver([])

        resultado = tools._trafico_cercano_impl(
            "Zona Inexistente", 300.0, datetime(2026, 8, 20, 14, tzinfo=_MADRID), neo4j_driver=driver
        )

        self.assertEqual(resultado.resumen, "sin_datos")
        self.assertEqual(resultado.estaciones, [])
        self.assertEqual(resultado.lugar, "Zona Inexistente")

    def test_una_estacion_cercana_combina_grafo_y_gold(self):
        neo4j_rows = [
            {"lugar_id": "poi:1", "lugar_nombre": "Parque del Retiro", "estacion_id": "trafico:4260", "distancia_m": 120.5}
        ]
        driver = FakeNeo4jDriver(neo4j_rows)
        gold_rows = [_row("4260", "14", "300.0", "0.2", "0.15", "0.3", "1.0")]
        athena = FakeAthenaClient(_TRAFICO_COLUMNS, gold_rows)

        resultado = tools._trafico_cercano_impl(
            "Retiro", 300.0, datetime(2026, 8, 20, 14, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(resultado.resumen, "fluido")
        self.assertEqual(resultado.hora, 14)
        self.assertEqual(len(resultado.estaciones), 1)
        estacion = resultado.estaciones[0]
        self.assertEqual(estacion.point_id, "4260")
        self.assertAlmostEqual(estacion.distancia_m, 120.5)
        self.assertAlmostEqual(estacion.avg_intensity_vph, 300.0)

    def test_varias_estaciones_se_ordenan_por_distancia_y_agregan_el_resumen(self):
        neo4j_rows = [
            {"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "trafico:200", "distancia_m": 250.0},
            {"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "trafico:100", "distancia_m": 50.0},
        ]
        driver = FakeNeo4jDriver(neo4j_rows)
        gold_rows = [
            _row("200", "10", "100.0", "0.1", "0.1", "0.1", "4.0"),
            _row("100", "10", "500.0", "0.7", "0.6", "0.7", "5.0"),
        ]
        athena = FakeAthenaClient(_TRAFICO_COLUMNS, gold_rows)

        resultado = tools._trafico_cercano_impl(
            "Sol", 300.0, datetime(2026, 8, 20, 10, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual([e.point_id for e in resultado.estaciones], ["100", "200"])
        self.assertEqual(resultado.resumen, "congestionado")  # media (5.0+4.0)/2 = 4.5

    def test_estacion_sin_dato_gold_para_la_hora_se_lista_con_valores_none(self):
        neo4j_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "trafico:999", "distancia_m": 80.0}]
        driver = FakeNeo4jDriver(neo4j_rows)
        athena = FakeAthenaClient(_TRAFICO_COLUMNS, [])  # Gold sin filas ese día

        resultado = tools._trafico_cercano_impl(
            "Sol", 300.0, datetime(2026, 8, 20, 10, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(len(resultado.estaciones), 1)
        self.assertEqual(resultado.estaciones[0].point_id, "999")
        self.assertIsNone(resultado.estaciones[0].avg_service_level)
        self.assertEqual(resultado.resumen, "sin_datos")

    def test_fallback_a_occupancy_ratio_cuando_no_hay_service_level(self):
        neo4j_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "trafico:1", "distancia_m": 80.0}]
        driver = FakeNeo4jDriver(neo4j_rows)
        gold_rows = [_row("1", "10", "300.0", "0.8", "0.7", "0.8", None)]
        athena = FakeAthenaClient(_TRAFICO_COLUMNS, gold_rows)

        resultado = tools._trafico_cercano_impl(
            "Sol", 300.0, datetime(2026, 8, 20, 10, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertIsNone(resultado.estaciones[0].avg_service_level)
        self.assertEqual(resultado.resumen, "congestionado")  # occupancy_ratio 0.8 >= 0.6

    def test_sin_momento_usa_la_hora_mas_reciente_del_dia(self):
        neo4j_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "trafico:1", "distancia_m": 80.0}]
        driver = FakeNeo4jDriver(neo4j_rows)
        gold_rows = [
            _row("1", "9", "100.0", "0.1", "0.1", "0.1", "0.5"),
            _row("1", "15", "600.0", "0.9", "0.9", "0.9", "5.5"),
        ]
        athena = FakeAthenaClient(_TRAFICO_COLUMNS, gold_rows)

        resultado = tools._trafico_cercano_impl(
            "Sol", 300.0, None, neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(resultado.hora, 15)
        self.assertAlmostEqual(resultado.estaciones[0].avg_intensity_vph, 600.0)


_AGENDA_EVENTOS_SILVER_COLUMNS = [
    _column("event_id", "varchar"),
    _column("title", "varchar"),
    _column("venue_name", "varchar"),
    _column("lat", "double"),
    _column("lon", "double"),
    _column("start_datetime", "varchar"),
]


class EventosCercanosToolTests(unittest.TestCase):
    def test_sin_lugar_coincidente_devuelve_lista_vacia_sin_excepcion(self):
        driver = FakeNeo4jDriver([])
        athena = FakeAthenaClient(_AGENDA_EVENTOS_SILVER_COLUMNS, [])

        resultado = tools._eventos_cercanos_impl(
            "Zona Inexistente",
            500.0,
            datetime(2026, 8, 20, 14, tzinfo=_MADRID),
            neo4j_driver=driver,
            athena_client=athena,
        )

        self.assertEqual(resultado, [])
        # Sin ningún :Lugar coincidente no hace falta ni consultar Silver.
        self.assertEqual(athena.start_query_execution_calls, [])

    def test_evento_dentro_del_radio_se_incluye(self):
        neo4j_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Retiro", "lat": 40.415, "lon": -3.684}]
        driver = FakeNeo4jDriver(neo4j_rows)
        eventos_rows = [
            _row("ev1", "Concierto en el Retiro", "Auditorio Retiro", "40.415", "-3.684", "2026-08-25T20:00:00+02:00")
        ]
        athena = FakeAthenaClient(_AGENDA_EVENTOS_SILVER_COLUMNS, eventos_rows)

        resultado = tools._eventos_cercanos_impl(
            "Retiro", 500.0, datetime(2026, 8, 20, 14, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0].nombre, "Concierto en el Retiro")
        self.assertEqual(resultado[0].lugar, "Auditorio Retiro")
        self.assertAlmostEqual(resultado[0].distancia_m, 0.0, delta=1.0)
        self.assertIn("silver.agenda_eventos", resultado[0].fuente_dataset)

    def test_evento_fuera_del_radio_se_excluye(self):
        neo4j_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Retiro", "lat": 40.415, "lon": -3.684}]
        driver = FakeNeo4jDriver(neo4j_rows)
        eventos_rows = [
            _row("ev1", "Concierto Lejano", "Otro Sitio", "41.415", "-3.684", "2026-08-25T20:00:00+02:00")
        ]
        athena = FakeAthenaClient(_AGENDA_EVENTOS_SILVER_COLUMNS, eventos_rows)

        resultado = tools._eventos_cercanos_impl(
            "Retiro", 500.0, datetime(2026, 8, 20, 14, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(resultado, [])

    def test_evento_sin_coordenadas_se_excluye_en_vez_de_fallar(self):
        neo4j_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Retiro", "lat": 40.415, "lon": -3.684}]
        driver = FakeNeo4jDriver(neo4j_rows)
        eventos_rows = [_row("ev1", "Sin coordenadas", "?", None, None, "2026-08-25T20:00:00+02:00")]
        athena = FakeAthenaClient(_AGENDA_EVENTOS_SILVER_COLUMNS, eventos_rows)

        resultado = tools._eventos_cercanos_impl(
            "Retiro", 500.0, datetime(2026, 8, 20, 14, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(resultado, [])

    def test_eventos_se_ordenan_por_distancia_ascendente(self):
        neo4j_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Sol", "lat": 40.4169, "lon": -3.7035}]
        driver = FakeNeo4jDriver(neo4j_rows)
        eventos_rows = [
            _row("ev1", "Lejano", "Sitio A", "40.4200", "-3.7035", "2026-08-25T20:00:00+02:00"),
            _row("ev2", "Cercano", "Sitio B", "40.4170", "-3.7035", "2026-08-25T21:00:00+02:00"),
        ]
        athena = FakeAthenaClient(_AGENDA_EVENTOS_SILVER_COLUMNS, eventos_rows)

        resultado = tools._eventos_cercanos_impl(
            "Sol", 500.0, datetime(2026, 8, 20, 14, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual([e.nombre for e in resultado], ["Cercano", "Lejano"])

    def test_varios_lugares_coincidentes_toma_la_distancia_minima_a_cualquiera(self):
        # Dos :Lugar coinciden con "Centro" -- el evento solo tiene que estar
        # cerca de UNO de ellos, no de todos.
        neo4j_rows = [
            {"lugar_id": "poi:1", "lugar_nombre": "Centro Lejano", "lat": 41.0, "lon": -3.7},
            {"lugar_id": "poi:2", "lugar_nombre": "Centro Cercano", "lat": 40.4169, "lon": -3.7035},
        ]
        driver = FakeNeo4jDriver(neo4j_rows)
        eventos_rows = [_row("ev1", "Evento", "Sitio", "40.4169", "-3.7035", "2026-08-25T20:00:00+02:00")]
        athena = FakeAthenaClient(_AGENDA_EVENTOS_SILVER_COLUMNS, eventos_rows)

        resultado = tools._eventos_cercanos_impl(
            "Centro", 500.0, datetime(2026, 8, 20, 14, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(len(resultado), 1)
        self.assertAlmostEqual(resultado[0].distancia_m, 0.0, delta=1.0)

    def test_consulta_silver_acota_por_ventana_de_30_dias_desde_momento(self):
        neo4j_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Retiro", "lat": 40.415, "lon": -3.684}]
        driver = FakeNeo4jDriver(neo4j_rows)
        athena = FakeAthenaClient(_AGENDA_EVENTOS_SILVER_COLUMNS, [])

        tools._eventos_cercanos_impl(
            "Retiro", 500.0, datetime(2026, 8, 20, 14, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(len(athena.start_query_execution_calls), 1)
        sql = athena.start_query_execution_calls[0]["QueryString"]
        self.assertIn("2026-08-20", sql)
        self.assertIn("2026-09-19", sql)  # momento + 30 días

    def test_sin_momento_usa_el_instante_actual(self):
        neo4j_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Retiro", "lat": 40.415, "lon": -3.684}]
        driver = FakeNeo4jDriver(neo4j_rows)
        athena = FakeAthenaClient(_AGENDA_EVENTOS_SILVER_COLUMNS, [])

        resultado = tools._eventos_cercanos_impl(
            "Retiro", 500.0, None, neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(resultado, [])
        self.assertEqual(len(athena.start_query_execution_calls), 1)

    def test_evento_repetido_en_varios_dias_de_ingestion_se_deduplica(self):
        # Silver es un almacén persistente: el mismo event_id recibe una
        # fila nueva cada día de ingestión en que la fuente lo sigue
        # listando (ver docstring de `_eventos_cercanos_impl`) -- bug real
        # encontrado verificando esta tool contra datos reales (mismo
        # event_id repetido en la respuesta).
        neo4j_rows = [{"lugar_id": "poi:1", "lugar_nombre": "Retiro", "lat": 40.415, "lon": -3.684}]
        driver = FakeNeo4jDriver(neo4j_rows)
        eventos_rows = [
            _row("ev1", "Árboles de El Retiro", "CEA Retiro", "40.415", "-3.684", "2026-08-27T19:00:00+02:00"),
            _row("ev1", "Árboles de El Retiro", "CEA Retiro", "40.415", "-3.684", "2026-08-27T19:00:00+02:00"),
            _row("ev1", "Árboles de El Retiro", "CEA Retiro", "40.415", "-3.684", "2026-08-27T19:00:00+02:00"),
        ]
        athena = FakeAthenaClient(_AGENDA_EVENTOS_SILVER_COLUMNS, eventos_rows)

        resultado = tools._eventos_cercanos_impl(
            "Retiro", 500.0, datetime(2026, 8, 20, 14, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(len(resultado), 1)


if __name__ == "__main__":
    unittest.main()
