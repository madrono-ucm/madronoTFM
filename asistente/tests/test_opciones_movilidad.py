"""Tests de la tool `opciones_movilidad` (tarea 096) -- mockea Neo4j/Athena,
sin ninguna llamada ni credencial real.

Como `afluencia_estimada` (`test_afluencia_estimada.py`), pero más: cada
modo hace **dos** consultas Neo4j (origen y destino) y hasta **dos**
consultas Athena -- hasta 8 llamadas Neo4j + 6 Athena por invocación.
`_RoutingNeo4jDriver` enruta por `nombre_lugar` (exacto, en minúsculas) y,
si la consulta sigue `PROXIMO_A`, también por `tipo`. `_RoutingAthenaClient`
enruta por nombre de tabla y filtra las filas devueltas a las que su
columna de identificador aparece en el propio SQL (mismo criterio que un
`WHERE ... IN (...)` real, sin necesitar un motor SQL de verdad)."""

import re
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
        nombre_lugar = (params.get("nombre_lugar") or "").lower()
        if "PROXIMO_A" not in query:
            return _RoutingNeo4jResult(self._driver.lugares.get(nombre_lugar, []))
        for tipo, rows_by_lugar in self._driver.rows_by_tipo.items():
            if f"tipo: '{tipo}'" in query:
                return _RoutingNeo4jResult(rows_by_lugar.get(nombre_lugar, []))
        return _RoutingNeo4jResult([])


class _RoutingNeo4jDriver:
    """`lugares`: `{"retiro": [{"lugar_id": ..., "lugar_nombre": ...}]}` --
    solo hace falta una fila no vacía para que `resolver_lugar_query`
    encuentre el lugar; `resolver_lugar_query` no filtra por `tipo`, así que
    se enruta solo por `nombre_lugar` en minúsculas.

    `rows_by_tipo`: `{"trafico": {"retiro": [...], "sol": [...]}, ...}` --
    filas de `lugares_proximos_a_*_query` (con `estacion_id`/`distancia_m`),
    una lista por combinación de tipo y lugar consultado."""

    def __init__(self, lugares: dict, rows_by_tipo: dict):
        self.lugares = lugares
        self.rows_by_tipo = rows_by_tipo

    def session(self, database=None):
        return _RoutingNeo4jSession(self)


class _RoutingAthenaClient:
    """`rows_by_tabla`: `{"trafico_por_punto_hora": (columns, {"1": row, "2": row})}` --
    enruta por nombre de tabla (`FROM <tabla>`) y filtra las filas cuyo id
    (la clave de `rows_by_id`) aparece literalmente en el SQL (equivalente
    a `IN (...)`)."""

    def __init__(self, rows_by_tabla: dict):
        self.rows_by_tabla = rows_by_tabla
        self.start_query_execution_calls: "list[dict]" = []

    def start_query_execution(self, QueryString, QueryExecutionContext, WorkGroup):
        self.start_query_execution_calls.append({"QueryString": QueryString})
        for tabla in self.rows_by_tabla:
            if f"FROM {tabla}" in QueryString:
                return {"QueryExecutionId": f"fake-{tabla}", "_sql": QueryString}
        return {"QueryExecutionId": "fake-empty", "_sql": QueryString}

    def get_query_execution(self, QueryExecutionId):
        return {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}

    def get_query_results(self, QueryExecutionId, NextToken=None):
        tabla = QueryExecutionId.replace("fake-", "", 1)
        if tabla not in self.rows_by_tabla:
            return {"ResultSet": {"ResultSetMetadata": {"ColumnInfo": []}, "Rows": [_row()]}}
        columns, rows_by_id = self.rows_by_tabla[tabla]
        # Reconstruye qué IDs pidió esta consulta concreta a partir de las
        # últimas llamadas registradas -- suficiente para estos tests
        # (no hay concurrencia real).
        sql = self.start_query_execution_calls[-1]["QueryString"]
        ids_pedidos = set(re.findall(r"'([^']+)'", sql))
        rows = [row for rid, row in rows_by_id.items() if rid in ids_pedidos]
        header = _row(*[c["Name"] for c in columns])
        return {"ResultSet": {"ResultSetMetadata": {"ColumnInfo": columns}, "Rows": [header] + rows}}


_TRAFICO_COLUMNS = [
    _column("point_id", "varchar"),
    _column("hour", "integer"),
    _column("avg_service_level", "double"),
    _column("avg_occupancy_ratio", "double"),
]
_BICIMAD_COLUMNS = [
    _column("station_id", "varchar"),
    _column("hour", "integer"),
    _column("avg_bikes_available", "double"),
    _column("avg_docks_available", "double"),
]
_EMT_COLUMNS = [
    _column("stop_id", "varchar"),
    _column("hour", "integer"),
    _column("avg_estimate_arrive_sec", "double"),
]


