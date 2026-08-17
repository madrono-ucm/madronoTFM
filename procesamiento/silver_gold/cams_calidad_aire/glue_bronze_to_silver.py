"""Job de AWS Glue: Bronze -> Silver del dataset `cams_calidad_aire`.

**No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
sin `terraform apply`, que el resto de datasets del patrón, ver
`procesamiento/README.md`): este script asume el entorno de ejecución real
de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
`great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
(esta EC2 de desarrollo no tiene Spark instalado).

Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
añadir la columna auxiliar de consistencia que necesita `ge_suite.py` (ver
`_with_plausible_max_column`) y escribir el resultado.

**Para el informe de Great Expectations se escribe directamente a S3 vía
`boto3`** (`_write_quality_report`), NO con
`sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
producción en la tarea 051 (el runtime de Glue no trae la clase de
committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
`saveAsTextFile` necesita).

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/cams_calidad_aire/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/cams_calidad_aire/`.
- `quality_report_path`: prefijo S3 donde se escribe el informe de
  validación de Great Expectations (un JSON por ejecución del job).
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
from pyspark.sql import functions as F
from pyspark.sql.functions import date_format, to_timestamp
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from procesamiento.silver_gold.cams_calidad_aire.ge_suite import run_quality_report
from procesamiento.silver_gold.cams_calidad_aire.transform import (
    PLAUSIBLE_MAX_BY_POLLUTANT,
    bronze_to_silver,
)

MADRID_TZ = ZoneInfo("Europe/Madrid")

SILVER_SCHEMA = StructType(
    [
        StructField("schema_version", IntegerType(), False),
        StructField("source", StringType(), True),
        StructField("pollutant", StringType(), False),
        StructField("pollutant_code", StringType(), False),
        StructField("value", DoubleType(), False),
        StructField("unit", StringType(), True),
        StructField("valid_datetime", StringType(), False),
        StructField("forecast_issued_at", StringType(), False),
        StructField("leadtime_hour", IntegerType(), False),
        StructField("model", StringType(), True),
        StructField("latitude", DoubleType(), True),
        StructField("longitude", DoubleType(), True),
        StructField("ingested_at", StringType(), False),
        StructField("processed_at", StringType(), False),
    ]
)


def _to_silver_row(silver_record: dict) -> Row:
    return Row(**{field.name: silver_record[field.name] for field in SILVER_SCHEMA.fields})


def _write_quality_report(report_uri: str, quality_report: dict) -> None:
    """Escribe el informe de Great Expectations directamente a S3 vía boto3 (ver docstring del módulo)."""
    bucket, _, key = report_uri.removeprefix("s3://").partition("/")
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(quality_report, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )


def _process_partition(rows, processed_at_iso: str):
    """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor)."""
    processed_at = datetime.fromisoformat(processed_at_iso)
    bronze_records = [row.asDict(recursive=True) for row in rows]
    silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
    return [_to_silver_row(r) for r in silver_records]


def _with_plausible_max_column(silver_df):
    """Añade la columna auxiliar que `ge_suite.py` valida como `<= 0`.

    GX no tiene una expectation nativa de "el máximo depende del valor de
    otra columna" (ver docstring de `ge_suite.py`); se traduce aquí
    `transform.PLAUSIBLE_MAX_BY_POLLUTANT` a una expresión `when/otherwise`
    de Spark en vez de repetir la tabla como una segunda fuente de verdad --
    un contaminante sin entrada en la tabla (no debería ocurrir) usa
    `float("inf")` como máximo, igual que `transform.validate_record` no
    aplica ningún tope de rango en ese caso.
    """
    max_expr = F.lit(float("inf"))
    for pollutant, max_value in PLAUSIBLE_MAX_BY_POLLUTANT.items():
        max_expr = F.when(F.col("pollutant") == pollutant, F.lit(float(max_value))).otherwise(max_expr)
    return silver_df.withColumn("value_over_plausible_max", F.col("value") - max_expr)


def main() -> None:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"])

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # Cada objeto Bronze es un array JSON de registros (ver
    # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
    # que Spark expanda ese array en filas en vez de esperar NDJSON.
    bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])

    silver_rdd = bronze_df.rdd.mapPartitions(lambda rows: _process_partition(rows, processed_at.isoformat()))
    silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
    silver_df.cache()

    # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
    # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
    # `bronze_to_silver`, en el mismo SparkSession.
    gx_context = gx.get_context(mode="ephemeral")
    quality_report = run_quality_report(gx_context, _with_plausible_max_column(silver_df))
    report_key = f"{args['quality_report_path'].rstrip('/')}/cams_calidad_aire_{processed_at:%Y%m%dT%H%M%S}.json"
    _write_quality_report(report_key, quality_report)

    # Particiona por el día/hora del instante **previsto** (`valid_datetime`),
    # no por `forecast_issued_at` (la corrida) ni por `ingested_at` (la
    # captura) -- responde "qué se predijo para tal fecha/hora", mismo
    # criterio que `aggregate.py` usa `valid_datetime` para `fecha_validez`.
    silver_partitioned = silver_df.withColumn(
        "fecha", date_format(to_timestamp("valid_datetime"), "yyyy-MM-dd")
    ).withColumn("hora", date_format(to_timestamp("valid_datetime"), "HH"))

    silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(args["silver_path"])

    job.commit()


if __name__ == "__main__":
    main()
