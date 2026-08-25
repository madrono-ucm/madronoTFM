"""Tests de la tool `afluencia_estimada` (tarea 089) -- mockea Neo4j/Athena,
sin ninguna llamada ni credencial real.

A diferencia de `calidad_aire`/`trafico_cercano` (una sola consulta a cada
sistema), `afluencia_estimada` hace **cuatro** consultas Neo4j y hasta
**cuatro** consultas Athena (una por señal: tráfico/ruido/BiciMAD/calidad
del aire) -- los fakes de `test_mcp_tools.py` (`FakeNeo4jDriver`,
`FakeAthenaClient`) devuelven siempre las mismas filas sin mirar la
consulta, insuficiente aquí. `_RoutingNeo4jDriver`/`_RoutingAthenaClient`
enrutan por el `tipo`/nombre de tabla presente en la consulta real."""

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from asistente.mcp_agent import tools

_MADRID = ZoneInfo("Europe/Madrid")


def _column(name: str, athena_type: str) -> dict:
    return {"Name": name, "Type": athena_type}


def _row(*values) -> dict:
    return {"Data": [({"VarCharValue": v} if v is not None else {}) for v in values]}


class _RoutingNeo4jResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _RoutingNeo4jSession:
    def __init__(self, driver):
        self._driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def run(self, query, params):
        for tipo, rows in self._driver.rows_by_tipo.items():
            if f"tipo: '{tipo}'" in query:
                return _RoutingNeo4jResult(rows)
        return _RoutingNeo4jResult([])


class _RoutingNeo4jDriver:
    """`rows_by_tipo`: `{"trafico": [...], "ruido": [...], "bicimad": [...],
    "calidad_aire": [...]}` -- solo hace falta rellenar las señales que el
    test necesite, el resto devuelve `[]` (equivalente a "sin nodos cerca")."""

    def __init__(self, rows_by_tipo: dict):
        self.rows_by_tipo = rows_by_tipo

    def session(self, database=None):
        return _RoutingNeo4jSession(self)


class _RoutingAthenaClient:
    """`rows_by_tabla`: `{"trafico_por_punto_hora": (columns, rows), ...}` --
    enruta por el nombre de tabla (`FROM <tabla>`) presente en el SQL real."""

    def __init__(self, rows_by_tabla: dict):
        self.rows_by_tabla = rows_by_tabla

    def start_query_execution(self, QueryString, QueryExecutionContext, WorkGroup):
        for tabla in self.rows_by_tabla:
            if f"FROM {tabla}" in QueryString:
                return {"QueryExecutionId": f"fake-{tabla}"}
        return {"QueryExecutionId": "fake-empty"}

    def get_query_execution(self, QueryExecutionId):
        return {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}

    def get_query_results(self, QueryExecutionId, NextToken=None):
        tabla = QueryExecutionId.replace("fake-", "", 1)
        columns, rows = self.rows_by_tabla.get(tabla, ([], []))
        header = _row(*[c["Name"] for c in columns])
        return {"ResultSet": {"ResultSetMetadata": {"ColumnInfo": columns}, "Rows": [header] + rows}}


_TRAFICO_COLUMNS = [
    _column("point_id", "varchar"),
    _column("hour", "integer"),
    _column("avg_intensity_vph", "double"),
    _column("avg_occupancy_ratio", "double"),
    _column("avg_service_level", "double"),
]
_RUIDO_COLUMNS = [
    _column("station_id", "varchar"),
    _column("period", "varchar"),
    _column("avg_laeq_db", "double"),
]
_BICIMAD_COLUMNS = [
    _column("station_id", "varchar"),
    _column("hour", "integer"),
    _column("avg_bikes_available", "double"),
    _column("avg_docks_available", "double"),
    _column("avg_occupancy_ratio", "double"),
]
_CALIDAD_AIRE_COLUMNS = [
    _column("station_id", "varchar"),
    _column("pollutant", "varchar"),
    _column("hour", "integer"),
    _column("avg_value", "double"),
]


class AfluenciaEstimadaSinDatosTests(unittest.TestCase):
    def test_sin_ningun_nodo_cercano_devuelve_sin_datos_sin_excepcion(self):
        driver = _RoutingNeo4jDriver({})
        athena = _RoutingAthenaClient({})

        resultado = tools._afluencia_estimada_impl(
            "Lugar Inexistente", 300.0, datetime(2026, 8, 20, 14, tzinfo=_MADRID),
            neo4j_driver=driver, athena_client=athena,
        )

        self.assertEqual(resultado.nivel_estimado, "sin_datos")
        self.assertEqual(resultado.trafico, [])
        self.assertEqual(resultado.ruido, [])
        self.assertEqual(resultado.bicimad, [])
        self.assertEqual(resultado.calidad_aire, [])
        self.assertEqual(resultado.fuentes_gold, [])


