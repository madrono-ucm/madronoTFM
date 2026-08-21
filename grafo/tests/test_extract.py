"""Tests de `grafo.extract` -- mockea `boto3` (Athena/S3), sin conexión ni
credenciales reales, mismo criterio que el resto de `grafo/tests/` (ver
`grafo/README.md`, "Tests"). Las consultas y el layout de S3 en sí ya se han
verificado contra datos reales de esta cuenta (`eu-west-1`,
`222234418587`) al escribir este módulo -- ver `doc/069-grafo-lectura-real-
athena.md`.
"""

import io
import json
import unittest

from grafo import extract


def _column(name: str, athena_type: str) -> dict:
    return {"Name": name, "Type": athena_type}


def _row(*values) -> dict:
    return {"Data": [({"VarCharValue": v} if v is not None else {}) for v in values]}


class FakeAthenaClient:
    """Responde `start_query_execution`/`get_query_execution`/
    `get_query_results` como lo haría Athena para una consulta ya
    `SUCCEEDED` de una sola página, sin ninguna llamada de red real."""

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
        status = {"State": self.final_state}
        if self.final_state not in ("SUCCEEDED",):
            status["StateChangeReason"] = "motivo de prueba"
        return {"QueryExecution": {"Status": status}}

    def get_query_results(self, QueryExecutionId, NextToken=None):
        header = _row(*[c["Name"] for c in self.columns])
        return {
            "ResultSet": {
                "ResultSetMetadata": {"ColumnInfo": self.columns},
                "Rows": [header] + self.data_rows,
            }
        }


class FakeS3Client:
    """`objects` es `{key: bytes}`; simula `list_objects_v2` (vía
    paginador) y `get_object` sin tocar S3 real."""

    def __init__(self, objects: "dict[str, bytes]"):
        self.objects = objects

    def get_paginator(self, operation_name):
        assert operation_name == "list_objects_v2"
        return self

    def paginate(self, Bucket, Prefix):
        contents = [{"Key": key} for key in self.objects if key.startswith(Prefix)]
        yield {"Contents": contents}

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}


class RunAthenaQueryTests(unittest.TestCase):
    def test_parsea_filas_y_castea_tipos_numericos(self):
        columns = [_column("point_id", "varchar"), _column("lat", "double"), _column("lon", "double")]
        rows = [_row("4152", "40.41", "-3.70"), _row("4153", None, None)]
        client = FakeAthenaClient(columns, rows)

        result = extract.run_athena_query(
            "SELECT point_id, lat, lon FROM trafico_por_punto_hora",
            "madrono-tfm_dev_gold",
            athena_client=client,
            poll_interval_seconds=0,
        )

        self.assertEqual(
            result,
            [
                {"point_id": "4152", "lat": 40.41, "lon": -3.70},
                {"point_id": "4153", "lat": None, "lon": None},
            ],
        )
        call = client.start_query_execution_calls[0]
        self.assertEqual(call["WorkGroup"], extract.ATHENA_WORKGROUP)
        self.assertEqual(call["QueryExecutionContext"], {"Database": "madrono-tfm_dev_gold"})

    def test_castea_enteros_sin_convertirlos_a_float(self):
        columns = [_column("hour", "integer"), _column("samples_count", "bigint")]
        rows = [_row("14", "4178")]
        client = FakeAthenaClient(columns, rows)

        result = extract.run_athena_query(
            "SELECT hour, samples_count FROM trafico_por_punto_hora",
            "madrono-tfm_dev_gold",
            athena_client=client,
            poll_interval_seconds=0,
        )

        self.assertEqual(result, [{"hour": 14, "samples_count": 4178}])
        self.assertIsInstance(result[0]["hour"], int)

    def test_query_fallida_lanza_runtimeerror_con_el_motivo(self):
        client = FakeAthenaClient([], [], final_state="FAILED")

        with self.assertRaises(RuntimeError) as ctx:
            extract.run_athena_query(
                "SELECT 1", "madrono-tfm_dev_gold", athena_client=client, poll_interval_seconds=0
            )
        self.assertIn("FAILED", str(ctx.exception))
        self.assertIn("motivo de prueba", str(ctx.exception))

    def test_query_que_nunca_termina_lanza_timeout(self):
        client = FakeAthenaClient([], [], final_state="RUNNING")

        with self.assertRaises(TimeoutError):
            extract.run_athena_query(
                "SELECT 1",
                "madrono-tfm_dev_gold",
                athena_client=client,
                poll_interval_seconds=0,
                max_wait_seconds=0,
            )

    def test_query_sin_filas_devuelve_lista_vacia(self):
        columns = [_column("cinema_id", "varchar")]
        client = FakeAthenaClient(columns, [])

        result = extract.run_athena_query(
            "SELECT cinema_id FROM cartelera_cines_estrenos_por_pelicula_cine_fecha",
            "madrono-tfm_dev_gold",
            athena_client=client,
            poll_interval_seconds=0,
        )

        self.assertEqual(result, [])


