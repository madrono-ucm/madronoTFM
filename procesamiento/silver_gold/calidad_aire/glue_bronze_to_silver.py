"""Job de AWS Glue: Bronze -> Silver del dataset `calidad_aire`.

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

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/calidad_aire/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/calidad_aire/`.
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
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from procesamiento.silver_gold.calidad_aire.ge_suite import run_quality_report
from procesamiento.silver_gold.calidad_aire.transform import PLAUSIBLE_MAX_BY_POLLUTANT, bronze_to_silver

MADRID_TZ = ZoneInfo("Europe/Madrid")

LOCATION_SCHEMA = StructType(
    [
        StructField("lat", DoubleType(), True),
        StructField("lon", DoubleType(), True),
        StructField("srid", StringType(), True),
    ]
)

SILVER_SCHEMA = StructType(
    [
        StructField("schema_version", IntegerType(), False),
        StructField("source", StringType(), True),
        StructField("station_id", StringType(), False),
        StructField("station_name", StringType(), True),
        StructField("station_address", StringType(), True),
        StructField("magnitude_code", StringType(), True),
        StructField("pollutant", StringType(), False),
        StructField("pollutant_name", StringType(), True),
        StructField("unit", StringType(), True),
        StructField("value", DoubleType(), False),
        StructField("measured_at", StringType(), False),
        StructField("ingested_at", StringType(), False),
        StructField("processed_at", StringType(), False),
        StructField("location", LOCATION_SCHEMA, False),
    ]
)


def _to_silver_row(silver_record: dict) -> Row:
    location = silver_record["location"]
    return Row(
        schema_version=silver_record["schema_version"],
        source=silver_record["source"],
        station_id=silver_record["station_id"],
        station_name=silver_record["station_name"],
        station_address=silver_record["station_address"],
        magnitude_code=silver_record["magnitude_code"],
        pollutant=silver_record["pollutant"],
        pollutant_name=silver_record["pollutant_name"],
        unit=silver_record["unit"],
        value=silver_record["value"],
        measured_at=silver_record["measured_at"],
        ingested_at=silver_record["ingested_at"],
        processed_at=silver_record["processed_at"],
        location=Row(
            lat=location["lat"],
            lon=location["lon"],
            srid=location["srid"],
        ),
    )


def _write_quality_report(report_uri: str, quality_report: dict) -> None:
    """Escribe el informe de Great Expectations directamente a S3 vía boto3.

    Sustituye a `sc.parallelize([...], numSlices=1).saveAsTextFile(...)`: un
    único JSON pequeño no necesita el protocolo de commit distribuido de
    Spark/Hadoop, que en el runtime de AWS Glue falla buscando
    `org.apache.hadoop.mapred.DirectOutputCommitter` (clase de EMR/
    `hadoop-aws` ausente en Glue) — ver tarea 051.
    """
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
    args = getResolvedOptions(
        sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
    )

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

    silver_rdd = bronze_df.rdd.mapPartitions(
        lambda rows: _process_partition(rows, processed_at.isoformat())
    )
    silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
    silver_df.cache()

    # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
    # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
    # `bronze_to_silver`, en el mismo SparkSession.
    gx_context = gx.get_context(mode="ephemeral")
    quality_report = run_quality_report(gx_context, _with_plausible_max_column(silver_df))
    report_key = (
        f"{args['quality_report_path'].rstrip('/')}/"
        f"calidad_aire_{processed_at:%Y%m%dT%H%M%S}.json"
    )
    _write_quality_report(report_key, quality_report)

    # Mismo esquema de partición que Bronze (fecha=/hora=, hora de Madrid),
    # para que un consumidor ya familiarizado con Bronze no tenga que
    # aprender un esquema de partición distinto para Silver.
    from pyspark.sql.functions import date_format, to_timestamp

    silver_partitioned = silver_df.withColumn(
        "fecha", date_format(to_timestamp("measured_at"), "yyyy-MM-dd")
    ).withColumn("hora", date_format(to_timestamp("measured_at"), "HH"))

    silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
        args["silver_path"]
    )

    job.commit()


if __name__ == "__main__":
    main()
