"""Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
`cams_calidad_aire` (tarea 077, mismo patrón que
`procesamiento/silver_gold/bicimad/glue_backfill_dedup_gold.py`, tarea 074).

**No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
tarea 076), que solo procesa la partición `fecha=hoy` de Silver. Este job
existe para recalcular Gold desde cero tras la reconstrucción deduplicada de
Silver (`glue_backfill_dedup.py`, misma tarea): lee TODO el histórico de
Silver de una vez y agrega, en vez de una sola partición diaria.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen completo, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/cams_calidad_aire/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/cams_calidad_aire_por_contaminante_fecha_validez/`.
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

    silver_with_fecha_validez = silver_df.withColumn(
        "fecha_validez", F.date_format(F.to_timestamp("valid_datetime"), "yyyy-MM-dd")
    )

    gold_df = (
        silver_with_fecha_validez.groupBy("pollutant", "fecha_validez")
        .agg(
            F.first("pollutant_code", ignorenulls=True).alias("pollutant_code"),
            F.first("unit", ignorenulls=True).alias("unit"),
            F.count(F.lit(1)).alias("samples_count"),
            F.avg("value").alias("avg_value"),
            F.max("value").alias("max_value"),
            F.sort_array(F.collect_set("leadtime_hour")).alias("leadtime_hours"),
            F.min("forecast_issued_at").alias("first_forecast_issued_at"),
            F.max("forecast_issued_at").alias("last_forecast_issued_at"),
        )
        .withColumn("schema_version", F.lit(1))
        .withColumn("processed_at", F.lit(processed_at.isoformat()))
    )

    # `overwrite`, no `append`: este job reconstruye Gold desde cero. El
    # prefijo de destino debe estar vacío antes de lanzarlo.
    gold_df.write.mode("overwrite").partitionBy("pollutant").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
