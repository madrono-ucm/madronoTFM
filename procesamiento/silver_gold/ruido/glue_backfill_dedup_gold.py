"""Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
`ruido` (tarea 077, mismo patrón que
`procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).

**No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
tarea 053/076), que solo lee una ventana de los últimos
`ROLLING_WINDOW_DAYS` días y escribe únicamente la fila de HOY (`append`).
Este job existe para recalcular Gold desde cero tras la reconstrucción
deduplicada de Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el
histórico de Silver de una vez, calcula la media móvil de 7 días con la
MISMA lógica de ventana de calendario (`Window.rangeBetween` sobre
`date_epoch_days`, ver docstring de `glue_silver_to_gold.py`) pero sobre el
histórico completo en vez de una ventana de 8 días, y escribe TODAS las
filas resultantes (no solo la de hoy) con `overwrite` en vez de `append` --
a diferencia del pipeline incremental, aquí no hay "días ya escritos en
ejecuciones anteriores" que evitar duplicar: es una reconstrucción total de
una sola vez.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen completo, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/ruido_por_estacion_periodo_fecha/`.
"""

from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

MADRID_TZ = ZoneInfo("Europe/Madrid")

ROLLING_WINDOW_DAYS = 7


def main() -> None:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # A diferencia del pipeline incremental, este job de un solo uso lee TODO
    # el histórico de Silver de una vez -- necesario para calcular
    # correctamente la media móvil de todos los días, no solo los últimos 8.
    silver_df = spark.read.parquet(args["silver_path"])

    daily_df = silver_df.groupBy("station_id", "period", "measured_date").agg(
        F.count(F.lit(1)).alias("samples_count"),
        F.first("station_name", ignorenulls=True).alias("station_name"),
        F.first("period_name", ignorenulls=True).alias("period_name"),
        F.first("district", ignorenulls=True).alias("district"),
        F.first("neighbourhood", ignorenulls=True).alias("neighbourhood"),
        F.avg("laeq_db").alias("avg_laeq_db"),
        F.max("laeq_db").alias("max_laeq_db"),
        F.min("laeq_db").alias("min_laeq_db"),
        F.avg("l1_db").alias("avg_l1_db"),
        F.avg("l10_db").alias("avg_l10_db"),
        F.avg("l50_db").alias("avg_l50_db"),
        F.avg("l90_db").alias("avg_l90_db"),
        F.avg("l99_db").alias("avg_l99_db"),
        F.first("location.lat", ignorenulls=True).alias("lat"),
        F.first("location.lon", ignorenulls=True).alias("lon"),
        F.first("location.altitude_m", ignorenulls=True).alias("altitude_m"),
    )

    daily_df = daily_df.withColumn(
        "date_epoch_days", F.datediff(F.to_date("measured_date"), F.lit("1970-01-01"))
    )

    rolling_window = (
        Window.partitionBy("station_id", "period")
        .orderBy("date_epoch_days")
        .rangeBetween(-(ROLLING_WINDOW_DAYS - 1), 0)
    )

    gold_df = (
        daily_df.withColumn("laeq_rolling_7d_avg_db", F.avg("avg_laeq_db").over(rolling_window))
        .withColumn("laeq_rolling_7d_days", F.count("avg_laeq_db").over(rolling_window))
        .drop("date_epoch_days")
        .withColumnRenamed("measured_date", "date")
        .withColumn("schema_version", F.lit(1))
        .withColumn("processed_at", F.lit(processed_at.isoformat()))
    )

    # `overwrite`, no `append`: este job reconstruye Gold desde cero, con
    # TODAS las filas (no solo la de hoy, a diferencia del pipeline
    # incremental) -- el prefijo de destino debe estar vacío antes de
    # lanzarlo.
    gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
