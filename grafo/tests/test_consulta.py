"""Tests de `grafo.consulta` (FIL_67) -- guard de solo lectura y resolución
de credenciales, sin conexión ni el driver `neo4j` instalado."""

from __future__ import annotations

import unittest

from grafo import consulta


class GuardEscrituraTests(unittest.TestCase):
    def test_rechaza_clausulas_de_escritura(self):
        for cy in (
            "MATCH (n) DELETE n",
            "CREATE (n:X)",
            "MATCH (n:X) SET n.y = 1",
            "MATCH (a)-[r]-(b) DETACH DELETE a",
            "MERGE (n:X {id: 1})",
            "MATCH (n) REMOVE n.y",
            "LOAD CSV FROM 'x' AS row RETURN row",
            "CALL apoc.merge.node(['X'], {}) YIELD node RETURN node",
        ):
            with self.assertRaises(ValueError, msg=cy):
                consulta.ejecutar(cy)

    def test_no_marca_lectura_ni_apoc_de_lectura(self):
        for cy in (
            "MATCH (e:EstacionMedida) RETURN e.tipo, count(*)",
            "MATCH (l:Lugar)-[r:PROXIMO_A]-(e) RETURN l, r, e LIMIT 5",
            "CALL apoc.algo.dijkstra(a, b, 'PROXIMO_A', 'distancia_m') YIELD path RETURN path",
            "CALL db.schema.visualization()",
        ):
            self.assertIsNone(consulta._ESCRITURA.search(cy), msg=cy)


class CredencialesSsmTests(unittest.TestCase):
    def test_parseo_de_nombres_ssm(self):
        # el sufijo tras el último "-" es la clave (uri/username/password/database)
        for nombre, esperado in (
            ("/madrono-tfm/dev/secrets/neo4j-uri", "uri"),
            ("/madrono-tfm/dev/secrets/neo4j-username", "username"),
            ("/madrono-tfm/dev/secrets/neo4j-password", "password"),
            ("/madrono-tfm/dev/secrets/neo4j-database", "database"),
        ):
            self.assertEqual(nombre.rsplit("-", 1)[-1], esperado)


if __name__ == "__main__":
    unittest.main()