class FetchGoldNodeSourcesTests(unittest.TestCase):
    """Una consulta por tipo de nodo -- verifica que la forma del resultado
    (columnas `lat`/`lon` planas anidadas en `location`) es la que espera
    `grafo.nodos` (ver `grafo/nodos.py::_location`)."""

    def test_fetch_estaciones_trafico_anida_location(self):
        columns = [_column("point_id", "varchar"), _column("lat", "double"), _column("lon", "double")]
        rows = [_row("10013", "40.43", "-3.67")]
        client = FakeAthenaClient(columns, rows)

        result = extract.fetch_estaciones_trafico(athena_client=client)

        self.assertEqual(result, [{"point_id": "10013", "location": {"lat": 40.43, "lon": -3.67}}])

    def test_fetch_estaciones_calidad_aire(self):
        columns = [
            _column("station_id", "varchar"),
            _column("station_name", "varchar"),
            _column("lat", "double"),
            _column("lon", "double"),
        ]
        rows = [_row("28079027", "Barajas Pueblo", "40.4769179", "-3.5800258")]
        client = FakeAthenaClient(columns, rows)

        result = extract.fetch_estaciones_calidad_aire(athena_client=client)

        self.assertEqual(
            result,
            [
                {
                    "station_id": "28079027",
                    "station_name": "Barajas Pueblo",
                    "location": {"lat": 40.4769179, "lon": -3.5800258},
                }
            ],
        )

    def test_fetch_estaciones_ruido(self):
        columns = [
            _column("station_id", "varchar"),
            _column("station_name", "varchar"),
            _column("lat", "double"),
            _column("lon", "double"),
        ]
        rows = [_row("RF-01", "Plaza del Carmen", "40.4192091", "-3.7031662")]
        client = FakeAthenaClient(columns, rows)

        result = extract.fetch_estaciones_ruido(athena_client=client)

        self.assertEqual(
            result,
            [
                {
                    "station_id": "RF-01",
                    "station_name": "Plaza del Carmen",
                    "location": {"lat": 40.4192091, "lon": -3.7031662},
                }
            ],
        )

    def test_fetch_paradas_emt_solo_identidad_sin_location(self):
        columns = [_column("stop_id", "varchar")]
        rows = [_row("71")]
        client = FakeAthenaClient(columns, rows)

        result = extract.fetch_paradas_emt(athena_client=client)

        self.assertEqual(result, [{"stop_id": "71"}])

    def test_fetch_paradas_bicimad(self):
        columns = [
            _column("station_id", "varchar"),
            _column("name", "varchar"),
            _column("lat", "double"),
            _column("lon", "double"),
        ]
        rows = [_row("1411", "7 - Hortaleza, 75", "40.4251906", "-3.6977715")]
        client = FakeAthenaClient(columns, rows)

        result = extract.fetch_paradas_bicimad(athena_client=client)

        self.assertEqual(
            result,
            [
                {
                    "station_id": "1411",
                    "name": "7 - Hortaleza, 75",
                    "location": {"lat": 40.4251906, "lon": -3.6977715},
                }
            ],
        )

    def test_fetch_lugares_aparcamientos_gold_vacio_no_da_error(self):
        """Gold de `aparcamientos` está vacío a fecha de esta tarea (ver
        docstring de `extract.fetch_lugares_aparcamientos`) -- una consulta
        sin filas debe devolver `[]`, no lanzar ninguna excepción."""
        columns = [
            _column("parking_id", "varchar"),
            _column("name", "varchar"),
            _column("lat", "double"),
            _column("lon", "double"),
        ]
        client = FakeAthenaClient(columns, [])

        result = extract.fetch_lugares_aparcamientos(athena_client=client)

        self.assertEqual(result, [])

    def test_fetch_lugares_cartelera_cines_gold_vacio_no_da_error(self):
        """Mismo caso que `aparcamientos`, ya documentado desde la tarea 063
        (job Silver->Gold sin `--extra-py-files`, Silver vacío)."""
        columns = [_column("cinema_id", "varchar"), _column("cinema_name", "varchar")]
        client = FakeAthenaClient(columns, [])

        result = extract.fetch_lugares_cartelera_cines(athena_client=client)

        self.assertEqual(result, [])


