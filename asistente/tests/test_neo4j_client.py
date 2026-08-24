"""Tests de `asistente.neo4j_client`: la consulta se verifica por inspección
de la cadena (mismo criterio que `grafo/tests/test_cypher.py`, sin conexión
ni el driver `neo4j` instalado) y `run_neo4j_query` se prueba con un driver
Neo4j falso mínimo (sin ninguna credencial ni conexión real)."""

from __future__ import annotations

import unittest

from asistente.neo4j_client import lugares_proximos_a_estaciones_trafico_query, run_neo4j_query


class LugaresProximosQueryTests(unittest.TestCase):
    def test_query_matches_lugar_por_texto_y_filtra_por_radio(self):
        query, params = lugares_proximos_a_estaciones_trafico_query("Retiro", 300.0)

        self.assertIn("MATCH (l:Lugar)", query)
        self.assertIn("toLower(l.nombre) CONTAINS toLower($nombre_lugar)", query)
        self.assertIn("(l)-[r:PROXIMO_A]-(e:EstacionMedida {tipo: 'trafico'})", query)
        self.assertIn("r.distancia_m <= $radio_m", query)
        self.assertEqual(params, {"nombre_lugar": "Retiro", "radio_m": 300.0})

    def test_query_no_usa_direccion_en_proximo_a(self):
        # La relación se carga en un único sentido por pareja (ver
        # grafo/relaciones.py::proximo_a) -- esta consulta debe ser
        # explícitamente no dirigida, sin `->` ni `<-` en el patrón PROXIMO_A.
        query, _ = lugares_proximos_a_estaciones_trafico_query("Sol", 500.0)
        self.assertNotIn("-[r:PROXIMO_A]->", query)
        self.assertNotIn("<-[r:PROXIMO_A]-", query)


class _FakeResult:
    def __init__(self, records: "list[dict]"):
        self._records = records

    def __iter__(self):
        return iter(self._records)


class _FakeSession:
    def __init__(self, records: "list[dict]", calls: list):
        self._records = records
        self._calls = calls

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *exc_info) -> None:
        return None

    def run(self, query, params):
        self._calls.append({"query": query, "params": params})
        return _FakeResult(self._records)


class _FakeDriver:
    def __init__(self, records: "list[dict]"):
        self._records = records
        self.session_calls: list = []
        self.run_calls: list = []

    def session(self, database=None):
        self.session_calls.append(database)
        return _FakeSession(self._records, self.run_calls)


class RunNeo4jQueryTests(unittest.TestCase):
    def test_devuelve_las_filas_como_dict(self):
        driver = _FakeDriver([{"a": 1}, {"a": 2}])

        rows = run_neo4j_query("MATCH (n) RETURN n", {}, driver=driver, database="neo4j")

        self.assertEqual(rows, [{"a": 1}, {"a": 2}])
        self.assertEqual(driver.session_calls, ["neo4j"])
        self.assertEqual(driver.run_calls, [{"query": "MATCH (n) RETURN n", "params": {}}])

    def test_sin_filas_devuelve_lista_vacia(self):
        driver = _FakeDriver([])

        rows = run_neo4j_query("MATCH (n) RETURN n", {}, driver=driver)

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
