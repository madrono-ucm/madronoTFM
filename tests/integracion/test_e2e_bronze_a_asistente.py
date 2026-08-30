"""Test de integración end-to-end (`FIL_18`): un registro Bronze acaba
siendo una respuesta coherente del asistente.

Recorre, **sin AWS ni Spark reales**, la cadena completa:

    fixture Bronze
      -> procesamiento.silver_gold.<ds>.transform.bronze_to_silver   (puerta de calidad)
      -> procesamiento.silver_gold.<ds>.aggregate.aggregate_silver_to_gold
      -> _aplanar_gold_*  (réplica de la proyección .select() del job de Glue)
      -> doble de Athena que sirve esas filas Gold
      -> [tráfico] doble de Neo4j con un sub-grafo estación<->lugar
      -> tool del asistente (calidad_aire / calidad_aire_prevista / trafico_cercano)
      -> aserción sobre la respuesta

Qué NO cubre (queda para §7.5 / verificación manual): el runtime Spark real
de los jobs de Glue (aquí se usa la lógica Python pura equivalente, ver
`procesamiento/README.md`), Athena/Neo4j reales, y el `.select()`/cast de
Spark (sustituido por `_aplanar_gold_*`).
"""

from __future__ import annotations

import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from asistente.mcp_agent import tools
from procesamiento.silver_gold.calidad_aire import aggregate as ca_agg
from procesamiento.silver_gold.calidad_aire import transform as ca_tr
from procesamiento.silver_gold.trafico import aggregate as tf_agg
from procesamiento.silver_gold.trafico import transform as tf_tr

_MADRID = timezone(timedelta(hours=2))
_PROCESSED_AT = datetime(2026, 8, 20, 13, 0, tzinfo=_MADRID)


# --------------------------------------------------------------------------
# Dobles de infraestructura
# --------------------------------------------------------------------------
class GoldAthenaDouble:
    """Sustituye a `run_athena_query`: parsea el `WHERE` de las consultas que
    lanzan las tools (filtro `date`, `LIKE` de estación, `point_id IN (...)`)
    y devuelve las filas Gold en memoria que casan -- ya como `list[dict]`
    con tipos nativos, igual que `asistente.athena.run_athena_query`."""

    def __init__(self, tablas: "dict[str, list[dict]]"):
        self.tablas = tablas
        self.consultas: "list[str]" = []

    def __call__(self, sql, database, *, athena_client=None):
        self.consultas.append(sql)
        tabla = re.search(r"FROM\s+(\S+)", sql).group(1).split(".")[-1].strip('"')
        filas = self.tablas.get(tabla, [])

        fechas = set(re.findall(r"'(\d{4}-\d{2}-\d{2})'", sql))
        like = re.search(r"LIKE\s+'%([^%']*)%'", sql)
        termino = like.group(1).lower() if like else None
        pid_in = re.search(r"point_id\s+IN\s*\(([^)]*)\)", sql)
        pids = {p.strip().strip("'") for p in pid_in.group(1).split(",")} if pid_in else None

        out = []
        for fila in filas:
            if fechas and str(fila.get("date")) not in fechas:
                continue
            if termino is not None:
                nombre = (fila.get("station_name") or "").lower()
                ident = (fila.get("station_id") or "").lower()
                if termino not in nombre and termino not in ident:
                    continue
            if pids is not None and str(fila.get("point_id")) not in pids:
                continue
            out.append(dict(fila))
        return out


class Neo4jGraphDouble:
    """Sustituye a `run_neo4j_query` para `lugares_proximos_a_estaciones_*`:
    resuelve `$nombre_lugar` (CONTAINS, case-insensitive) y filtra por
    `distancia_m <= $radio_m` sobre un sub-grafo en memoria."""

    def __init__(self, aristas: "list[dict]"):
        self.aristas = aristas

    def __call__(self, query, params, *, driver=None):
        termino = params["nombre_lugar"].lower()
        radio = params["radio_m"]
        return [
            {
                "lugar_id": a["lugar_id"],
                "lugar_nombre": a["lugar_nombre"],
                "estacion_id": a["estacion_id"],
                "distancia_m": a["distancia_m"],
            }
            for a in self.aristas
            if termino in a["lugar_nombre"].lower() and a["distancia_m"] <= radio
        ]


