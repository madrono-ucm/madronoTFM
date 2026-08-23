"""Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
`agenda_eventos` (tarea 077, mismo patrón que
`procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).

**No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
tarea 056/076), que solo procesa la partición `fecha=hoy` de Silver. Este
job existe para recalcular Gold desde cero tras la reconstrucción
deduplicada de Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el
histórico de Silver de una vez y agrega, en vez de una sola partición diaria.
Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía trigger ni
schedule.

A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
`dropDuplicates`: parte de un Silver que el propio backfill de Silver ya dejó
sin duplicados (`event_id` único) -- lo que hace este job es la misma
agregación de producción de `glue_silver_to_gold.py`, solo que sobre todo el
histórico en vez de una única partición diaria, y escribiendo con
`overwrite` en vez de `append` (el prefijo de destino debe borrarse a mano
antes de lanzarlo, igual que Silver).

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen completo, p.ej.
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
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # A diferencia del pipeline incremental, este job de un solo uso lee TODO
    # el histórico de Silver de una vez -- exactamente lo que necesita una
    # reconstrucción completa de Gold.
    silver_df = spark.read.parquet(args["silver_path"])

    normalized_df = silver_df.withColumn(
        "category_key", F.coalesce(F.col("category"), F.lit(UNKNOWN_CATEGORY))
    ).withColumn("district_key", F.coalesce(F.col("district"), F.lit(UNKNOWN_DISTRICT)))

    # Misma agregación que el pipeline de producción
    # (`glue_silver_to_gold.py`): una fila por categoría/distrito/día.
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

    # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
    # prefijo de destino debe estar vacío antes de lanzarlo (mismo criterio
    # que `glue_backfill_dedup.py` para Silver).
    gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
