"""Job de AWS Glue: Bronze -> Silver del dataset `aemet_prevision_avisos`.

**No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
sin `terraform apply`, que el resto de datasets del patrón, ver
`procesamiento/README.md`): este script asume el entorno de ejecución real
de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
`great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
(esta EC2 de desarrollo no tiene Spark instalado).

Un único job procesa **las dos** formas de dato (previsión y avisos, ver
`transform.py`) porque comparten productor, credencial y cadencia de
scheduling real (ver `ingesta/README.md`, "Cadencia real de publicación") --
tal como pide el enunciado de esta tarea ("job de Glue x2": Bronze->Silver y
Silver->Gold, no cuatro jobs). Internamente son dos flujos Spark
independientes (dos lecturas, dos `mapPartitions`, dos escrituras), cada uno
reutilizando `transform.bronze_to_silver_prevision`/
`transform.bronze_to_silver_avisos` tal cual -- este módulo solo es el
"pegamento" de Spark/Glue.

**Para el informe de Great Expectations se escribe directamente a S3 vía
`boto3`** (`_write_quality_report`), NO con
`sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
producción en la tarea 051 (el runtime de Glue no trae la clase de
committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
`saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo). Se
escriben dos informes por ejecución (uno por forma de dato), bajo el mismo
prefijo `quality_report_path`.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_prevision_path` / `bronze_avisos_path`: prefijos S3 de origen,
  p.ej. `s3://madrono-tfm-dev-bronze-222234418587/aemet_prevision/` /
  `.../aemet_avisos/` -- dos prefijos reales y distintos, ver
  `transform.py`, "Prefijos S3 reales de Bronze".
- `silver_prevision_path` / `silver_avisos_path`: prefijos S3 de destino.
- `quality_report_path`: prefijo S3 donde se escriben los informes de
  validación de Great Expectations (dos JSON por ejecución del job, uno por
  forma de dato).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3
import great_expectations as gx
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import Row, SparkSession
from pyspark.sql.functions import date_format, to_timestamp
from pyspark.sql.types import DoubleType, IntegerType, StringType, StructField, StructType

from procesamiento.silver_gold.aemet_prevision_avisos.ge_suite import (
    run_avisos_quality_report,
    run_prevision_quality_report,
)
from procesamiento.silver_gold.aemet_prevision_avisos.transform import (
    bronze_to_silver_avisos,
    bronze_to_silver_prevision,
)

MADRID_TZ = ZoneInfo("Europe/Madrid")

SILVER_PREVISION_SCHEMA = StructType(
    [
        StructField("schema_version", IntegerType(), False),
        StructField("source", StringType(), True),
        StructField("municipio_code", StringType(), False),
        StructField("municipio_name", StringType(), True),
        StructField("province", StringType(), True),
        StructField("elaborated_at", StringType(), True),
        StructField("valid_date", StringType(), False),
        StructField("sky_state", StringType(), True),
        StructField("sky_state_code", StringType(), True),
        StructField("precipitation_probability_pct", DoubleType(), True),
        StructField("temperature_max_c", DoubleType(), True),
        StructField("temperature_min_c", DoubleType(), True),
        StructField("thermal_sensation_max_c", DoubleType(), True),
        StructField("thermal_sensation_min_c", DoubleType(), True),
        StructField("humidity_max_pct", DoubleType(), True),
        StructField("humidity_min_pct", DoubleType(), True),
        StructField("wind_direction", StringType(), True),
        StructField("wind_speed_kmh", DoubleType(), True),
        StructField("wind_gust_max_kmh", DoubleType(), True),
        StructField("uv_max", DoubleType(), True),
        StructField("ingested_at", StringType(), False),
        StructField("processed_at", StringType(), False),
    ]
)

SILVER_AVISOS_SCHEMA = StructType(
    [
        StructField("schema_version", IntegerType(), False),
        StructField("source", StringType(), True),
        StructField("identifier", StringType(), False),
        StructField("sent_at", StringType(), True),
        StructField("zone", StringType(), False),
        StructField("level", StringType(), False),
        StructField("phenomenon", StringType(), False),
        StructField("probability", StringType(), True),
        StructField("severity", StringType(), True),
        StructField("urgency", StringType(), True),
        StructField("certainty", StringType(), True),
        StructField("effective_from", StringType(), False),
        StructField("effective_until", StringType(), True),
        StructField("headline", StringType(), True),
        StructField("description", StringType(), True),
        StructField("ingested_at", StringType(), False),
        StructField("processed_at", StringType(), False),
    ]
)


def _to_silver_prevision_row(r: dict) -> Row:
    return Row(**{field.name: r[field.name] for field in SILVER_PREVISION_SCHEMA.fields})


def _to_silver_avisos_row(r: dict) -> Row:
    return Row(**{field.name: r[field.name] for field in SILVER_AVISOS_SCHEMA.fields})


def _write_quality_report(report_uri: str, quality_report: dict) -> None:
    """Escribe el informe de Great Expectations directamente a S3 vía boto3 (ver docstring del módulo)."""
    bucket, _, key = report_uri.removeprefix("s3://").partition("/")
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )


def _process_prevision_partition(rows, processed_at_iso: str):
    processed_at = datetime.fromisoformat(processed_at_iso)
    bronze_records = [row.asDict(recursive=True) for row in rows]
    silver_records, _rejected = bronze_to_silver_prevision(bronze_records, processed_at)
    return [_to_silver_prevision_row(r) for r in silver_records]


def _process_avisos_partition(rows, processed_at_iso: str):
    processed_at = datetime.fromisoformat(processed_at_iso)
    bronze_records = [row.asDict(recursive=True) for row in rows]
    silver_records, _rejected = bronze_to_silver_avisos(bronze_records, processed_at)
    return [_to_silver_avisos_row(r) for r in silver_records]


def main() -> None:
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "bronze_prevision_path",
            "bronze_avisos_path",
            "silver_prevision_path",
            "silver_avisos_path",
            "quality_report_path",
        ],
    )

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)
    gx_context = gx.get_context(mode="ephemeral")

    # --- Previsión --------------------------------------------------------
    bronze_prevision_df = spark.read.option("multiLine", True).json(args["bronze_prevision_path"])
    silver_prevision_rdd = bronze_prevision_df.rdd.mapPartitions(
        lambda rows: _process_prevision_partition(rows, processed_at.isoformat())
    )
    silver_prevision_df = spark.createDataFrame(silver_prevision_rdd, schema=SILVER_PREVISION_SCHEMA)
    silver_prevision_df.cache()

    prevision_quality_report = run_prevision_quality_report(gx_context, silver_prevision_df)
    _write_quality_report(
        f"{args['quality_report_path'].rstrip('/')}/aemet_prevision_{processed_at:%Y%m%dT%H%M%S}.json",
        prevision_quality_report,
    )

    # Particiona solo por `fecha` (el día previsto, `valid_date`): la
    # previsión es diaria, sin resolución horaria real -- mismo criterio que
    # `ruido`/`agenda_eventos`.
    silver_prevision_df.withColumn("fecha", to_timestamp("valid_date")).withColumn(
        "fecha", date_format("fecha", "yyyy-MM-dd")
    ).write.mode("append").partitionBy("fecha").parquet(args["silver_prevision_path"])

    # --- Avisos -------------------------------------------------------------
    bronze_avisos_df = spark.read.option("multiLine", True).json(args["bronze_avisos_path"])
    silver_avisos_rdd = bronze_avisos_df.rdd.mapPartitions(
        lambda rows: _process_avisos_partition(rows, processed_at.isoformat())
    )
    silver_avisos_df = spark.createDataFrame(silver_avisos_rdd, schema=SILVER_AVISOS_SCHEMA)
    silver_avisos_df.cache()

    avisos_quality_report = run_avisos_quality_report(gx_context, silver_avisos_df)
    _write_quality_report(
        f"{args['quality_report_path'].rstrip('/')}/aemet_avisos_{processed_at:%Y%m%dT%H%M%S}.json",
        avisos_quality_report,
    )

    # Particiona por `fecha` = día de inicio de vigencia (`effective_from`),
    # no por `ingested_at` -- mismo criterio que `aggregate.py`.
    silver_avisos_df.withColumn("fecha", to_timestamp("effective_from")).withColumn(
        "fecha", date_format("fecha", "yyyy-MM-dd")
    ).write.mode("append").partitionBy("fecha").parquet(args["silver_avisos_path"])

    job.commit()


if __name__ == "__main__":
    main()