# --------------------------------------------------------------------------
# Fixtures Bronze + cadena transform -> aggregate -> aplanado
# --------------------------------------------------------------------------
def _bronze_calidad_aire() -> "list[dict]":
    """31 lecturas horarias de NO2 en una estación (2026-08-19 06:00 ->
    2026-08-20 12:00) + 1 lectura corrupta (PM10 negativo) que la puerta de
    calidad debe rechazar."""
    inicio = datetime(2026, 8, 19, 6, 0, tzinfo=_MADRID)
    registros = []
    for k in range(31):
        t = inicio + timedelta(hours=k)
        registros.append({
            "schema_version": 1, "source": "madrid_calidad_aire",
            "station_id": "28079004", "station_name": "Plaza de España",
            "station_address": "Plaza de España", "magnitude_code": "08",
            "magnitude_abbr": "NO2", "magnitude_name": "Dióxido de Nitrógeno",
            "unit": "µg/m³", "value": 60.0 + (k % 6) * 8.0,
            "measured_at": t.isoformat(),
            "ingested_at": (t + timedelta(minutes=20)).isoformat(),
            "location": {"lat": 40.4239, "lon": -3.7128, "srid": "EPSG:4326"},
        })
    registros.append({  # corrupto: se rechaza en validate_record
        "schema_version": 1, "source": "madrid_calidad_aire",
        "station_id": "28079004", "station_name": "Plaza de España",
        "station_address": "Plaza de España", "magnitude_code": "10",
        "magnitude_abbr": "PM10", "magnitude_name": "Partículas < 10 µm",
        "unit": "µg/m³", "value": -5.0,
        "measured_at": datetime(2026, 8, 20, 12, 0, tzinfo=_MADRID).isoformat(),
        "ingested_at": datetime(2026, 8, 20, 12, 20, tzinfo=_MADRID).isoformat(),
        "location": {"lat": 40.4239, "lon": -3.7128, "srid": "EPSG:4326"},
    })
    return registros


def _aplanar_gold_calidad_aire(filas: "list[dict]") -> "list[dict]":
    """Réplica de la proyección del job de Glue silver->gold de calidad_aire
    (`.select(...).withColumnRenamed("fecha","date")` + `location.lat` ->
    `lat`): sube lat/lon al nivel superior. El resto de columnas que leen
    las tools ya salen así de `aggregate_silver_to_gold`."""
    aplanadas = []
    for f in filas:
        loc = f.get("location") or {}
        g = {k: v for k, v in f.items() if k != "location"}
        g["lat"] = loc.get("lat")
        g["lon"] = loc.get("lon")
        aplanadas.append(g)
    return aplanadas


