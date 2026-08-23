"""Job de AWS Glue de UN SOLO USO: reconstrucción completa de Gold de
`transporte_publico_emt`.

**No es parte del pipeline de producción incremental** (`glue_silver_to_gold.py`,
tarea 046/072), que solo procesa la partición horaria anterior a la
ejecución. Este job existe para recalcular Gold desde cero tras la
reconstrucción deduplicada de Silver (`glue_backfill_dedup.py`, tarea 075):
lee TODO el histórico de Silver de una vez y agrega, en vez de una sola
hora. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
trigger ni schedule. Ver `doc/075-arreglo-lectura-incremental-glue-grupo-horario.md`.

A diferencia de `glue_backfill_dedup.py` (Silver), este job **no** necesita
`dropDuplicates`: parte de un Silver que la propia tarea 075 ya dejó sin
duplicados (`(stop_id, line, bus_id, ingested_at)` único) -- lo que hace
este job es la misma agregación de producción de `glue_silver_to_gold.py`,
solo que sobre todo el histórico en vez de una única partición horaria, y
escribiendo con `overwrite` en vez de `append` (el prefijo de destino debe
borrarse a mano antes de lanzarlo, igual que Silver).

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen completo, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/transporte_publico_emt/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/transporte_publico_emt_por_parada_hora/`.
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
        .withColumn("fecha", F.date_format(F.to_timestamp("ingested_at"), "yyyy-MM-dd"))
        .withColumn("hora", F.date_format(F.to_timestamp("ingested_at"), "HH"))
    )

    # Misma agregación que el pipeline de producción
    # (`glue_silver_to_gold.py`): una fila por parada/línea/fecha/hora.
    gold_df = (
        silver_df.groupBy("stop_id", "line", "fecha", "hora")
        .agg(
            F.count(F.lit(1)).alias("samples_count"),
            F.min("ingested_at").alias("first_ingested_at"),
            F.max("ingested_at").alias("last_ingested_at"),
            F.avg("estimate_arrive_sec").alias("avg_estimate_arrive_sec"),
            F.min("estimate_arrive_sec").alias("min_estimate_arrive_sec"),
            F.max("estimate_arrive_sec").alias("max_estimate_arrive_sec"),
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
