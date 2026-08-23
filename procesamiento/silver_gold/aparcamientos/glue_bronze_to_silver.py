"""Job de AWS Glue: Bronze -> Silver del dataset `aparcamientos`.

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
`_with_consistency_column`) y escribir el resultado.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/aparcamientos/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/aparcamientos/`.
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

from procesamiento.silver_gold.incremental import (
    hourly_partition_uri,
    partition_has_objects,
    previous_hour,
)
from procesamiento.silver_gold.aparcamientos.ge_suite import run_quality_report
from procesamiento.silver_gold.aparcamientos.transform import bronze_to_silver

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
        StructField("parking_id", StringType(), False),
        StructField("name", StringType(), True),
        StructField("address", StringType(), True),
        # `measured_at` es nullable a propósito (ocupación no compartida en
        # tiempo real, ver transform.py) -- a diferencia del resto de
        # datasets del patrón, donde es obligatorio.
        StructField("measured_at", StringType(), True),
        StructField("ingested_at", StringType(), False),
        StructField("processed_at", StringType(), False),
        StructField("free_spaces", IntegerType(), True),
        StructField("total_spaces", IntegerType(), True),
        StructField("occupancy_ratio", DoubleType(), True),
        StructField("location", LOCATION_SCHEMA, False),
    ]
)


def _to_silver_row(silver_record: dict) -> Row:
    location = silver_record["location"]
    return Row(
        schema_version=silver_record["schema_version"],
        source=silver_record["source"],
        parking_id=silver_record["parking_id"],
        name=silver_record["name"],
        address=silver_record["address"],
        measured_at=silver_record["measured_at"],
        ingested_at=silver_record["ingested_at"],
        processed_at=silver_record["processed_at"],
        free_spaces=silver_record["free_spaces"],
        total_spaces=silver_record["total_spaces"],
        occupancy_ratio=silver_record["occupancy_ratio"],
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


def _with_consistency_column(silver_df):
    """Añade la columna auxiliar que `ge_suite.py` valida como `<= 0`.

    GX no tiene una expectation nativa de "columna <= columna" (ver
    docstring de `ge_suite.py`); se calcula aquí una vez, en Spark, en vez
    de repetir la lógica de `transform.validate_record` como una expresión
    de columnas separada. `free_spaces`/`total_spaces` pueden ser nulos (ver
    `transform.py`): `coalesce(..., 0)` hace que un registro con cualquiera
    de los dos ausentes dé `<= 0` (no viola la regla), igual que hace
    `validate_record` (solo compara cuando ambos están presentes).
    """
    return silver_df.withColumn(
        "free_spaces_over_total_spaces",
        F.coalesce(F.col("free_spaces"), F.lit(0)) - F.coalesce(F.col("total_spaces"), F.lit(1_000_000_000)),
    )


def main() -> None:
    args = getResolvedOptions(
        sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
    )

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    # Sin esto, `date_format(to_timestamp(...), "HH")` calcula `fecha`/`hora`
    # en el timezone de sesión por defecto de Spark (UTC en el runtime de
    # Glue), desalineado con la hora de Madrid real de `measured_at` -- ver
    # doc/072-arreglo-lectura-incremental-glue.md (desfase silencioso: el job
    # termina sin error pero nunca escribe la partición que espera Gold).
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # Lectura incremental (tarea 072): solo la particion Bronze de la hora
    # completa anterior a esta ejecucion -- nunca la raiz del dataset
    # completo, que crecia sin limite y disparo el coste real de Glue
    # documentado en doc/072-arreglo-lectura-incremental-glue.md.
    fecha, hora = previous_hour(processed_at)
    bronze_partition_path = hourly_partition_uri(args["bronze_path"], fecha, hora)
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
    quality_report = run_quality_report(gx_context, _with_consistency_column(silver_df))
    report_key = (
        f"{args['quality_report_path'].rstrip('/')}/"
        f"aparcamientos_{processed_at:%Y%m%dT%H%M%S}.json"
    )
    _write_quality_report(report_key, quality_report)

    # `measured_at` puede ser nulo (ver transform.py): esas filas se
    # particionan bajo `fecha=__sin_medida__/hora=__sin_medida__` en vez de
    # perderse -- siguen siendo consultables (auditoría de cobertura), pero
    # `glue_silver_to_gold.py`/`aggregate.py` las excluyen de la agregación
    # horaria (no hay hora que asignarles, ver docstring de `aggregate.py`).
    from pyspark.sql.functions import coalesce, date_format, lit, to_timestamp

    silver_partitioned = silver_df.withColumn(
        "fecha",
        coalesce(date_format(to_timestamp("measured_at"), "yyyy-MM-dd"), lit("__sin_medida__")),
    ).withColumn(
        "hora",
        coalesce(date_format(to_timestamp("measured_at"), "HH"), lit("__sin_medida__")),
    )

    silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
        args["silver_path"]
    )

    job.commit()


if __name__ == "__main__":
    main()