def _bronze_trafico() -> "list[dict]":
    """26 lecturas horarias de un punto de tráfico (service_level creciente)
    + 1 lectura de un sensor en error (`has_error`) que se rechaza."""
    inicio = datetime(2026, 8, 19, 11, 0, tzinfo=_MADRID)
    registros = []
    for k in range(26):
        t = inicio + timedelta(hours=k)
        registros.append({
            "schema_version": 1, "source": "madrid_trafico_intensidad",
            "point_id": "3001", "measured_at": t.isoformat(),
            "ingested_at": (t + timedelta(minutes=2)).isoformat(),
            "description": "Punto 3001", "access_code": "0301", "subarea": "Retiro",
            "intensity_vph": 800 + k * 10, "occupancy_pct": 10 + (k % 5) * 3,
            "load_pct": 18 + (k % 5) * 4, "service_level": min(4, k // 7),
            "saturation_intensity_vph": 3000, "has_error": False, "error_code": "N",
            "location": {"x": 441000.0, "y": 4474000.0, "srid": "EPSG:25830"},
        })
    registros.append({
        "schema_version": 1, "source": "madrid_trafico_intensidad",
        "point_id": "3001",
        "measured_at": datetime(2026, 8, 20, 13, 0, tzinfo=_MADRID).isoformat(),
        "ingested_at": datetime(2026, 8, 20, 13, 2, tzinfo=_MADRID).isoformat(),
        "description": "Punto 3001", "access_code": "0301", "subarea": "Retiro",
        "intensity_vph": 950, "occupancy_pct": 20, "load_pct": 30,
        "service_level": 1, "saturation_intensity_vph": 3000,
        "has_error": True, "error_code": "E",
        "location": {"x": 441000.0, "y": 4474000.0, "srid": "EPSG:25830"},
    })
    return registros


def _aplanar_gold_trafico(filas: "list[dict]") -> "list[dict]":
    aplanadas = []
    for f in filas:
        loc = f.get("location") or {}
        g = {k: v for k, v in f.items() if k != "location"}
        g["lat"] = loc.get("lat")
        g["lon"] = loc.get("lon")
        aplanadas.append(g)
    return aplanadas


def _cadena_calidad_aire():
    bronze = _bronze_calidad_aire()
    silver, rechazados = ca_tr.bronze_to_silver(bronze, _PROCESSED_AT)
    gold = ca_agg.aggregate_silver_to_gold(silver, _PROCESSED_AT)
    return silver, rechazados, _aplanar_gold_calidad_aire(gold)


def _cadena_trafico():
    bronze = _bronze_trafico()
    silver, rechazados = tf_tr.bronze_to_silver(bronze, _PROCESSED_AT)
    gold = tf_agg.aggregate_silver_to_gold(silver, _PROCESSED_AT)
    return silver, rechazados, _aplanar_gold_trafico(gold)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
class CalidadAireE2ETests(unittest.TestCase):
    def test_bronze_llega_a_respuesta_de_calidad_aire(self):
        _silver, _rech, gold = _cadena_calidad_aire()
        doble = GoldAthenaDouble({"calidad_aire_por_estacion_contaminante_hora": gold})

        momento = datetime(2026, 8, 20, 12, 0, tzinfo=_MADRID)
        with patch("asistente.mcp_agent.tools.run_athena_query", doble):
            r = tools.calidad_aire("españa", momento)

        self.assertEqual(r.contaminante_principal, "NO2")
        self.assertEqual(r.hora, 12)
        # hora 12: 2026-08-19T12 (k=6 -> 60) y 2026-08-20T12 (k=30 -> 60) => avg 60
        self.assertAlmostEqual(r.valor, 60.0, places=6)
        self.assertEqual(r.unidad, "µg/m³")
        self.assertIn("Plaza de España", r.estaciones_consultadas)
        self.assertIn(r.indice_calidad, ("buena", "regular", "mala", "muy mala"))
        self.assertTrue(doble.consultas, "la tool no llegó a consultar Athena")

    def test_puerta_de_calidad_descarta_el_registro_corrupto(self):
        _silver, rechazados, gold = _cadena_calidad_aire()
        motivos = [m for r in rechazados for m in r["reasons"]]
        self.assertIn("value_negative", motivos)
        # el PM10 corrupto era la única lectura de ese contaminante -> no hay
        # ninguna fila Gold de PM10
        self.assertEqual([g for g in gold if g["pollutant"] == "PM10"], [])

        doble = GoldAthenaDouble({"calidad_aire_por_estacion_contaminante_hora": gold})
        with patch("asistente.mcp_agent.tools.run_athena_query", doble):
            r = tools.calidad_aire("españa", datetime(2026, 8, 20, 12, 0, tzinfo=_MADRID))
        self.assertNotEqual(r.contaminante_principal, "PM10")

    def test_bronze_llega_a_prevision_desde_onnx(self):
        _silver, _rech, gold = _cadena_calidad_aire()
        doble = GoldAthenaDouble({"calidad_aire_por_estacion_contaminante_hora": gold})

        momento = datetime(2026, 8, 20, 12, 0, tzinfo=_MADRID)
        with patch("asistente.mcp_agent.tools.run_athena_query", doble):
            r = tools.calidad_aire_prevista("españa", 3, momento)

        self.assertTrue(r.disponible)
        self.assertIsNotNone(r.valor_previsto)
        self.assertEqual(r.contaminante, "NO2")
        self.assertIn("calidad_aire_h3.onnx", r.modelo)
        self.assertIsNotNone(r.ventana_datos)
        self.assertGreaterEqual(r.data_completeness, 0.8)
        self.assertEqual(r.momento_objetivo, r.momento + timedelta(hours=3))


class TraficoGrafoE2ETests(unittest.TestCase):
    def test_bronze_cruza_el_grafo_y_llega_a_trafico_cercano(self):
        _silver, rechazados, gold = _cadena_trafico()
        self.assertIn("sensor_reports_error", [m for r in rechazados for m in r["reasons"]])

        athena = GoldAthenaDouble({"trafico_por_punto_hora": gold})
        grafo = Neo4jGraphDouble([{
            "lugar_id": "lugar:retiro", "lugar_nombre": "Parque del Retiro",
            "estacion_id": "trafico:3001", "distancia_m": 80.0,
        }])

        momento = datetime(2026, 8, 20, 12, 0, tzinfo=_MADRID)
        with patch("asistente.mcp_agent.tools.run_athena_query", athena), \
             patch("asistente.mcp_agent.tools.run_neo4j_query", grafo):
            r = tools.trafico_cercano("retiro", 300.0, momento)

        self.assertEqual([e.point_id for e in r.estaciones], ["3001"])
        self.assertEqual(r.estaciones[0].distancia_m, 80.0)
        self.assertIsNotNone(r.estaciones[0].avg_service_level)
        self.assertIn(r.resumen, ("fluido", "denso", "congestionado"))

    def test_lugar_fuera_de_radio_no_devuelve_estaciones(self):
        _s, _r, gold = _cadena_trafico()
        athena = GoldAthenaDouble({"trafico_por_punto_hora": gold})
        grafo = Neo4jGraphDouble([{
            "lugar_id": "lugar:retiro", "lugar_nombre": "Parque del Retiro",
            "estacion_id": "trafico:3001", "distancia_m": 500.0,  # > radio
        }])
        with patch("asistente.mcp_agent.tools.run_athena_query", athena), \
             patch("asistente.mcp_agent.tools.run_neo4j_query", grafo):
            r = tools.trafico_cercano("retiro", 300.0, datetime(2026, 8, 20, 12, 0, tzinfo=_MADRID))
        self.assertEqual(r.resumen, "sin_datos")


class EslabonRotoTests(unittest.TestCase):
    """Si se rompe un eslabón, el test debe caer -- comprobado saltándose el
    paso de agregación (se sirven filas Silver, sin `avg_value`)."""

    def test_sin_agregacion_la_tool_no_encuentra_datos(self):
        silver, _rech, _gold = _cadena_calidad_aire()
        # Silver aplanado, SIN pasar por aggregate_silver_to_gold:
        crudo = _aplanar_gold_calidad_aire([
            {**s, "date": "2026-08-20", "hour": 12} for s in silver
        ])
        doble = GoldAthenaDouble({"calidad_aire_por_estacion_contaminante_hora": crudo})
        with patch("asistente.mcp_agent.tools.run_athena_query", doble):
            r = tools.calidad_aire("españa", datetime(2026, 8, 20, 12, 0, tzinfo=_MADRID))
        # sin `avg_value` en las filas, la tool no puede clasificar
        self.assertEqual(r.indice_calidad, "sin_datos")


if __name__ == "__main__":
    unittest.main()
