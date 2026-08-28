"""Tests de `grafo.cypher`: verifican el Cypher/parámetros generados por
inspección de la cadena, sin conexión real ni el driver `neo4j` instalado
(ver el docstring de `grafo/cypher.py` -- las funciones `*_query()` son
Python puro; solo `Neo4jLoader` importa `neo4j`, de forma perezosa)."""

import unittest

from grafo import cypher
from grafo.cypher import (
    Neo4jLoader,
    barrio_query,
    conectado_con_query,
    distrito_query,
    estacion_medida_query,
    lugar_query,
    parada_transporte_query,
    pertenece_a_query,
    proximo_a_query,
    ubicado_en_query,
)


class DistritoBarrioQueryTests(unittest.TestCase):
    def test_distrito_query(self):
        query, params = distrito_query({"codigo": "01", "nombre": "Centro"})
        self.assertIn("MERGE (n:Distrito {codigo: $codigo})", query)
        self.assertEqual(params, {"codigo": "01", "nombre": "Centro"})

    def test_barrio_query(self):
        query, params = barrio_query(
            {"codigo": "011", "nombre": "Palacio", "distrito_codigo": "01"}
        )
        self.assertIn("MERGE (n:Barrio {codigo: $codigo})", query)
        self.assertIn("n.distrito_codigo = $distrito_codigo", query)
        self.assertEqual(
            params, {"codigo": "011", "nombre": "Palacio", "distrito_codigo": "01"}
        )


class UbicacionQueryTests(unittest.TestCase):
    def test_estacion_medida_query_con_ubicacion(self):
        query, params = estacion_medida_query(
            {
                "id": "trafico:1009",
                "tipo": "trafico",
                "fuente": "trafico",
                "ubicacion": {"lat": 40.4, "lon": -3.7},
            }
        )
        self.assertIn("MERGE (n:EstacionMedida {id: $id})", query)
        self.assertIn("point({latitude: $lat, longitude: $lon", query)
        self.assertEqual(
            params,
            {"id": "trafico:1009", "tipo": "trafico", "fuente": "trafico", "lat": 40.4, "lon": -3.7},
        )

    def test_estacion_medida_query_sin_ubicacion_manda_lat_lon_none(self):
        # Sin ubicacion, el CASE de la query conserva el valor existente en
        # el nodo (n.ubicacion) en vez de sobrescribirlo con null -- $lat/$lon
        # deben viajar como None para que ese CASE se cumpla.
        query, params = estacion_medida_query(
            {"id": "transporte_publico_emt:71", "tipo": "emt", "fuente": "transporte_publico_emt", "ubicacion": None}
        )
        self.assertIsNone(params["lat"])
        self.assertIsNone(params["lon"])
        self.assertIn("CASE WHEN $lat IS NOT NULL AND $lon IS NOT NULL", query)

    def test_parada_transporte_query(self):
        query, params = parada_transporte_query(
            {
                "id": "bicimad:1406",
                "tipo": "bicimad",
                "fuente": "bicimad",
                "ubicacion": {"lat": 40.42, "lon": -3.70},
            }
        )
        self.assertIn("MERGE (n:ParadaTransporte {id: $id})", query)
        self.assertEqual(params["id"], "bicimad:1406")

    def test_lugar_query(self):
        query, params = lugar_query(
            {
                "id": "poi_madrid:109143",
                "nombre": "Friedenskirche",
                "tipo": "poi_turistico",
                "fuente": "poi_madrid",
                "ubicacion": {"lat": 40.4272094, "lon": -3.6891476},
            }
        )
        self.assertIn("MERGE (n:Lugar {id: $id})", query)
        self.assertIn("n.nombre = $nombre", query)
        self.assertEqual(params["nombre"], "Friedenskirche")


class PerteneceAQueryTests(unittest.TestCase):
    def test_pertenece_a_query(self):
        query, params = pertenece_a_query({"barrio_codigo": "011", "distrito_codigo": "01"})
        self.assertIn("MATCH (b:Barrio {codigo: $barrio_codigo})", query)
        self.assertIn("MERGE (b)-[:PERTENECE_A]->(d)", query)
        self.assertEqual(params, {"barrio_codigo": "011", "distrito_codigo": "01"})


