"""Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de `bicimad`.

**NO es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
(tarea 041/047, arreglado en la tarea 072) calcula internamente una única
hora/partición concreta a procesar (la anterior a la ejecución) -- no acepta
un `--bronze_path` que apunte a "todo el histórico", así que no sirve para
reconstruir Silver desde cero. Este script existe únicamente para eso: leer
TODO el histórico de Bronze de una vez y deduplicar de verdad, tras varios
intentos previos de limpieza manual (borrado + relanzar el job de producción
o compactar) que dejaron el dato en estados intermedios inconsistentes --
duplicados masivos (`n=6752` para una fila) y fechas con huecos. Ver
`doc/073-limpieza-duplicados-bicimad-lanzar.md` para el detalle de esos
intentos. Se lanza una sola vez a mano (`aws glue start-job-run`), nunca vía
trigger ni schedule.

Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
lanzarlo (borrado manual con `aws s3 rm --recursive`, ver doc/073): este
script escribe con `mode("overwrite")`, no `append` -- si el prefijo no
está vacío de antemano, el resultado seguiría mezclando el dato viejo (ya
duplicado) con la reconstrucción.

Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
de Spark/GX que ya usa el pipeline de producción
(`glue_bronze_to_silver.py`): `SILVER_SCHEMA`, `_process_partition`,
`_with_consistency_columns`, `_write_quality_report`.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen completo, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/bicimad/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/bicimad/`.
- `quality_report_path`: prefijo S3 donde se escribe el informe de
  validación de Great Expectations (un JSON, igual que el pipeline de
  producción).
"""

from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import great_expectations as gx
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql.functions import date_format, to_timestamp

from procesamiento.silver_gold.bicimad.ge_suite import run_quality_report
from procesamiento.silver_gold.bicimad.glue_bronze_to_silver import (
    SILVER_SCHEMA,
    _process_partition,
    _with_consistency_columns,
    _write_quality_report,
)

MADRID_TZ = ZoneInfo("Europe/Madrid")


def main() -> None:
    args = getResolvedOptions(
        sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
    )

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    # Mismo motivo que el pipeline de producción (tarea 072): sin esto,
    # `date_format(to_timestamp(...), "HH")` calcula `hora` en el timezone
    # de sesión por defecto de Spark (UTC en el runtime de Glue), desalineado
    # con la hora de Madrid real de `measured_at`.
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # A diferencia del pipeline incremental, este job de un solo uso lee TODO
    # el histórico de Bronze de una vez -- exactamente lo que necesita una
    # reconstrucción completa.
    bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])

    silver_rdd = bronze_df.rdd.mapPartitions(
        lambda rows: _process_partition(rows, processed_at.isoformat())
    )
    silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)

    # La deduplicación real que faltaba: intentos previos dejaron registros
    # repetidos miles de veces para la misma estación/instante. Un par
    # (station_id, measured_at) identifica de forma única una medición real
    # del feed GBFS.
    silver_df = silver_df.dropDuplicates(["station_id", "measured_at"])
    silver_df.cache()

    gx_context = gx.get_context(mode="ephemeral")
    quality_report = run_quality_report(gx_context, _with_consistency_columns(silver_df))
    report_key = (
        f"{args['quality_report_path'].rstrip('/')}/"
        f"bicimad_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
    )
    _write_quality_report(report_key, quality_report)

    # Mismo esquema de partición que el pipeline de producción (fecha=/hora=,
    # hora de Madrid).
    silver_partitioned = silver_df.withColumn(
        "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
    ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))

    # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
    # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
    # del módulo) -- `overwrite` aquí es una salvaguarda adicional, no un
    # sustituto de ese borrado previo.
    silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
        args["silver_path"]
    )

    job.commit()


if __name__ == "__main__":
    main()
