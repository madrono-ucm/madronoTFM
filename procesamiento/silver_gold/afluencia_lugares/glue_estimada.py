"""Job de AWS Glue (FIL_06 parte 2): materializa `afluencia_lugares` como
serie temporal Gold a partir de la señal **derivada** de sensores vía el
grafo Neo4j -- ya no hay Bronze/Silver de este dataset (Google Popular Times
retirado, parte 1).

Cada ejecución (horaria, ver `glue_scheduling.tf`):

1. Lee las credenciales de Neo4j de SSM (`--neo4j_*_param`, `SecureString`).
2. Una consulta a Neo4j: por cada `:Lugar`, sus sensores `PROXIMO_A`
   (`:EstacionMedida` de trafico/ruido/calidad_aire, `:ParadaTransporte` de
   bicimad) con la distancia.
3. Lee la partición Gold de hoy de las 4 tablas de sensores (Parquet directo
   con Spark) y se queda con el valor de la hora objetivo por estación.
4. `estimada.fila_gold` por lugar (fórmula de `nivel.py`, compartida con la
   tool en vivo del asistente).
5. Escribe Parquet en `gold/afluencia_lugares_por_lugar_fecha_hora/
   date=<fecha>/hora=<hora>/` (`overwrite` dinámico -> re-ejecutar la misma
   hora es idempotente, no duplica).

`--additional-python-modules "neo4j>=5,<6"` (ver `glue.tf`). El job NO está
en VPC, así que tiene salida a Internet para el `neo4j+s://` de AuraDB.

Args (`--<nombre>`, ver `glue.tf`):
  JOB_NAME, gold_path,
  neo4j_uri_param, neo4j_user_param, neo4j_pass_param, neo4j_db_param,
  trafico_gold_path, ruido_gold_path, bicimad_gold_path, calidad_aire_gold_path
"""

from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from procesamiento.silver_gold.afluencia_lugares.estimada import fila_gold, sensores_por_tipo

MADRID_TZ = ZoneInfo("Europe/Madrid")

_LUGARES_CON_SENSORES = """
MATCH (l:Lugar)
OPTIONAL MATCH (l)-[p:PROXIMO_A]-(s)
WHERE s:EstacionMedida OR s:ParadaTransporte
WITH l, collect(
  CASE WHEN s IS NULL THEN NULL
  ELSE {id: s.id, tipo: s.tipo, distancia_m: p.distancia_m} END
) AS sensores
RETURN l.id AS id, l.tipo AS tipo,
       l.ubicacion.latitude AS lat, l.ubicacion.longitude AS lon,
       [x IN sensores WHERE x IS NOT NULL] AS sensores
"""


def _ssm_value(ssm, name: str) -> str:
    return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


def _leer_lugares(uri: str, user: str, password: str, database: str) -> "list[dict]":
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            return [r.data() for r in session.run(_LUGARES_CON_SENSORES)]
    finally:
        driver.close()


def _gold_por_estacion(
    spark: SparkSession, path: str, fecha: str, hora: int, id_col: str, valor_cols: "list[str]"
) -> "dict[str, dict]":
    """Lee `path/date=<fecha>/` y devuelve `{id_real: {col: valor}}` para la
    `hora` objetivo (o, si esa tabla no tiene columna `hour`, cualquier fila
    del día). `id_real` = valor de `id_col` (Gold ya lo guarda sin prefijo).
    """
    try:
        df = spark.read.parquet(f"{path.rstrip('/')}/date={fecha}/")
    except Exception:  # noqa: BLE001 -- partición del día aún sin escribir
        return {}
    cols = df.columns
    if "hour" in cols:
        df = df.filter(F.col("hour") == hora)
    seleccion = [id_col] + [c for c in valor_cols if c in cols]
    out: "dict[str, dict]" = {}
    for row in df.select(*seleccion).collect():
        rid = row[id_col]
        if rid is None:
            continue
        fila = {c: row[c] for c in valor_cols if c in cols}
        # calidad del aire: varias filas por estación (una por contaminante) --
        # quedarse con el peor `avg_value`.
        if rid in out and "avg_value" in fila:
            if (fila.get("avg_value") or -1) <= (out[rid].get("avg_value") or -1):
                continue
        out[rid] = fila
    return out


def main() -> None:
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "gold_path",
            "neo4j_uri_param",
            "neo4j_user_param",
            "neo4j_pass_param",
            "neo4j_db_param",
            "trafico_gold_path",
            "ruido_gold_path",
            "bicimad_gold_path",
            "calidad_aire_gold_path",
        ],
    )

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)
    fecha = processed_at.strftime("%Y-%m-%d")
    hora = processed_at.hour

    ssm = boto3.client("ssm")
    lugares = _leer_lugares(
        _ssm_value(ssm, args["neo4j_uri_param"]),
        _ssm_value(ssm, args["neo4j_user_param"]),
        _ssm_value(ssm, args["neo4j_pass_param"]),
        _ssm_value(ssm, args["neo4j_db_param"]),
    )

    valores_gold = {
        "trafico": _gold_por_estacion(
            spark, args["trafico_gold_path"], fecha, hora, "point_id",
            ["avg_service_level", "avg_occupancy_ratio"],
        ),
        "ruido": _gold_por_estacion(
            spark, args["ruido_gold_path"], fecha, hora, "station_id", ["avg_laeq_db"]
        ),
        "bicimad": _gold_por_estacion(
            spark, args["bicimad_gold_path"], fecha, hora, "station_id", ["avg_occupancy_ratio"]
        ),
        "calidad_aire": _gold_por_estacion(
            spark, args["calidad_aire_gold_path"], fecha, hora, "station_id", ["avg_value"]
        ),
    }

    filas = [
        fila_gold(
            lugar={"id": l["id"], "tipo": l.get("tipo"), "lat": l.get("lat"), "lon": l.get("lon")},
            sensores=sensores_por_tipo(l.get("sensores") or []),
            valores_gold=valores_gold,
            fecha=fecha,
            hora=hora,
            processed_at=processed_at,
        )
        for l in lugares
    ]

    if not filas:
        job.commit()
        return

    gold_df = spark.createDataFrame(filas)
    gold_df.write.mode("overwrite").partitionBy("date", "hora").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
