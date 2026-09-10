"""Tests de `asistente.neo4j_client`: la consulta se verifica por inspección
de la cadena (mismo criterio que `grafo/tests/test_cypher.py`, sin conexión
ni el driver `neo4j` instalado) y `run_neo4j_query` se prueba con un driver
Neo4j falso mínimo (sin ninguna credencial ni conexión real)."""

from __future__ import annotations

import unittest

from asistente.neo4j_client import (
    aparcamientos_cerca_query,
    bicimad_cerca_query,
    estaciones_calidad_aire_que_miden_query,
    estaciones_meteo_cerca_query,
    lineas_que_pasan_por_query,
    lugares_proximos_a_estaciones_trafico_query,
    paradas_de_linea_query,
    recintos_cerca_query,
    run_neo4j_query,
    vecindario_de_lugar_query,
)


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

    def test_calidad_aire_que_miden_filtra_por_contaminante(self):  # FIL_67 / FIL_66
        query, params = estaciones_calidad_aire_que_miden_query("Retiro", "o3", 400.0)
        self.assertIn("(e:EstacionMedida {tipo: 'calidad_aire'})", query)
        self.assertIn("toUpper($contaminante) IN e.contaminantes", query)
        self.assertIn("e.contaminantes AS contaminantes", query)
        self.assertEqual(params, {"nombre_lugar": "Retiro", "contaminante": "o3", "radio_m": 400.0})
        self.assertNotIn("-[r:PROXIMO_A]->", query)


class LibreriaConsultasFil67Tests(unittest.TestCase):
    """FIL_67 Parte 2B — constructores parametrizados nuevos. Solo inspección
    de la cadena, sin conexión."""

    def test_vecindario_devuelve_atributos_de_fil66(self):
        q, p = vecindario_de_lugar_query("Sol", 300.0)
        for campo in ("contaminantes", "magnitudes", "subarea", "anclajes_totales", "plazas_totales"):
            self.assertIn(f"v.{campo} AS {campo}", q)
        self.assertIn("labels(v)[0] AS categoria", q)
        self.assertEqual(p, {"nombre_lugar": "Sol", "radio_m": 300.0})
        self.assertNotIn("-[r:PROXIMO_A]->", q)

    def test_meteo_cerca(self):
        q, p = estaciones_meteo_cerca_query("Retiro", 250.0)
        self.assertIn("(e:EstacionMedida {tipo: 'meteo'})", q)
        self.assertIn("e.magnitudes AS magnitudes", q)
        self.assertEqual(p["radio_m"], 250.0)

    def test_recintos_cerca(self):
        q, _ = recintos_cerca_query("Retiro", 300.0)
        self.assertIn("(v:Lugar {tipo: 'recinto'})", q)

    def test_aparcamientos_y_bicimad_traen_capacidad(self):
        qa, _ = aparcamientos_cerca_query("Sol", 300.0)
        self.assertIn("v.plazas_totales AS plazas_totales", qa)
        self.assertIn("(v:Lugar {tipo: 'aparcamiento'})", qa)
        qb, _ = bicimad_cerca_query("Sol", 300.0)
        self.assertIn("v.anclajes_totales AS anclajes_totales", qb)
        self.assertIn("(v:ParadaTransporte {tipo: 'bicimad'})", qb)

    def test_lineas_de_parada(self):
        q, p = lineas_que_pasan_por_query("crtm_red_transporte_madrid:par_1")
        self.assertIn("[r:CONECTADO_CON]", q)
        self.assertIn("DISTINCT r.modo AS modo, r.linea AS linea", q)
        self.assertEqual(p, {"estacion_id": "crtm_red_transporte_madrid:par_1"})

    def test_paradas_de_linea(self):
        q, p = paradas_de_linea_query("6", "metro")
        self.assertIn("[r:CONECTADO_CON {linea: $linea}]", q)
        self.assertIn("r.modo = $modo", q)
        self.assertEqual(p, {"linea": "6", "modo": "metro"})


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

    def session(self, database=None, **kwargs):
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
