"""Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
`calidad_aire`.

**No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
tarea 049/072), que solo procesa la partición horaria anterior a la
ejecución. Este job existe para recalcular Gold desde cero tras la
reconstrucción deduplicada de Silver (`glue_backfill_dedup.py`, tarea 075):
lee TODO el histórico de Silver de una vez y agrega, en vez de una sola
hora. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
trigger ni schedule. Ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`.

A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
`dropDuplicates`: parte de un Silver que la propia tarea 075 ya dejó sin
duplicados (`(station_id, magnitude_code, measured_at)` único) -- lo que
hace este job es la misma agregación de producción de
`glue_silver_to_gold.py`, solo que sobre todo el histórico en vez de una
única partición horaria, y escribiendo con `overwrite` en vez de `append`
(el prefijo de destino debe borrarse a mano antes de lanzarlo, igual que
Silver).

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen completo, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/calidad_aire/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/calidad_aire_por_estacion_contaminante_hora/`.
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
    # Mismo motivo que el resto de jobs del patrón (tarea 072): sin esto,
    # `fecha`/`hora` se recalcularían en UTC (timezone de sesión por defecto
    # de Spark en el runtime de Glue) en vez de Europe/Madrid.
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # A diferencia del pipeline incremental, este job de un solo uso lee TODO
    # el histórico de Silver de una vez -- exactamente lo que necesita una
    # reconstrucción completa de Gold.
    silver_df = (
        spark.read.parquet(args["silver_path"])
        .withColumn("fecha", F.date_format(F.to_timestamp("measured_at"), "yyyy-MM-dd"))
        .withColumn("hora", F.date_format(F.to_timestamp("measured_at"), "HH"))
    )

    # Misma agregación que el pipeline de producción
    # (`glue_silver_to_gold.py`): una fila por estación/contaminante/fecha/
    # hora.
    gold_df = (
        silver_df.groupBy("station_id", "pollutant", "fecha", "hora")
        .agg(
            F.count(F.lit(1)).alias("samples_count"),
            F.first("station_name", ignorenulls=True).alias("station_name"),
            F.first("magnitude_code", ignorenulls=True).alias("magnitude_code"),
            F.first("pollutant_name", ignorenulls=True).alias("pollutant_name"),
            F.first("unit", ignorenulls=True).alias("unit"),
            F.min("measured_at").alias("first_measured_at"),
            F.max("measured_at").alias("last_measured_at"),
            F.avg("value").alias("avg_value"),
            F.max("value").alias("max_value"),
            F.min("value").alias("min_value"),
            F.first("location.lat", ignorenulls=True).alias("lat"),
            F.first("location.lon", ignorenulls=True).alias("lon"),
        )
        .withColumnRenamed("fecha", "date")
        .withColumn("hour", F.col("hora").cast("int"))
        .drop("hora")
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
