"""Job de AWS Glue: Bronze -> Silver del dataset `ruido`.

**No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
sin `terraform apply`, que el resto de datasets del patrón, ver
`procesamiento/README.md`): este script asume el entorno de ejecución real
de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
`great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
(esta EC2 de desarrollo no tiene Spark instalado).

Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`
y escribir el resultado.

**Partición de Silver: solo `fecha`, sin `hora`** -- a diferencia del resto
de datasets del patrón (partición `fecha=/hora=`, derivada de un
`measured_at` con instante), esta fuente es diaria (`measured_date` es una
fecha, no un timestamp -- ver `transform.py`), así que no hay ninguna hora
real que particionar.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/ruido/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/ruido/`.
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
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from procesamiento.silver_gold.incremental import (
    daily_partition_uri,
    partition_has_objects,
    today,
)
from procesamiento.silver_gold.ruido.ge_suite import run_quality_report
from procesamiento.silver_gold.ruido.transform import bronze_to_silver

MADRID_TZ = ZoneInfo("Europe/Madrid")

LOCATION_SCHEMA = StructType(
    [
        StructField("lat", DoubleType(), True),
        StructField("lon", DoubleType(), True),
        StructField("srid", StringType(), True),
        StructField("altitude_m", IntegerType(), True),
    ]
)

SILVER_SCHEMA = StructType(
    [
        StructField("schema_version", IntegerType(), False),
        StructField("source", StringType(), True),
        StructField("station_id", StringType(), False),
        StructField("station_name", StringType(), True),
        StructField("station_address", StringType(), True),
        StructField("district", StringType(), True),
        StructField("neighbourhood", StringType(), True),
        StructField("period", StringType(), False),
        StructField("period_name", StringType(), True),
        StructField("measured_date", StringType(), False),
        StructField("ingested_at", StringType(), False),
        StructField("processed_at", StringType(), False),
        StructField("laeq_db", DoubleType(), False),
        StructField("l1_db", DoubleType(), True),
        StructField("l10_db", DoubleType(), True),
        StructField("l50_db", DoubleType(), True),
        StructField("l90_db", DoubleType(), True),
        StructField("l99_db", DoubleType(), True),
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
        district=silver_record["district"],
        neighbourhood=silver_record["neighbourhood"],
        period=silver_record["period"],
        period_name=silver_record["period_name"],
        measured_date=silver_record["measured_date"],
        ingested_at=silver_record["ingested_at"],
        processed_at=silver_record["processed_at"],
        laeq_db=silver_record["laeq_db"],
        l1_db=silver_record["l1_db"],
        l10_db=silver_record["l10_db"],
        l50_db=silver_record["l50_db"],
        l90_db=silver_record["l90_db"],
        l99_db=silver_record["l99_db"],
        location=Row(
            lat=location["lat"],
            lon=location["lon"],
            srid=location["srid"],
            altitude_m=location["altitude_m"],
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

    # Lectura incremental (tarea 072): solo la particion Bronze de hoy (dia
    # de ingestion; cadencia diaria, ver glue_scheduling.tf) -- nunca la
    # raiz del dataset completo, ver doc/072-arreglo-lectura-incremental-glue.md.
    fecha = today(processed_at)
    bronze_partition_path = daily_partition_uri(args["bronze_path"], fecha)
    if not partition_has_objects(boto3.client("s3"), bronze_partition_path):
        job.commit()
        return

    # Cada objeto Bronze es un array JSON de registros (ver
    # `ingesta/capturas/bronze.py`, `write_batch`); `multiLine=True` hace
    # que Spark expanda ese array en filas en vez de esperar NDJSON.
    bronze_df = spark.read.option("multiLine", True).json(bronze_partition_path)

    silver_rdd = bronze_df.rdd.mapPartitions(
        lambda rows: _process_partition(rows, processed_at.isoformat())
    )
    silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
    silver_df.cache()

    # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
    # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
    # `bronze_to_silver`, en el mismo SparkSession.
    gx_context = gx.get_context(mode="ephemeral")
    quality_report = run_quality_report(gx_context, silver_df)
    report_key = (
        f"{args['quality_report_path'].rstrip('/')}/"
        f"ruido_{processed_at:%Y%m%dT%H%M%S}.json"
    )
    _write_quality_report(report_key, quality_report)

    # Partición solo por `fecha` (derivada de `measured_date`, ya una cadena
    # "yyyy-MM-dd") -- ver docstring del módulo, esta fuente no tiene
    # ninguna hora real que particionar.
    (
        silver_df.withColumn("fecha", silver_df["measured_date"])
        .write.mode("append")
        .partitionBy("fecha")
        .parquet(args["silver_path"])
    )

    job.commit()


if __name__ == "__main__":
    main()
