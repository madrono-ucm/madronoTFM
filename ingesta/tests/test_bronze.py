"""Tests de `BronzeWriter` (tarea 025: soporte de escritura real en S3).

No hacen ninguna llamada de red ni usan credenciales reales: el modo S3 se
verifica con un doble de `boto3.client`, sustituido vía `unittest.mock.patch`.
El modo local se verifica igual que ya lo hacía `test_trafico_madrid.py`
(tarea 002) para confirmar que no cambió su comportamiento.
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from ingesta.capturas.bronze import BronzeWriter


class LocalModeTests(unittest.TestCase):
    def test_write_batch_creates_partitioned_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = BronzeWriter(tmp, dataset="trafico")
            self.assertFalse(writer.is_s3)
            moment = datetime(2026, 8, 12, 9, 30, 0, tzinfo=timezone.utc)
            records = [{"point_id": "1", "intensity_vph": 10}]

            out_path = writer.write_batch(records, moment=moment)

            self.assertIsInstance(out_path, Path)
            self.assertTrue(out_path.exists())
            expected_dir = Path(tmp) / "trafico" / "fecha=2026-08-12" / "hora=09"
            self.assertEqual(out_path.parent, expected_dir)

            with out_path.open(encoding="utf-8") as f:
                written = json.load(f)
            self.assertEqual(written, records)

    def test_pathlike_base_path_is_not_treated_as_s3(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = BronzeWriter(Path(tmp), dataset="trafico")
            self.assertFalse(writer.is_s3)


class S3ModeTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("ingesta.capturas.bronze.boto3.client")
        self.addCleanup(patcher.stop)
        self.mock_boto_client = patcher.start()
        self.mock_s3 = MagicMock()
        self.mock_boto_client.return_value = self.mock_s3

    def test_write_batch_puts_object_with_expected_bucket_and_key(self):
        writer = BronzeWriter(
            "s3://madrono-tfm-dev-bronze-222234418587/", dataset="trafico"
        )
        self.assertTrue(writer.is_s3)
        self.mock_boto_client.assert_called_once_with("s3")

        moment = datetime(2026, 8, 12, 9, 30, 0, tzinfo=timezone.utc)
        records = [{"point_id": "1", "intensity_vph": 10}]

        out_uri = writer.write_batch(records, moment=moment)

        self.mock_s3.put_object.assert_called_once()
        call_kwargs = self.mock_s3.put_object.call_args.kwargs
        self.assertEqual(call_kwargs["Bucket"], "madrono-tfm-dev-bronze-222234418587")
        self.assertTrue(
            call_kwargs["Key"].startswith("trafico/fecha=2026-08-12/hora=09/")
        )
        self.assertTrue(call_kwargs["Key"].endswith(".json"))
        self.assertEqual(call_kwargs["ContentType"], "application/json")
        self.assertEqual(json.loads(call_kwargs["Body"]), records)

        self.assertEqual(
            out_uri,
            f"s3://madrono-tfm-dev-bronze-222234418587/{call_kwargs['Key']}",
        )

    def test_optional_prefix_is_prepended_to_the_key(self):
        writer = BronzeWriter(
            "s3://madrono-tfm-dev-bronze-222234418587/algun/prefijo",
            dataset="trafico",
        )
        moment = datetime(2026, 8, 12, 9, 30, 0, tzinfo=timezone.utc)

        writer.write_batch([{"a": 1}], moment=moment)

        key = self.mock_s3.put_object.call_args.kwargs["Key"]
        self.assertTrue(
            key.startswith("algun/prefijo/trafico/fecha=2026-08-12/hora=09/")
        )

    def test_no_local_filesystem_writes_happen_in_s3_mode(self):
        writer = BronzeWriter(
            "s3://madrono-tfm-dev-bronze-222234418587/", dataset="trafico"
        )
        moment = datetime(2026, 8, 12, 9, 30, 0, tzinfo=timezone.utc)

        out_uri = writer.write_batch([{"a": 1}], moment=moment)

        self.assertIsInstance(out_uri, str)
        self.assertTrue(out_uri.startswith("s3://"))


if __name__ == "__main__":
    unittest.main()