class AfluenciaEstimadaSoloTraficoTests(unittest.TestCase):
    def test_solo_senal_trafico_disponible_calcula_nivel_con_lo_que_hay(self):
        driver = _RoutingNeo4jDriver({
            "trafico": [{"lugar_id": "poi:1", "lugar_nombre": "Retiro", "estacion_id": "trafico:4260", "distancia_m": 120.0}],
        })
        athena = _RoutingAthenaClient({
            "trafico_por_punto_hora": (_TRAFICO_COLUMNS, [_row("4260", "14", "300.0", "0.2", "1.0")]),
        })

        resultado = tools._afluencia_estimada_impl(
            "Retiro", 300.0, datetime(2026, 8, 20, 14, tzinfo=_MADRID),
            neo4j_driver=driver, athena_client=athena,
        )

        self.assertEqual(len(resultado.trafico), 1)
        self.assertEqual(resultado.trafico[0].point_id, "4260")
        self.assertEqual(resultado.nivel_estimado, "bajo")  # avg_service_level 1.0 -> "fluido" -> severidad 0
        self.assertEqual(resultado.fuentes_gold, ["gold.trafico_por_punto_hora"])
        self.assertEqual(resultado.ruido, [])


class AfluenciaEstimadaCombinadaTests(unittest.TestCase):
    def test_combina_trafico_ruido_y_bicimad_en_nivel_estimado(self):
        driver = _RoutingNeo4jDriver({
            "trafico": [{"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "trafico:100", "distancia_m": 50.0}],
            "ruido": [{"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "ruido:RF-01", "distancia_m": 80.0}],
            "bicimad": [{"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "bicimad:200", "distancia_m": 40.0}],
        })
        athena = _RoutingAthenaClient({
            "trafico_por_punto_hora": (_TRAFICO_COLUMNS, [_row("100", "10", "500.0", "0.7", "5.0")]),  # congestionado -> severidad 2
            "ruido_por_estacion_periodo_fecha": (_RUIDO_COLUMNS, [_row("RF-01", "D", "50.0")]),  # bajo -> severidad 0
            "bicimad_por_estacion_hora": (_BICIMAD_COLUMNS, [_row("200", "10", "3.0", "12.0", "0.2")]),  # bajo -> severidad 0
        })

        resultado = tools._afluencia_estimada_impl(
            "Sol", 300.0, datetime(2026, 8, 20, 10, tzinfo=_MADRID),
            neo4j_driver=driver, athena_client=athena,
        )

        self.assertEqual(len(resultado.trafico), 1)
        self.assertEqual(len(resultado.ruido), 1)
        self.assertEqual(len(resultado.bicimad), 1)
        self.assertEqual(resultado.ruido[0].avg_laeq_db, 50.0)
        self.assertEqual(resultado.bicimad[0].avg_occupancy_ratio, 0.2)
        # severidades: trafico=2, ruido=0, bicimad=0 -> media 0.666 -> "bajo"
        self.assertEqual(resultado.nivel_estimado, "bajo")
        self.assertEqual(
            sorted(resultado.fuentes_gold),
            sorted(["gold.trafico_por_punto_hora", "gold.ruido_por_estacion_periodo_fecha", "gold.bicimad_por_estacion_hora"]),
        )

    def test_calidad_aire_no_contribuye_a_nivel_estimado(self):
        driver = _RoutingNeo4jDriver({
            "trafico": [{"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "trafico:100", "distancia_m": 50.0}],
            "calidad_aire": [{"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "calidad_aire:28079008", "distancia_m": 90.0}],
        })
        athena = _RoutingAthenaClient({
            "trafico_por_punto_hora": (_TRAFICO_COLUMNS, [_row("100", "10", "100.0", "0.1", "1.0")]),  # fluido
            "calidad_aire_por_estacion_contaminante_hora": (
                _CALIDAD_AIRE_COLUMNS, [_row("28079008", "NO2", "10", "999.0")],  # valor extremo, no debe mover nivel_estimado
            ),
        })

        resultado = tools._afluencia_estimada_impl(
            "Sol", 300.0, datetime(2026, 8, 20, 10, tzinfo=_MADRID),
            neo4j_driver=driver, athena_client=athena,
        )

        self.assertEqual(len(resultado.calidad_aire), 1)
        self.assertEqual(resultado.calidad_aire[0].contaminante_principal, "NO2")
        self.assertEqual(resultado.calidad_aire[0].valor, 999.0)
        # Solo tráfico (fluido -> severidad 0) contribuye a nivel_estimado.
        self.assertEqual(resultado.nivel_estimado, "bajo")


class AfluenciaEstimadaSinDatoGoldTests(unittest.TestCase):
    def test_nodo_cercano_sin_fila_gold_se_lista_con_valores_none(self):
        driver = _RoutingNeo4jDriver({
            "ruido": [{"lugar_id": "poi:1", "lugar_nombre": "Sol", "estacion_id": "ruido:RF-99", "distancia_m": 70.0}],
        })
        athena = _RoutingAthenaClient({})  # Gold sin filas ese día

        resultado = tools._afluencia_estimada_impl(
            "Sol", 300.0, datetime(2026, 8, 20, 10, tzinfo=_MADRID),
            neo4j_driver=driver, athena_client=athena,
        )

        self.assertEqual(len(resultado.ruido), 1)
        self.assertEqual(resultado.ruido[0].station_id, "RF-99")
        self.assertIsNone(resultado.ruido[0].avg_laeq_db)
        self.assertEqual(resultado.nivel_estimado, "sin_datos")


if __name__ == "__main__":
    unittest.main()