class UbicadoEnQueryTests(unittest.TestCase):
    def test_ubicado_en_query(self):
        query, params = ubicado_en_query({"nodo_id": "poi_madrid:1", "barrio_codigo": "011"})
        self.assertIn("MATCH (n {id: $nodo_id})", query)
        self.assertIn("MATCH (n {id: $nodo_id}), (b:Barrio {codigo: $barrio_codigo})", query)
        self.assertIn("MERGE (n)-[:UBICADO_EN]->(b)", query)
        self.assertEqual(params, {"nodo_id": "poi_madrid:1", "barrio_codigo": "011"})


class ProximoAQueryTests(unittest.TestCase):
    def test_proximo_a_query(self):
        query, params = proximo_a_query({"origen_id": "trafico:1", "destino_id": "ruido:1", "distancia_m": 42.5})
        self.assertIn("MATCH (a {id: $origen_id}), (b {id: $destino_id})", query)
        self.assertIn("MERGE (a)-[r:PROXIMO_A]->(b)", query)
        self.assertIn("r.distancia_m = $distancia_m", query)
        self.assertEqual(params, {"origen_id": "trafico:1", "destino_id": "ruido:1", "distancia_m": 42.5})


class ConectadoConQueryTests(unittest.TestCase):
    def test_conectado_con_query_con_ubicacion(self):
        relacion = {
            "origen": {"id": "crtm_red_transporte_madrid:par_4_263", "tipo": "metro", "ubicacion": {"lat": 40.48, "lon": -3.66}},
            "destino": {"id": "crtm_red_transporte_madrid:par_4_262", "tipo": "metro", "ubicacion": {"lat": 40.47, "lon": -3.67}},
            "modo": "metro",
            "linea": "1",
        }
        query, params = conectado_con_query(relacion)
        self.assertIn("MERGE (a:ParadaTransporte {id: $origen_id})", query)
        self.assertIn("MERGE (b:ParadaTransporte {id: $destino_id})", query)
        self.assertIn("MERGE (a)-[r:CONECTADO_CON {linea: $linea}]->(b)", query)
        self.assertIn("r.modo = $modo", query)
        self.assertEqual(
            params,
            {
                "origen_id": "crtm_red_transporte_madrid:par_4_263",
                "destino_id": "crtm_red_transporte_madrid:par_4_262",
                "modo": "metro",
                "linea": "1",
                "origen_lat": 40.48,
                "origen_lon": -3.66,
                "destino_lat": 40.47,
                "destino_lon": -3.67,
            },
        )

    def test_conectado_con_query_sin_ubicacion_manda_lat_lon_none(self):
        relacion = {
            "origen": {"id": "crtm_red_transporte_madrid:x", "tipo": "emt", "ubicacion": None},
            "destino": {"id": "crtm_red_transporte_madrid:y", "tipo": "emt", "ubicacion": None},
            "modo": "emt",
            "linea": "1",
        }
        _, params = conectado_con_query(relacion)
        self.assertIsNone(params["origen_lat"])
        self.assertIsNone(params["destino_lon"])

    def test_linea_forma_parte_del_patron_merge_de_la_relacion(self):
        # Dos líneas distintas sobre el mismo par de paradas no deben
        # colapsar en una sola relación -- `linea` debe ir dentro del propio
        # patrón MERGE, no solo en un SET posterior.
        relacion = {
            "origen": {"id": "a", "tipo": "emt", "ubicacion": None},
            "destino": {"id": "b", "tipo": "emt", "ubicacion": None},
            "modo": "emt",
            "linea": "10",
        }
        query, _ = conectado_con_query(relacion)
        self.assertIn("[r:CONECTADO_CON {linea: $linea}]", query)


