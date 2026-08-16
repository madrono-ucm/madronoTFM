import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.aforos_peatones_bicicletas.aggregate import (
    aggregate_silver_to_gold,
)


def _silver_record(
    station_id,
    mode,
    measured_at,
    count,
    district_code="1",
    district="Centro",
    address="Calle Arenal esquina San Martín",
    address_notes="Calle peatonal",
    lat=40.417386,
    lon=-3.707141,
):
    return {
        "schema_version": 1,
        "source": "madrid_aforos_peatones_bicicletas",
        "station_id": station_id,
        "mode": mode,
        "count": count,
        "measured_at": measured_at,
        "ingested_at": measured_at,
        "processed_at": measured_at,
        "district_code": district_code,
        "district": district,
        "address": address,
        "address_notes": address_notes,
        "location": {"lat": lat, "lon": lon, "srid": "EPSG:4326"},
    }


class AggregateSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)
        self.records = [
            # Misma estación/modo/hora reingestada dos veces (reingesta del
            # mismo lote, o dos capturas dentro de la misma hora).
            _silver_record("PERM_PEA01_PM01", "peatones", "2024-06-30T00:00:00+02:00", 857),
            _silver_record("PERM_PEA01_PM01", "peatones", "2024-06-30T00:10:00+02:00", 843),
            # Misma estación, hora distinta.
            _silver_record("PERM_PEA01_PM01", "peatones", "2024-06-30T01:00:00+02:00", 450),
            # Misma estación, mismo instante, pero modo distinto: no debe
            # mezclarse con los conteos de peatones (redes de estaciones
            # distintas, unidades no comparables).
            _silver_record(
                "PERM_BICI01_PM01",
                "bicicletas",
                "2024-06-30T00:00:00+02:00",
                16,
                district_code="2",
                district="Arganzuela",
                address="Calle Toledo 133",
                address_notes="Sentido Gta. Pirámides",
                lat=40.405472,
                lon=-3.711961,
            ),
        ]

    def test_groups_by_station_mode_and_hour(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)

        keys = {(r["station_id"], r["mode"], r["date"], r["hour"]) for r in gold}
        self.assertEqual(
            keys,
            {
                ("PERM_PEA01_PM01", "peatones", "2024-06-30", 0),
                ("PERM_PEA01_PM01", "peatones", "2024-06-30", 1),
                ("PERM_BICI01_PM01", "bicicletas", "2024-06-30", 0),
            },
        )

    def test_total_and_average_are_correct_for_the_reingested_bucket(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(
            r
            for r in gold
            if r["station_id"] == "PERM_PEA01_PM01" and r["mode"] == "peatones" and r["hour"] == 0
        )

        self.assertEqual(bucket["samples_count"], 2)
        self.assertEqual(bucket["total_count"], 857 + 843)
        self.assertAlmostEqual(bucket["avg_count"], (857 + 843) / 2)
        self.assertEqual(bucket["max_count"], 857)
        self.assertEqual(bucket["min_count"], 843)
        self.assertEqual(bucket["first_measured_at"], "2024-06-30T00:00:00+02:00")
        self.assertEqual(bucket["last_measured_at"], "2024-06-30T00:10:00+02:00")
        self.assertEqual(bucket["district"], "Centro")

    def test_single_sample_bucket_matches_its_only_record(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bucket = next(r for r in gold if r["station_id"] == "PERM_PEA01_PM01" and r["hour"] == 1)

        self.assertEqual(bucket["samples_count"], 1)
        self.assertEqual(bucket["total_count"], 450)
        self.assertEqual(bucket["avg_count"], 450)

    def test_bicycle_bucket_does_not_mix_with_pedestrian_bucket_same_hour(self):
        gold = aggregate_silver_to_gold(self.records, self.processed_at)
        bicycle_bucket = next(r for r in gold if r["mode"] == "bicicletas")

        self.assertEqual(bicycle_bucket["samples_count"], 1)
        self.assertEqual(bicycle_bucket["total_count"], 16)
        self.assertEqual(bicycle_bucket["district"], "Arganzuela")
        self.assertEqual(bicycle_bucket["location"]["lat"], 40.405472)

    def test_records_without_measured_at_are_ignored(self):
        no_measured_at = _silver_record("PERM_PEA99_PM01", "peatones", None, 10)
        gold = aggregate_silver_to_gold([no_measured_at], self.processed_at)
        self.assertEqual(gold, [])

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_silver_to_gold([], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