class FetchBronzeOnlySourcesTests(unittest.TestCase):
    """Fuentes sin Silver/Gold: lectura JSON directa de S3, sin Athena."""

    def test_lee_y_concatena_varios_ficheros_json(self):
        objects = {
            "poi_madrid/fecha=2026-08-15/hora=18/a.json": json.dumps(
                [{"poi_id": "1", "name": "Museo A"}]
            ).encode("utf-8"),
            "poi_madrid/fecha=2026-08-15/hora=19/b.json": json.dumps(
                [{"poi_id": "2", "name": "Museo B"}]
            ).encode("utf-8"),
            # Un dataset distinto bajo el mismo bucket -- no debe mezclarse.
            "barrios_distritos_madrid_distritos/fecha=2026-08-15/hora=18/c.json": json.dumps(
                [{"district_id": "01", "name": "Centro"}]
            ).encode("utf-8"),
        }
        s3 = FakeS3Client(objects)

        result = extract.fetch_poi_bronze(s3_client=s3)

        self.assertEqual(
            result,
            [{"poi_id": "1", "name": "Museo A"}, {"poi_id": "2", "name": "Museo B"}],
        )

    def test_sin_ningun_objeto_devuelve_lista_vacia(self):
        """Caso real a fecha de esta tarea: ninguno de los tres orígenes
        Bronze-only (`barrios_distritos_madrid`, `poi_madrid`,
        `crtm_red_transporte_madrid`) se ha subido nunca al bucket Bronze
        real (confirmado con `aws s3 ls` -- ver `doc/069-grafo-lectura-real-
        athena.md`) -- debe devolver `[]` sin ningún error, igual que un
        dataset Gold vacío."""
        s3 = FakeS3Client({})

        self.assertEqual(extract.fetch_distritos_bronze(s3_client=s3), [])
        self.assertEqual(extract.fetch_barrios_bronze(s3_client=s3), [])
        self.assertEqual(extract.fetch_poi_bronze(s3_client=s3), [])
        self.assertEqual(extract.fetch_paradas_crtm_bronze(s3_client=s3), [])

    def test_crtm_bronze_devuelve_registros_de_ruta_sin_transformar(self):
        """`extract` no aplana rutas en paradas -- eso lo hace
        `grafo.nodos.paradas_transporte_from_crtm_bronze` (tarea 067); este
        módulo solo debe devolver los registros de ruta tal cual vienen del
        JSON de Bronze."""
        route = {
            "mode": "metro",
            "route_id": "4__1___",
            "stops": [{"stop_id": "par_4_263", "name": "PINAR DE CHAMARTIN", "location": {"lat": 40.48, "lon": -3.66}}],
        }
        objects = {
            "crtm_red_transporte_madrid/fecha=2026-08-15/hora=18/a.json": json.dumps([route]).encode("utf-8"),
        }
        s3 = FakeS3Client(objects)

        result = extract.fetch_paradas_crtm_bronze(s3_client=s3)

        self.assertEqual(result, [route])


if __name__ == "__main__":
    unittest.main()