class ToUnwindTests(unittest.TestCase):
    def test_convierte_parametros_a_row(self):
        q, _ = proximo_a_query({"origen_id": "a", "destino_id": "b", "distancia_m": 5})
        unwind = cypher._to_unwind(q)
        self.assertTrue(unwind.startswith("UNWIND $rows AS row\n"))
        self.assertIn("row.origen_id", unwind)
        self.assertIn("row.distancia_m", unwind)
        self.assertNotIn("$origen_id", unwind)

    def test_no_toca_literales_ni_row(self):
        q, _ = conectado_con_query(
            {"origen": {"id": "a"}, "destino": {"id": "b"}, "modo": "bus", "linea": "1"}
        )
        unwind = cypher._to_unwind(q)
        self.assertIn("'crtm_red_transporte_madrid'", unwind)  # literal intacto
        self.assertIn("row.origen_lat", unwind)


class _FakeTx:
    def __init__(self, session):
        self._session = session

    def run(self, query, **kwargs):
        self._session.calls.append((query, kwargs))
        if self._session.fail_next:
            self._session.fail_next = False
            raise self._session.transient_exc("conexión caída (simulado)")
        return self

    def consume(self):
        return None


class _FakeSession:
    def __init__(self, driver):
        self._driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute_write(self, fn):
        return fn(_FakeTx(self._driver))


class _FakeDriver:
    def __init__(self, transient_exc):
        self.calls = []
        self.fail_next = False
        self.transient_exc = transient_exc
        self.reconnects = 0

    def session(self, **kwargs):
        return _FakeSession(self)

    def close(self):
        pass


class RunAllBatchingTests(unittest.TestCase):
    """FIL_08: `_run_all` agrupa por sentencia y ejecuta en lotes `UNWIND`,
    con reintento/reconexión ante cortes transitorios."""

    def _loader_con_fake(self, transient_exc):
        loader = object.__new__(Neo4jLoader)
        loader._database = "neo4j"
        loader._uri = "neo4j+s://x"
        loader._auth = ("u", "p")
        fake = _FakeDriver(transient_exc)
        loader._driver = fake
        loader._reconectar = lambda: setattr(fake, "reconnects", fake.reconnects + 1)
        return loader, fake

    def test_agrupa_y_batchea(self):
        try:
            from neo4j.exceptions import SessionExpired
        except ImportError:
            self.skipTest("driver neo4j no instalado")
        loader, fake = self._loader_con_fake(SessionExpired)
        # 2500 distritos + 10 barrios -> 3 lotes de distrito (1000/1000/500) + 1 de barrio
        nodos = [{"codigo": f"D{i}", "nombre": f"n{i}"} for i in range(2500)]
        loader.load_distritos(nodos)
        loader.load_barrios([{"codigo": f"B{i}", "distrito_codigo": "D0"} for i in range(10)])
        self.assertEqual(len(fake.calls), 4)
        self.assertTrue(all(c[0].startswith("UNWIND $rows AS row") for c in fake.calls))
        self.assertEqual([len(c[1]["rows"]) for c in fake.calls], [1000, 1000, 500, 10])
        self.assertIn(":Distrito", fake.calls[0][0])

    def test_reintenta_y_reconecta_ante_error_transitorio(self):
        try:
            from neo4j.exceptions import SessionExpired
        except ImportError:
            self.skipTest("driver neo4j no instalado")
        loader, fake = self._loader_con_fake(SessionExpired)
        cypher._BACKOFF_BASE_S = 0.0  # sin espera real en el test
        fake.fail_next = True
        loader.load_distritos([{"codigo": "D1", "nombre": "n"}])
        self.assertEqual(fake.reconnects, 1)
        self.assertEqual(len(fake.calls), 2)  # 1 fallo + 1 éxito


class Neo4jLoaderSinDriverTests(unittest.TestCase):
    def test_instanciar_sin_driver_instalado_falla_con_import_error(self):
        # No se instala `neo4j` en esta EC2 (ver grafo/requirements.txt);
        # confirma que el fallo es un ImportError claro en el momento de
        # instanciar, no un error oscuro en tiempo de uso.
        from grafo.cypher import Neo4jLoader

        try:
            import neo4j  # noqa: F401

            self.skipTest("el driver neo4j SÍ está instalado en este entorno")
        except ImportError:
            pass

        with self.assertRaises(ImportError):
            Neo4jLoader("neo4j+s://example.databases.neo4j.io", "neo4j", "password")


if __name__ == "__main__":
    unittest.main()
