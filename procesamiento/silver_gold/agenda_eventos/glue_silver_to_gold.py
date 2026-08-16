"""Job de AWS Glue: Silver -> Gold del dataset `agenda_eventos` (número de
eventos por categoría, distrito y día de celebración).

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
  `s3://madrono-tfm-dev-silver-222234418587/agenda_eventos/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/agenda_eventos_por_categoria_distrito_fecha/`.
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

UNKNOWN_CATEGORY = "__sin_categoria__"
UNKNOWN_DISTRICT = "__sin_distrito__"


def main() -> None:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    silver_df = spark.read.parquet(args["silver_path"])

    # `category`/`district` ausentes se agrupan bajo un sentinela en vez de
    # descartarse -- mismo criterio que `aggregate.py` (ver docstring de ese
    # módulo).
    normalized_df = silver_df.withColumn(
        "category_key", F.coalesce(F.col("category"), F.lit(UNKNOWN_CATEGORY))
    ).withColumn("district_key", F.coalesce(F.col("district"), F.lit(UNKNOWN_DISTRICT)))

    # `fecha` ya es una columna de partición física de Silver (derivada de
    # `start_datetime`, ver glue_bronze_to_silver.py); agrupar por ella
    # permite a Spark aprovechar partition pruning si `silver_path` acota un
    # rango de fechas concreto.
    gold_df = (
        normalized_df.groupBy("category_key", "district_key", "fecha")
        .agg(
            F.count(F.lit(1)).alias("samples_count"),
            F.countDistinct("event_id").alias("events_count"),
            F.countDistinct(F.when(F.col("free") == True, F.col("event_id"))).alias(  # noqa: E712
                "free_events_count"
            ),
            F.sort_array(F.collect_set("source")).alias("sources"),
            F.min("start_datetime").alias("first_start_datetime"),
            F.max("start_datetime").alias("last_start_datetime"),
        )
        .withColumnRenamed("category_key", "category")
        .withColumnRenamed("district_key", "district")
        .withColumnRenamed("fecha", "date")
        .withColumn("schema_version", F.lit(1))
        .withColumn("processed_at", F.lit(processed_at.isoformat()))
    )

    # Gold es órdenes de magnitud más pequeño que Silver (una fila por
    # categoría, distrito y día, no una por evento): particionar solo por
    # `date` es suficiente para podar particiones sin generar ficheros
    # diminutos.
    gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
