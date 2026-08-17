"""Job de AWS Glue: Silver -> Gold del dataset `bluesky_menciones` (número de
menciones por término de búsqueda, modo, día y hora).

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
  `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/bluesky_menciones_por_termino_modo_hora/`.
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

MADRID_TZ = ZoneInfo("Europe/Madrid")


def main() -> None:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    silver_df = spark.read.parquet(args["silver_path"])

    # `fecha`/`hora` ya son las columnas de partición físicas de Silver (ver
    # glue_bronze_to_silver.py); agrupar por ellas permite a Spark
    # aprovechar partition pruning si `silver_path` acota un rango de
    # fechas concreto. `mode`/`match_term` entran en la clave junto a
    # `fecha`/`hora` -- mismo criterio que `aggregate.py`.
    gold_df = (
        silver_df.groupBy("mode", "match_term", "fecha", "hora")
        .agg(
            F.count(F.lit(1)).alias("samples_count"),
            F.countDistinct("post_hash").alias("mentions_count"),
            F.sort_array(F.collect_set("lang")).alias("langs"),
            F.coalesce(F.sum("like_count"), F.lit(0)).alias("total_like_count"),
            F.coalesce(F.sum("repost_count"), F.lit(0)).alias("total_repost_count"),
            F.coalesce(F.sum("reply_count"), F.lit(0)).alias("total_reply_count"),
            F.coalesce(F.sum("quote_count"), F.lit(0)).alias("total_quote_count"),
            F.min("created_at").alias("first_created_at"),
            F.max("created_at").alias("last_created_at"),
        )
        .withColumnRenamed("fecha", "date")
        .withColumn("hour", F.col("hora").cast("int"))
        .drop("hora")
        .withColumn("schema_version", F.lit(1))
        .withColumn("processed_at", F.lit(processed_at.isoformat()))
    )

    # Gold es órdenes de magnitud más pequeño que Silver (una fila por
    # término/modo/hora, no una por post): particionar solo por `date` es
    # suficiente para podar particiones sin generar ficheros diminutos --
    # mismo criterio que el resto del patrón (trafico, cartelera_cines_estrenos...).
    gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
