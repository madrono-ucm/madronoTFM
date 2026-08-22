"""Job de AWS Glue: Silver -> Gold del dataset `meteorologia` (valor medio/máx/mín por
estación, magnitud y hora).

**No ejecutado en esta tarea** (mismas condiciones que
`glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).

A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
`aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
través de múltiples particiones/ficheros de Silver necesita las primitivas
nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
expresiones de Spark de este job están escritas para producir exactamente el
mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
en uno debe reflejarse en el otro.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/meteorologia/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/meteorologia_por_estacion_magnitud_hora/`.
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

from procesamiento.silver_gold.incremental import (
    hourly_partition_uri,
    partition_has_objects,
    previous_hour,
)

MADRID_TZ = ZoneInfo("Europe/Madrid")


def main() -> None:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    fecha, hora = previous_hour(processed_at)
    silver_partition_path = hourly_partition_uri(args["silver_path"], fecha, hora)
    if not partition_has_objects(boto3.client("s3"), silver_partition_path):
        job.commit()
        return

    # `fecha`/`hora` son columnas de partición de Silver (ver
    # glue_bronze_to_silver.py); al narrowear la lectura a una única
    # partición (tarea 072), Spark ya no las infiere de la ruta -- se
    # recalculan aquí desde `measured_at`, la misma columna que las originó.
    silver_df = (
        spark.read.parquet(silver_partition_path)
        .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
        .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
    )

    # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
    # glue_bronze_to_silver.py); agrupar por ellas permite a Spark aprovechar
    # partition pruning si `silver_path` acota un rango de fechas concreto.
    # `magnitude` entra en la clave de agrupación (a diferencia de tráfico/
    # transporte_publico_emt/bicimad/aparcamientos): una misma estación
    # reporta varias magnitudes a la vez, ver docstring de `aggregate.py`.
    gold_df = (
        silver_df.groupBy("station_id", "magnitude", "fecha", "hora")
        .agg(
            F.count(F.lit(1)).alias("samples_count"),
            F.first("station_name", ignorenulls=True).alias("station_name"),
            F.min("measured_at").alias("first_measured_at"),
            F.max("measured_at").alias("last_measured_at"),
            F.avg("value").alias("avg_value"),
            F.max("value").alias("max_value"),
            F.min("value").alias("min_value"),
            F.first("location.lat", ignorenulls=True).alias("lat"),
            F.first("location.lon", ignorenulls=True).alias("lon"),
            F.first("location.altitude_m", ignorenulls=True).alias("altitude_m"),
        )
        .withColumnRenamed("fecha", "date")
        .withColumn("hour", F.col("hora").cast("int"))
        .drop("hora")
        .withColumn("schema_version", F.lit(1))
        .withColumn("processed_at", F.lit(processed_at.isoformat()))
    )

    # Gold es órdenes de magnitud más pequeño que Silver (una fila por
    # estación, magnitud y hora, no cada ~20 minutos): particionar solo por
    # `date` es suficiente para podar particiones sin generar ficheros
    # diminutos.
    gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
