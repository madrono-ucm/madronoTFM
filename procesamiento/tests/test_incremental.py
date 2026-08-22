"""Tests de `procesamiento/silver_gold/incremental.py` (tarea 072).

Python puro (sin `pyspark`, sin `boto3` real): `partition_has_objects`/
`existing_daily_partitions` reciben un cliente S3 doble en vez de uno real.
"""

from __future__ import annotations

import unittest
from datetime import datetime

from procesamiento.silver_gold.incremental import (
    date_range,
    daily_partition_uri,
    existing_daily_partitions,
    hourly_partition_uri,
    partition_has_objects,
    previous_hour,
    today,
)


class FakeS3Client:
    """Doble mínimo de `boto3.client("s3")`: solo `list_objects_v2`."""

    def __init__(self, prefixes_with_objects: "set[str]"):
        self._prefixes_with_objects = prefixes_with_objects

    def list_objects_v2(self, Bucket: str, Prefix: str, MaxKeys: int):
        key_count = 1 if f"s3://{Bucket}/{Prefix}" in self._prefixes_with_objects else 0
        return {"KeyCount": key_count}


class PreviousHourTests(unittest.TestCase):
    def test_hora_intermedia(self):
        moment = datetime(2026, 8, 22, 14, 10)
        self.assertEqual(previous_hour(moment), ("2026-08-22", "13"))

    def test_cruce_de_dia(self):
        moment = datetime(2026, 8, 22, 0, 10)
        self.assertEqual(previous_hour(moment), ("2026-08-21", "23"))

    def test_hora_con_cero_relleno(self):
        moment = datetime(2026, 8, 22, 9, 10)
        fecha, hora = previous_hour(moment)
        self.assertEqual(hora, "08")


class DateRangeTests(unittest.TestCase):
    def test_solo_hoy(self):
        moment = datetime(2026, 8, 22, 8, 0)
        self.assertEqual(date_range(moment, 0, 0), ["2026-08-22"])

    def test_ventana_hacia_atras(self):
        moment = datetime(2026, 8, 22, 8, 0)
        self.assertEqual(
            date_range(moment, -3, -1),
            ["2026-08-19", "2026-08-20", "2026-08-21"],
        )

    def test_ventana_hacia_delante(self):
        moment = datetime(2026, 8, 22, 8, 0)
        self.assertEqual(
            date_range(moment, 0, 3),
            ["2026-08-22", "2026-08-23", "2026-08-24", "2026-08-25"],
        )

    def test_cruce_de_mes(self):
        moment = datetime(2026, 8, 30, 8, 0)
        self.assertEqual(
            date_range(moment, 0, 2),
            ["2026-08-30", "2026-08-31", "2026-09-01"],
        )

    def test_today_es_date_range_de_un_solo_dia(self):
        moment = datetime(2026, 8, 22, 23, 59)
        self.assertEqual(today(moment), "2026-08-22")


class PartitionUriTests(unittest.TestCase):
    def test_hourly_partition_uri(self):
        self.assertEqual(
            hourly_partition_uri("s3://bucket/trafico/", "2026-08-22", "13"),
            "s3://bucket/trafico/fecha=2026-08-22/hora=13/",
        )

    def test_hourly_partition_uri_sin_barra_final(self):
        self.assertEqual(
            hourly_partition_uri("s3://bucket/trafico", "2026-08-22", "13"),
            "s3://bucket/trafico/fecha=2026-08-22/hora=13/",
        )

    def test_daily_partition_uri(self):
        self.assertEqual(
            daily_partition_uri("s3://bucket/ruido/", "2026-08-22"),
            "s3://bucket/ruido/fecha=2026-08-22/",
        )


class PartitionHasObjectsTests(unittest.TestCase):
    def test_partition_con_objetos(self):
        client = FakeS3Client({"s3://bucket/trafico/fecha=2026-08-22/hora=13/"})
        self.assertTrue(
            partition_has_objects(client, "s3://bucket/trafico/fecha=2026-08-22/hora=13/")
        )

    def test_partition_vacia(self):
        client = FakeS3Client(set())
        self.assertFalse(
            partition_has_objects(client, "s3://bucket/trafico/fecha=2026-08-22/hora=13/")
        )


class ExistingDailyPartitionsTests(unittest.TestCase):
    def test_filtra_solo_las_que_existen(self):
        client = FakeS3Client(
            {
                "s3://bucket/ruido/fecha=2026-08-20/",
                "s3://bucket/ruido/fecha=2026-08-22/",
            }
        )
        result = existing_daily_partitions(
            client, "s3://bucket/ruido/", ["2026-08-20", "2026-08-21", "2026-08-22"]
        )
        self.assertEqual(
            result,
            [
                ("2026-08-20", "s3://bucket/ruido/fecha=2026-08-20/"),
                ("2026-08-22", "s3://bucket/ruido/fecha=2026-08-22/"),
            ],
        )

    def test_ninguna_existe(self):
        client = FakeS3Client(set())
        result = existing_daily_partitions(client, "s3://bucket/ruido/", ["2026-08-21"])
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
