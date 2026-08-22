"""Job de AWS Glue: Bronze -> Silver del dataset `trafico`.

**No ejecutado en esta tarea** (piloto de solo código/infraestructura, sin
`terraform apply`, ver `procesamiento/README.md`): este script asume el
entorno de ejecución real de un Glue Job Spark (runtime `glueetl`, Python
3.11 a fecha de esta tarea, con `pyspark`/`awsglue`/`great_expectations`
disponibles — las dos primeras las provee el propio runtime de Glue, la
tercera se instala vía `--additional-python-modules`, ver `glue.tf`). No se
ha podido importar ni ejecutar aquí (esta EC2 de desarrollo no tiene Spark
instalado, ver restricciones de la tarea sobre disco compartido limitado).

Reutiliza toda la lógica de negocio de `transform.py` (reproyección,
normalización, puerta de calidad) tal cual — este módulo solo es el
"pegamento" de Spark/Glue: leer Bronze, aplicar `bronze_to_silver` fila a
fila vía `rdd.mapPartitions` (en vez de un DataFrame UDF: `transform.py`
opera sobre `dict` anidados de Python puro, y mapear sobre particiones
evita tener que expresar la misma lógica de nuevo con expresiones nativas
de columnas de Spark, manteniendo una única fuente de verdad de las
reglas), y escribir el resultado. Ver `ge_suite.py` para la validación de
Great Expectations que corre inmediatamente después, en el mismo
`SparkSession`.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/trafico/`. Se lee de forma
  recursiva (todas las particiones `fecha=/hora=` bajo ese prefijo);
  acotar el rango de fechas a procesar es responsabilidad de quien invoque
  el job (p.ej. pasando un prefijo más específico
  `.../trafico/fecha=2026-08-15/`), no de este script.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/trafico/`.
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
    BooleanType,
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
from procesamiento.silver_gold.trafico.ge_suite import run_quality_report
from procesamiento.silver_gold.trafico.transform import bronze_to_silver

MADRID_TZ = ZoneInfo("Europe/Madrid")

LOCATION_SCHEMA = StructType(
    [
        StructField("x", DoubleType(), True),
        StructField("y", DoubleType(), True),
        StructField("srid_source", StringType(), True),
        StructField("lat", DoubleType(), True),
        StructField("lon", DoubleType(), True),
        StructField("srid_target", StringType(), True),
    ]
)

SILVER_SCHEMA = StructType(
    [
        StructField("schema_version", IntegerType(), False),
        StructField("source", StringType(), True),
        StructField("point_id", StringType(), False),
        StructField("subarea", StringType(), True),
        StructField("description", StringType(), True),
        StructField("access_code", StringType(), True),
        StructField("measured_at", StringType(), False),
        StructField("ingested_at", StringType(), False),
        StructField("processed_at", StringType(), False),
        StructField("location", LOCATION_SCHEMA, False),
        StructField("intensity_vph", IntegerType(), True),
        StructField("occupancy_pct", IntegerType(), True),
        StructField("load_pct", IntegerType(), True),
        StructField("service_level", IntegerType(), True),
        StructField("saturation_intensity_vph", IntegerType(), True),
        StructField("occupancy_ratio", DoubleType(), True),
        StructField("load_ratio", DoubleType(), True),
        StructField("intensity_ratio", DoubleType(), True),
    ]
)


def _to_silver_row(silver_record: dict) -> Row:
    location = silver_record["location"]
    return Row(
        schema_version=silver_record["schema_version"],
        source=silver_record["source"],
        point_id=silver_record["point_id"],
        subarea=silver_record["subarea"],
        description=silver_record["description"],
        access_code=silver_record["access_code"],
        measured_at=silver_record["measured_at"],
        ingested_at=silver_record["ingested_at"],
        processed_at=silver_record["processed_at"],
        location=Row(
            x=location["x"],
            y=location["y"],
            srid_source=location["srid_source"],
            lat=location["lat"],
            lon=location["lon"],
            srid_target=location["srid_target"],
        ),
        intensity_vph=silver_record["intensity_vph"],
        occupancy_pct=silver_record["occupancy_pct"],
        load_pct=silver_record["load_pct"],
        service_level=silver_record["service_level"],
        saturation_intensity_vph=silver_record["saturation_intensity_vph"],
        occupancy_ratio=silver_record["occupancy_ratio"],
        load_ratio=silver_record["load_ratio"],
        intensity_ratio=silver_record["intensity_ratio"],
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

    # Lectura incremental (tarea 072): solo la partición Bronze de la hora
    # completa anterior a esta ejecución -- nunca la raíz del dataset
    # completo, que crecía sin límite y disparó el coste real de Glue
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
    quality_report = run_quality_report(gx_context, silver_df)
    report_key = (
        f"{args['quality_report_path'].rstrip('/')}/"
        f"trafico_{processed_at:%Y%m%dT%H%M%S}.json"
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
