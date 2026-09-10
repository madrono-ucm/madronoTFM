"""Tests de la tool `consulta_grafo` y su router (FIL_67).

Sin AWS, sin Neo4j, sin red: se inyecta un driver falso o se fuerza el
fallo, y se comprueba el contrato de degradación (`FIL_15`).
"""

from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

from asistente.main import create_app
from asistente.mcp_agent import tools
from asistente.mcp_agent.tools import _consulta_grafo_impl


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def run(self, query, params):
        return _FakeResult(self._rows)


class _FakeDriver:
    def __init__(self, rows):
        self._rows = rows

    def session(self, database=None, **kw):
        return _FakeSession(self._rows)


class ToolTests(unittest.TestCase):
    def test_plantilla_desconocida_degrada(self):
        r = tools.consulta_grafo("no_existe", lugar="Sol")
        self.assertFalse(r.disponible)
        self.assertIn("desconocida", r.motivo)
        self.assertIn("vecindario", r.plantillas_disponibles)

    def test_faltan_parametros_degrada(self):
        r = tools.consulta_grafo("aire_que_mide", lugar="Sol")  # falta `contaminante`
        self.assertFalse(r.disponible)
        self.assertIn("contaminante", r.motivo)

    def test_neo4j_caido_degrada_sin_excepcion(self):
        class _Boom:
            def session(self, *a, **k):
                raise RuntimeError("connection refused")

        r = _consulta_grafo_impl("vecindario", "Sol", 300.0, "", "", "", "", neo4j_driver=_Boom())
        self.assertFalse(r.disponible)
        self.assertIn("Neo4j", r.motivo)

    def test_camino_feliz_con_driver_falso(self):
        rows = [
            {"categoria": "EstacionMedida", "subtipo": "calidad_aire", "id": "calidad_aire:1",
             "nombre": "X", "distancia_m": 120, "contaminantes": ["NO2", "O3"], "magnitudes": None,
             "altitud_m": None, "subarea": None, "anclajes_totales": None, "plazas_totales": None},
        ]
        r = _consulta_grafo_impl("vecindario", "Sol", 300.0, "", "", "", "",
                                 neo4j_driver=_FakeDriver(rows))
        self.assertTrue(r.disponible)
        self.assertEqual(r.n_filas, 1)
        # las claves con valor None se limpian
        self.assertNotIn("magnitudes", r.filas[0])
        self.assertEqual(r.filas[0]["contaminantes"], ["NO2", "O3"])
        self.assertEqual(r.parametros, {"lugar": "Sol"})


class Fil72Tests(unittest.TestCase):
    """FIL_72: `plantilla` como enum, contaminante normalizado, diagnóstico
    de 0 filas."""

    def test_plantilla_es_un_enum_cerrado_sincronizado_con_las_builders(self):
        import typing

        from asistente.mcp_agent.tools import _PLANTILLAS_GRAFO

        args = set(typing.get_args(typing.get_type_hints(tools.consulta_grafo)["plantilla"]))
        self.assertEqual(args, set(_PLANTILLAS_GRAFO))

    def test_contaminante_se_normaliza_antes_de_consultar(self):
        capturado = {}

        class _Espia(_FakeSession):
            def run(self, query, params):
                capturado.update(params)
                return _FakeResult([])

        class _EspiaDriver:
            def session(self, *a, **k):
                return _Espia([])

        r = _consulta_grafo_impl("aire_que_mide", "Retiro", 300.0, "ozono", "", "", "",
                                 neo4j_driver=_EspiaDriver())
        self.assertEqual(capturado.get("contaminante"), "O3")
        self.assertEqual(r.contaminante_normalizado, "O3")

    def test_cero_filas_da_diagnostico_util(self):
        r = _consulta_grafo_impl("aire_que_mide", "SitioQueNoExiste", 300.0, "O₃", "", "", "",
                                 neo4j_driver=_FakeDriver([]))
        self.assertTrue(r.disponible)          # la consulta corrió, solo no hubo filas
        self.assertEqual(r.n_filas, 0)
        self.assertEqual(r.radio_m, 300.0)
        self.assertEqual(r.contaminante_normalizado, "O3")
        self.assertEqual(r.lugares_candidatos, [])
        self.assertIn("0 resultados", r.motivo)
        self.assertIn("ningún :Lugar contiene", r.motivo)

    def test_cero_filas_lista_lugares_candidatos(self):
        # driver que distingue la query principal (0 filas) de la sonda de
        # :Lugar (`lugares_que_contienen_query`, sin PROXIMO_A).
        class _PorQuery:
            def session(self, *a, **k):
                outer = self

                class _S:
                    def __enter__(self_): return self_
                    def __exit__(self_, *a): return None
                    def run(self_, query, params):
                        es_sonda = "PROXIMO_A" not in query
                        return _FakeResult([{"nombre": "Parque de El Retiro"}] if es_sonda else [])

                return _S()

        r = _consulta_grafo_impl("bicimad_cerca", "Retiro", 300.0, "", "", "", "",
                                 neo4j_driver=_PorQuery())
        self.assertEqual(r.n_filas, 0)
        self.assertIn("Parque de El Retiro", r.lugares_candidatos)
        self.assertNotIn("ningún :Lugar contiene", r.motivo)


class RouterTests(unittest.TestCase):
    def test_router_degradado_devuelve_respuesta_asistente(self):
        client = TestClient(create_app())
        resp = client.get("/consulta-grafo", params={"plantilla": "no_existe", "lugar": "Sol"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["veredicto"], "con_precaucion")
        self.assertIn("Plantillas disponibles", body["explicacion"])


@unittest.skipUnless(os.environ.get("NEO4J_URI"), "opt-in: necesita Neo4j real (NEO4J_URI/USERNAME/PASSWORD)")
class EnVivoTests(unittest.TestCase):  # FIL_72 punto 5
    """Pares (lugar, plantilla, ...) que en el grafo real deben dar > 0
    filas. Se salta sin credenciales; se corre a mano al recargar el grafo
    o al depurar `consulta_grafo`."""

    CASOS = [
        ("aire_que_mide", {"lugar": "Retiro", "contaminante": "ozono"}),
        ("aire_que_mide", {"lugar": "Chamberí", "contaminante": "NO2"}),
        ("aire_que_mide", {"lugar": "Plaza Elíptica", "contaminante": "PM10"}),
        ("bicimad_cerca", {"lugar": "Callao"}),
        ("meteo_cerca", {"lugar": "Retiro"}),
    ]

    def test_casos_conocidos_devuelven_filas(self):
        for plantilla, kw in self.CASOS:
            with self.subTest(plantilla=plantilla, **kw):
                r = tools.consulta_grafo(plantilla, **kw)
                self.assertTrue(r.disponible, r.motivo)
                self.assertGreater(r.n_filas, 0, f"{plantilla} {kw} -> {r.motivo}")


if __name__ == "__main__":
    unittest.main()
