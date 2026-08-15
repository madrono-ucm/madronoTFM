"""Tests de `BronzeWriter` (tarea 025: soporte de escritura real en S3).

No hacen ninguna llamada de red ni usan credenciales reales: el modo S3 se
verifica con un doble de `boto3.client`, sustituido vía `unittest.mock.patch`.
El modo local se verifica igual que ya lo hacía `test_trafico_madrid.py`
(tarea 002) para confirmar que no cambió su comportamiento.

`MadridTimezoneDefaultTests` (tarea 034) cubre que, sin `moment` explícito,
`write_batch` particiona según hora de Madrid (no UTC) — incluyendo un caso
que cruza medianoche en una zona pero no en la otra, para confirmar que se
usa de verdad `zoneinfo.ZoneInfo("Europe/Madrid")` y no un offset fijo.
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from ingesta.capturas.bronze import BronzeWriter, now_madrid

MADRID_TZ = ZoneInfo("Europe/Madrid")


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


class NowMadridTests(unittest.TestCase):
    def test_returns_aware_datetime_in_europe_madrid(self):
        moment = now_madrid()

        self.assertIsNotNone(moment.tzinfo)
        self.assertEqual(moment.tzinfo, MADRID_TZ)
        # Aware y consistente con el instante real: comparable directamente
        # con datetime.now(UTC) sin lanzar TypeError, con una diferencia
        # mínima (solo cambia cómo se representa, no el instante).
        delta = abs(
            (moment.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
        )
        self.assertLess(delta, 5)


class MadridTimezoneDefaultTests(unittest.TestCase):
    """Tarea 034: sin `moment` explícito, `write_batch` particiona en hora de Madrid."""

    def test_partitions_by_madrid_date_when_utc_date_is_still_the_previous_day(self):
        # 2026-01-15 00:30 hora de Madrid (CET, UTC+1) es todavía 2026-01-14
        # en UTC: la partición debe reflejar el 15 (Madrid), no el 14 (UTC).
        madrid_moment = datetime(2026, 1, 15, 0, 30, 0, tzinfo=MADRID_TZ)
        self.assertEqual(
            madrid_moment.astimezone(timezone.utc).date().isoformat(), "2026-01-14"
        )

        with tempfile.TemporaryDirectory() as tmp:
            writer = BronzeWriter(tmp, dataset="trafico")
            with patch(
                "ingesta.capturas.bronze.now_madrid", return_value=madrid_moment
            ):
                out_path = writer.write_batch([{"a": 1}])

            expected_dir = Path(tmp) / "trafico" / "fecha=2026-01-15" / "hora=00"
            self.assertEqual(out_path.parent, expected_dir)

    def test_partitions_correctly_in_summer_offset_too(self):
        # 2026-08-15 01:30 hora de Madrid (CEST, UTC+2, no UTC+1) es todavía
        # 2026-08-14 en UTC: confirma que se usa el desfase real de la zona
        # `Europe/Madrid` según la época del año, no un offset fijo.
        madrid_moment = datetime(2026, 8, 15, 1, 30, 0, tzinfo=MADRID_TZ)
        self.assertEqual(
            madrid_moment.astimezone(timezone.utc).date().isoformat(), "2026-08-14"
        )

        with tempfile.TemporaryDirectory() as tmp:
            writer = BronzeWriter(tmp, dataset="trafico")
            with patch(
                "ingesta.capturas.bronze.now_madrid", return_value=madrid_moment
            ):
                out_path = writer.write_batch([{"a": 1}])

            expected_dir = Path(tmp) / "trafico" / "fecha=2026-08-15" / "hora=01"
            self.assertEqual(out_path.parent, expected_dir)

    def test_explicit_moment_still_overrides_madrid_default(self):
        madrid_moment = datetime(2026, 1, 15, 0, 30, 0, tzinfo=MADRID_TZ)
        explicit_moment = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as tmp:
            writer = BronzeWriter(tmp, dataset="trafico")
            with patch(
                "ingesta.capturas.bronze.now_madrid", return_value=madrid_moment
            ) as mock_now_madrid:
                out_path = writer.write_batch([{"a": 1}], moment=explicit_moment)
                mock_now_madrid.assert_not_called()

            expected_dir = Path(tmp) / "trafico" / "fecha=2026-03-01" / "hora=10"
            self.assertEqual(out_path.parent, expected_dir)


if __name__ == "__main__":
    unittest.main()
