"""Tests de `grafo.cypher`: verifican el Cypher/parámetros generados por
inspección de la cadena, sin conexión real ni el driver `neo4j` instalado
(ver el docstring de `grafo/cypher.py` -- las funciones `*_query()` son
Python puro; solo `Neo4jLoader` importa `neo4j`, de forma perezosa)."""

import unittest

from grafo.cypher import (
    barrio_query,
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
