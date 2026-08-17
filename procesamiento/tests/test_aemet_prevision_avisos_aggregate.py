import unittest
from datetime import datetime, timezone

from procesamiento.silver_gold.aemet_prevision_avisos.aggregate import (
    aggregate_avisos_silver_to_gold,
    aggregate_prevision_silver_to_gold,
)


def _silver_prevision_record(
    municipio_code,
    valid_date,
    ingested_at,
    temperature_max_c=30.0,
    temperature_min_c=18.0,
    precipitation_probability_pct=10.0,
    municipio_name="Madrid",
):
    return {
        "schema_version": 1,
        "source": "aemet_prediccion_municipio",
        "municipio_code": municipio_code,
        "municipio_name": municipio_name,
        "province": "Madrid",
        "elaborated_at": "2026-08-13T21:19:10",
        "valid_date": valid_date,
        "sky_state": "Despejado",
        "sky_state_code": "11",
        "precipitation_probability_pct": precipitation_probability_pct,
        "temperature_max_c": temperature_max_c,
        "temperature_min_c": temperature_min_c,
        "thermal_sensation_max_c": temperature_max_c,
        "thermal_sensation_min_c": temperature_min_c,
        "humidity_max_pct": 40.0,
        "humidity_min_pct": 10.0,
        "wind_direction": "C",
        "wind_speed_kmh": 0.0,
        "wind_gust_max_kmh": None,
        "uv_max": 8.0,
        "ingested_at": ingested_at,
        "processed_at": "2026-08-14T10:00:00+02:00",
    }


def _silver_aviso_record(
    zone,
    level,
    identifier,
    effective_from,
    effective_until="2026-08-14T21:00:00+02:00",
    phenomenon="Altas temperaturas",
):
    return {
        "schema_version": 1,
        "source": "aemet_avisos_cap",
        "identifier": identifier,
        "sent_at": "2026-08-14T07:45:00+02:00",
        "zone": zone,
        "level": level,
        "phenomenon": phenomenon,
        "probability": "100%",
        "severity": "Moderate",
        "urgency": "Expected",
        "certainty": "Likely",
        "effective_from": effective_from,
        "effective_until": effective_until,
        "headline": "Aviso",
        "description": "Descripcion",
        "ingested_at": "2026-08-14T00:32:05+02:00",
        "processed_at": "2026-08-14T10:00:00+02:00",
    }


class AggregatePrevisionSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)

    def test_groups_by_municipio_and_leadtime_days(self):
        records = [
            # Municipio 28079, previsión "de mañana" (leadtime=1) capturada
            # dos días distintos.
            _silver_prevision_record("28079", "2026-08-15", "2026-08-14T00:00:00+02:00", temperature_max_c=34.0),
            _silver_prevision_record("28079", "2026-08-16", "2026-08-15T00:00:00+02:00", temperature_max_c=30.0),
            # Mismo municipio, previsión "de hoy" (leadtime=0): bucket distinto.
            _silver_prevision_record("28079", "2026-08-14", "2026-08-14T00:00:00+02:00", temperature_max_c=38.0),
            # Otro municipio, mismo leadtime=1: bucket distinto.
            _silver_prevision_record("28006", "2026-08-15", "2026-08-14T00:00:00+02:00", temperature_max_c=25.0),
        ]

        gold = aggregate_prevision_silver_to_gold(records, self.processed_at)

        keys = {(r["municipio_code"], r["leadtime_days"]) for r in gold}
        self.assertEqual(keys, {("28079", 1), ("28079", 0), ("28006", 1)})

    def test_computes_avg_and_max_min_of_temperatures_and_precipitation(self):
        records = [
            _silver_prevision_record(
                "28079", "2026-08-15", "2026-08-14T00:00:00+02:00",
                temperature_max_c=30.0, temperature_min_c=20.0, precipitation_probability_pct=10.0,
            ),
            _silver_prevision_record(
                "28079", "2026-08-16", "2026-08-15T00:00:00+02:00",
                temperature_max_c=40.0, temperature_min_c=10.0, precipitation_probability_pct=90.0,
            ),
        ]

        gold = aggregate_prevision_silver_to_gold(records, self.processed_at)
        bucket = next(r for r in gold if r["municipio_code"] == "28079" and r["leadtime_days"] == 1)

        self.assertEqual(bucket["samples_count"], 2)
        self.assertEqual(bucket["avg_temperature_max_c"], 35.0)
        self.assertEqual(bucket["max_temperature_max_c"], 40.0)
        self.assertEqual(bucket["avg_temperature_min_c"], 15.0)
        self.assertEqual(bucket["min_temperature_min_c"], 10.0)
        self.assertEqual(bucket["avg_precipitation_probability_pct"], 50.0)
        self.assertEqual(bucket["max_precipitation_probability_pct"], 90.0)
        self.assertEqual(bucket["municipio_name"], "Madrid")
        self.assertEqual(bucket["first_valid_date"], "2026-08-15")
        self.assertEqual(bucket["last_valid_date"], "2026-08-16")

    def test_records_without_valid_date_or_ingested_at_are_ignored(self):
        record = _silver_prevision_record("28079", None, "2026-08-14T00:00:00+02:00")
        self.assertEqual(aggregate_prevision_silver_to_gold([record], self.processed_at), [])

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_prevision_silver_to_gold([], self.processed_at), [])


