"""Job de AWS Glue: Silver -> Gold del dataset `ruido` (resumen diario por
estación y periodo, más media móvil de 7 días de LAeq).

**No ejecutado en esta tarea** (mismas condiciones que
`glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).

A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
`aggregate.py` en tiempo de ejecución: una agregación `groupBy` + ventana
correcta a través de múltiples particiones/ficheros de Silver necesita las
primitivas nativas de reduce/window distribuido de Spark, no un
`mapPartitions` fila a fila -- mismo motivo que el resto de datasets del
patrón. `aggregate.py` sigue siendo la fuente de verdad **documental y de
test** de qué agrega Gold (incluida la media móvil de 7 días, ver su
docstring para el razonamiento completo); las expresiones de Spark de este
job están escritas para producir exactamente el mismo esquema de salida que
`aggregate.aggregate_silver_to_gold`; un cambio en uno debe reflejarse en el
otro.

La media móvil usa `Window.rangeBetween` (no `rowsBetween`) sobre
`date_epoch_days` (días desde 1970-01-01, columna numérica auxiliar) para
que la ventana sea de **calendario** (día actual - 6 días hasta día actual),
no de "últimas 7 filas" -- un hueco de fin de semana/festivo (la Red Fija
del SIVCA no publica esos días) reduce cuántos días reales entran en la
ventana en vez de desplazarla, igual que hace `aggregate.py` en Python puro.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen, p.ej.
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
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    silver_df = spark.read.parquet(args["silver_path"])

    # Resumen diario por estación+periodo+día -- ver docstring de
    # `aggregate.py` para el porqué de esta clave (la fuente ya es diaria,
    # no hay ninguna hora que agregar).
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

    # Columna numérica auxiliar para poder usar `rangeBetween` (ventana de
    # calendario, no de "últimas N filas") -- ver docstring del módulo.
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

    # Gold es órdenes de magnitud más pequeño que Silver (una fila por
    # estación, periodo y día, no varias lecturas): particionar solo por
    # `date` es suficiente para podar particiones sin generar ficheros
    # diminutos.
    gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
