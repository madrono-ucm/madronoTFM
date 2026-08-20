import unittest

from grafo.nodos import barrios_from_bronze
from grafo.relaciones import pertenece_a_from_barrio_node, pertenece_a_from_barrios


class PerteneceATests(unittest.TestCase):
    def test_from_barrio_node(self):
        barrio_node = {"codigo": "011", "nombre": "Palacio", "distrito_codigo": "01"}
        self.assertEqual(
            pertenece_a_from_barrio_node(barrio_node),
            {"barrio_codigo": "011", "distrito_codigo": "01"},
        )

    def test_from_barrios_un_par_por_barrio(self):
        barrio_records = [
            {"neighbourhood_id": "011", "name": "Palacio", "district_id": "01"},
            {"neighbourhood_id": "021", "name": "Gaztambide", "district_id": "02"},
        ]
        barrio_nodes = barrios_from_bronze(barrio_records)
        relaciones = pertenece_a_from_barrios(barrio_nodes)
        self.assertEqual(
            relaciones,
            [
                {"barrio_codigo": "011", "distrito_codigo": "01"},
                {"barrio_codigo": "021", "distrito_codigo": "02"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