class AggregateAvisosSilverToGoldTests(unittest.TestCase):
    def setUp(self):
        self.processed_at = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)

    def test_groups_by_zone_fecha_and_level(self):
        records = [
            _silver_aviso_record("Madrid", "amarillo", "a1", "2026-08-14T13:00:00+02:00"),
            _silver_aviso_record("Madrid", "amarillo", "a2", "2026-08-14T15:00:00+02:00"),
            # Mismo dia/zona, nivel distinto: bucket separado.
            _silver_aviso_record("Madrid", "naranja", "a3", "2026-08-14T16:00:00+02:00"),
            # Otro dia: bucket separado.
            _silver_aviso_record("Madrid", "amarillo", "a4", "2026-08-15T09:00:00+02:00"),
            # Otra zona: bucket separado.
            _silver_aviso_record("Toledo", "amarillo", "a5", "2026-08-14T13:00:00+02:00"),
        ]

        gold = aggregate_avisos_silver_to_gold(records, self.processed_at)

        keys = {(r["zone"], r["fecha"], r["level"]) for r in gold}
        self.assertEqual(
            keys,
            {
                ("Madrid", "2026-08-14", "amarillo"),
                ("Madrid", "2026-08-14", "naranja"),
                ("Madrid", "2026-08-15", "amarillo"),
                ("Toledo", "2026-08-14", "amarillo"),
            },
        )

    def test_alerts_count_deduplicates_reingested_identifier(self):
        records = [
            _silver_aviso_record("Madrid", "amarillo", "a1", "2026-08-14T13:00:00+02:00"),
            # Reingesta del mismo aviso vigente (mismo identifier).
            _silver_aviso_record("Madrid", "amarillo", "a1", "2026-08-14T13:00:00+02:00"),
            _silver_aviso_record("Madrid", "amarillo", "a2", "2026-08-14T14:00:00+02:00"),
        ]

        gold = aggregate_avisos_silver_to_gold(records, self.processed_at)
        bucket = next(r for r in gold if r["zone"] == "Madrid" and r["level"] == "amarillo")

        self.assertEqual(bucket["samples_count"], 3)
        self.assertEqual(bucket["alerts_count"], 2)

    def test_phenomena_and_effective_range_are_tracked(self):
        records = [
            _silver_aviso_record(
                "Madrid", "amarillo", "a1", "2026-08-14T13:00:00+02:00",
                effective_until="2026-08-14T18:00:00+02:00", phenomenon="Altas temperaturas",
            ),
            _silver_aviso_record(
                "Madrid", "amarillo", "a2", "2026-08-14T15:00:00+02:00",
                effective_until="2026-08-14T21:00:00+02:00", phenomenon="Tormentas",
            ),
        ]

        gold = aggregate_avisos_silver_to_gold(records, self.processed_at)
        bucket = next(r for r in gold if r["zone"] == "Madrid" and r["level"] == "amarillo")

        self.assertEqual(bucket["phenomena"], ["Altas temperaturas", "Tormentas"])
        self.assertEqual(bucket["first_effective_from"], "2026-08-14T13:00:00+02:00")
        self.assertEqual(bucket["last_effective_until"], "2026-08-14T21:00:00+02:00")

    def test_records_without_zone_level_or_effective_from_are_ignored(self):
        record = _silver_aviso_record(None, "amarillo", "a1", "2026-08-14T13:00:00+02:00")
        self.assertEqual(aggregate_avisos_silver_to_gold([record], self.processed_at), [])

    def test_empty_input_yields_empty_output(self):
        self.assertEqual(aggregate_avisos_silver_to_gold([], self.processed_at), [])


if __name__ == "__main__":
    unittest.main()