class OpcionesMovilidadToolTests(unittest.TestCase):
    def test_ni_origen_ni_destino_coinciden_devuelve_lista_vacia(self):
        driver = _RoutingNeo4jDriver(lugares={}, rows_by_tipo={})
        athena = _RoutingAthenaClient({})

        resultado = tools._opciones_movilidad_impl(
            "Zona A", "Zona B", datetime(2026, 8, 20, 14, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(resultado, [])
        self.assertEqual(athena.start_query_execution_calls, [])

    def test_devuelve_las_tres_opciones_con_datos_reales_en_ambos_extremos(self):
        lugares = {"retiro": [{"lugar_id": "poi:1"}], "sol": [{"lugar_id": "poi:2"}]}
        rows_by_tipo = {
            "trafico": {
                "retiro": [{"estacion_id": "trafico:1", "distancia_m": 50.0}],
                "sol": [{"estacion_id": "trafico:2", "distancia_m": 60.0}],
            },
            "bicimad": {
                "retiro": [{"estacion_id": "bicimad:10", "distancia_m": 40.0}],
                "sol": [{"estacion_id": "bicimad:20", "distancia_m": 45.0}],
            },
            "emt": {
                "retiro": [{"estacion_id": "transporte_publico_emt:100", "distancia_m": 30.0}],
                "sol": [{"estacion_id": "transporte_publico_emt:200", "distancia_m": 35.0}],
            },
        }
        driver = _RoutingNeo4jDriver(lugares, rows_by_tipo)
        athena = _RoutingAthenaClient(
            {
                "trafico_por_punto_hora": (
                    _TRAFICO_COLUMNS,
                    {
                        "1": _row("1", "14", "1.0", "0.2"),  # fluido
                        "2": _row("2", "14", "5.0", "0.9"),  # congestionado
                    },
                ),
                "bicimad_por_estacion_hora": (
                    _BICIMAD_COLUMNS,
                    {
                        "10": _row("10", "14", "8.0", "2.0"),
                        "20": _row("20", "14", "1.0", "6.0"),
                    },
                ),
                "transporte_publico_emt_por_parada_hora": (
                    _EMT_COLUMNS,
                    {
                        "100": _row("100", "14", "120.0"),  # 2 min
                        "200": _row("200", "14", "600.0"),  # 10 min
                    },
                ),
            }
        )

        resultado = tools._opciones_movilidad_impl(
            "Retiro", "Sol", datetime(2026, 8, 20, 14, tzinfo=_MADRID), neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual([o.modo for o in resultado], ["coche", "transporte_publico", "bicimad"])
        for opcion in resultado:
            self.assertIsNone(opcion.duracion_estimada_min)

        coche = resultado[0]
        self.assertIn("fluido", coche.incidencias[0])
        self.assertIn("congestionado", coche.incidencias[1])

        transporte_publico = resultado[1]
        self.assertIn("2.0 min", transporte_publico.incidencias[0])
        self.assertIn("10.0 min", transporte_publico.incidencias[1])

        bicimad = resultado[2]
        self.assertIn("8.0 bicis", bicimad.incidencias[0])
        self.assertIn("6.0 anclajes", bicimad.incidencias[1])

    def test_solo_origen_resuelve_destino_aparece_sin_datos_en_las_tres(self):
        lugares = {"retiro": [{"lugar_id": "poi:1"}]}
        rows_by_tipo = {
            "trafico": {"retiro": [{"estacion_id": "trafico:1", "distancia_m": 50.0}]},
        }
        driver = _RoutingNeo4jDriver(lugares, rows_by_tipo)
        athena = _RoutingAthenaClient(
            {
                "trafico_por_punto_hora": (
                    _TRAFICO_COLUMNS,
                    {"1": _row("1", "14", "1.0", "0.2")},
                ),
            }
        )

        resultado = tools._opciones_movilidad_impl(
            "Retiro",
            "Lugar Que No Existe",
            datetime(2026, 8, 20, 14, tzinfo=_MADRID),
            neo4j_driver=driver,
            athena_client=athena,
        )

        self.assertEqual(len(resultado), 3)
        coche = resultado[0]
        self.assertIn("fluido", coche.incidencias[0])
        self.assertIn("sin datos", coche.incidencias[1])

    def test_sin_momento_usa_la_hora_mas_reciente_del_dia(self):
        # Dos estaciones distintas cerca de "Retiro", cada una con datos a
        # una hora distinta -- sin `momento`, solo debe contar la más
        # reciente (15h, congestionado), no la más antigua (9h, fluido).
        lugares = {"retiro": [{"lugar_id": "poi:1"}], "sol": [{"lugar_id": "poi:2"}]}
        rows_by_tipo = {
            "trafico": {
                "retiro": [
                    {"estacion_id": "trafico:1", "distancia_m": 50.0},
                    {"estacion_id": "trafico:3", "distancia_m": 55.0},
                ],
                "sol": [],
            },
        }
        driver = _RoutingNeo4jDriver(lugares, rows_by_tipo)
        athena = _RoutingAthenaClient(
            {
                "trafico_por_punto_hora": (
                    _TRAFICO_COLUMNS,
                    {
                        "1": _row("1", "9", "1.0", "0.1"),  # fluido, hora antigua
                        "3": _row("3", "15", "5.0", "0.9"),  # congestionado, hora reciente
                    },
                ),
            }
        )

        resultado = tools._opciones_movilidad_impl(
            "Retiro", "Sol", None, neo4j_driver=driver, athena_client=athena
        )

        self.assertEqual(len(resultado), 3)
        self.assertIn("congestionado", resultado[0].incidencias[0])
        self.assertNotIn("fluido", resultado[0].incidencias[0])


if __name__ == "__main__":
    unittest.main()
