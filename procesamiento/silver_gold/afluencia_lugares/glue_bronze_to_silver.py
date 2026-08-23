"""Job de AWS Glue: Bronze -> Silver del dataset `afluencia_lugares`.

**No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
sin `terraform apply`, que el resto de datasets del patrón, ver
`procesamiento/README.md`): este script asume el entorno de ejecución real
de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
`great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
(esta EC2 de desarrollo no tiene Spark instalado).

Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
de calidad) tal cual -- este módulo solo es el "pegamento" de Spark/Glue:
leer Bronze, aplicar `bronze_to_silver` fila a fila vía `rdd.mapPartitions`,
añadir las columnas auxiliares que necesita `ge_suite.py` (ver
`_with_typical_by_hour_range_columns`) y escribir el resultado.

**Para el informe de Great Expectations se escribe directamente a S3 vía
`boto3`** (`_write_quality_report`), NO con
`sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
producción en la tarea 051 (el runtime de Glue no trae la clase de
committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
`saveAsTextFile` necesita).

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/afluencia_lugares_patron_tipico/`
  (nombre real del dataset Bronze que escribe
  `ingesta/capturas/afluencia_lugares_madrid.py::DATASET_NAME`, distinto del
  nombre `afluencia_lugares` usado en Silver/Gold -- corregido en la tarea
  061, ver doc/061).
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/afluencia_lugares/`.
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
    ArrayType,
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
from procesamiento.silver_gold.afluencia_lugares.ge_suite import run_quality_report
from procesamiento.silver_gold.afluencia_lugares.transform import WEEKDAY_KEYS_ES, bronze_to_silver

MADRID_TZ = ZoneInfo("Europe/Madrid")

TYPICAL_BY_HOUR_SCHEMA = StructType(
    [StructField(day, ArrayType(IntegerType()), True) for day in WEEKDAY_KEYS_ES]
)

SILVER_SCHEMA = StructType(
    [
        StructField("schema_version", IntegerType(), False),
        StructField("source", StringType(), True),
        StructField("place_id", StringType(), False),
        StructField("name", StringType(), False),
        StructField("query", StringType(), True),
        StructField("address", StringType(), True),
        StructField("lat", DoubleType(), True),
        StructField("lon", DoubleType(), True),
        StructField("live_pct", IntegerType(), True),
        StructField("typical_by_hour", TYPICAL_BY_HOUR_SCHEMA, True),
        StructField("ingested_at", StringType(), False),
        StructField("processed_at", StringType(), False),
    ]
)


def _typical_by_hour_row(typical_by_hour):
    if not typical_by_hour:
        return None
    return Row(**{day: typical_by_hour.get(day) for day in WEEKDAY_KEYS_ES})


def _to_silver_row(silver_record: dict) -> Row:
    row_dict = {
        field.name: silver_record[field.name] for field in SILVER_SCHEMA.fields if field.name != "typical_by_hour"
    }
    row_dict["typical_by_hour"] = _typical_by_hour_row(silver_record.get("typical_by_hour"))
    return Row(**row_dict)


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


def _with_typical_by_hour_range_columns(silver_df):
    """Añade las columnas auxiliares que `ge_suite.py` valida como `[0, 100]`.

    GX no tiene una expectation nativa de "cada valor de cada array anidado
    de un struct está en un rango" (ver docstring de `ge_suite.py`); se
    aplanan aquí los 7 arrays del struct `typical_by_hour` (uno por día de
    la semana) y se calcula su mínimo/máximo. Un registro sin
    `typical_by_hour` produce columnas auxiliares `null` (arrays vacíos tras
    el `coalesce`, `array_min`/`array_max` de un array vacío es `null` en
    Spark) -- GX ignora los `null` en `expect_column_values_to_be_between`
    por defecto.
    """
    day_arrays = [F.coalesce(F.col(f"typical_by_hour.{day}"), F.array()) for day in WEEKDAY_KEYS_ES]
    all_values = F.flatten(F.array(*day_arrays))
    return silver_df.withColumn("typical_by_hour_min_value", F.array_min(all_values)).withColumn(
        "typical_by_hour_max_value", F.array_max(all_values)
    )


def main() -> None:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"])

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    # Timezone de sesion de Spark = Europe/Madrid (tarea 076, mismo bug que
    # la tarea 072): sin esto, `date_format(to_timestamp(...), ...)` calcula
    # fecha/hora en UTC (el timezone por defecto del runtime de Glue usado
    # aqui), desalineado con `today()`/`daily_partition_uri()` (Python,
    # Europe/Madrid) -- ver doc/072-arreglo-lectura-incremental-glue.md.
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
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

    silver_rdd = bronze_df.rdd.mapPartitions(lambda rows: _process_partition(rows, processed_at.isoformat()))
    silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)
    silver_df.cache()

    # Puerta de calidad Great Expectations (observabilidad/auditoría, ver
    # docstring de `ge_suite.py`): corre sobre Silver ya filtrado por
    # `bronze_to_silver`, en el mismo SparkSession.
    gx_context = gx.get_context(mode="ephemeral")
    quality_report = run_quality_report(gx_context, _with_typical_by_hour_range_columns(silver_df))
    report_key = f"{args['quality_report_path'].rstrip('/')}/afluencia_lugares_{processed_at:%Y%m%dT%H%M%S}.json"
    _write_quality_report(report_key, quality_report)

    # Particiona por el día/hora del instante de captura (`ingested_at`,
    # único timestamp de este dataset) -- mismo criterio que `trafico`.
    silver_partitioned = silver_df.withColumn(
        "fecha", date_format(to_timestamp("ingested_at"), "yyyy-MM-dd")
    ).withColumn("hora", date_format(to_timestamp("ingested_at"), "HH"))

    silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(args["silver_path"])

    job.commit()


if __name__ == "__main__":
    main()
