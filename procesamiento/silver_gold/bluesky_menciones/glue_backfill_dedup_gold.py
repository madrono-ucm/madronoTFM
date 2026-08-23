"""Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
`bluesky_menciones` (tarea 077, mismo patrón que
`procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).

**No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
tarea 057/076), que solo procesa la partición `fecha=hoy` de Silver. Este
job existe para recalcular Gold desde cero tras la reconstrucción
deduplicada de Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el
histórico de Silver de una vez y agrega, en vez de una sola partición diaria.
Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía trigger ni
schedule.

A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
`dropDuplicates`: parte de un Silver que el propio backfill de Silver ya dejó
sin duplicados (`post_hash` único) -- lo que hace este job es la misma
agregación de producción de `glue_silver_to_gold.py`, solo que sobre todo el
histórico en vez de una única partición diaria, y escribiendo con
`overwrite` en vez de `append`.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen completo, p.ej.
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
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    silver_df = spark.read.parquet(args["silver_path"])

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

    # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
    # prefijo de destino debe estar vacío antes de lanzarlo.
    gold_df.write.mode("overwrite").partitionBy("date").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
