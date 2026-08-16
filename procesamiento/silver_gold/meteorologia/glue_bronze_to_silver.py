"""Job de AWS Glue: Bronze -> Silver del dataset `meteorologia`.

**No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
sin `terraform apply`, que el resto de datasets del patrón, ver
`procesamiento/README.md`): este script asume el entorno de ejecución real
de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
`great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
(esta EC2 de desarrollo no tiene Spark instalado).

Reutiliza toda la lógica de negocio de `transform.py` (pivote ancho->largo,
puerta de calidad) tal cual -- este módulo solo es el "pegamento" de
Spark/Glue: leer Bronze, aplicar `bronze_to_silver` fila a fila vía
`rdd.mapPartitions` (una fila Bronze de entrada puede producir varias filas
Silver de salida, una por magnitud -- ver docstring de `transform.py`),
añadir las columnas auxiliares que necesita `ge_suite.py`
(`_with_plausible_range_columns`) y escribir el resultado.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/meteorologia/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/meteorologia/`.
- `quality_report_path`: prefijo S3 donde se escribe el informe de
  validación de Great Expectations (un JSON por ejecución del job).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

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

from procesamiento.silver_gold.meteorologia.ge_suite import run_quality_report
from procesamiento.silver_gold.meteorologia.transform import PLAUSIBLE_RANGE_BY_MAGNITUDE, bronze_to_silver

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
        StructField("magnitude", StringType(), False),
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
        magnitude=silver_record["magnitude"],
        value=silver_record["value"],
        measured_at=silver_record["measured_at"],
        ingested_at=silver_record["ingested_at"],
        processed_at=silver_record["processed_at"],
        location=Row(
            lat=location["lat"],
            lon=location["lon"],
            srid=location["srid"],
            altitude_m=location["altitude_m"],
        ),
    )


def _process_partition(rows, processed_at_iso: str):
    """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor).

    Cada fila Bronze de entrada (una estación, un instante, hasta 8
    magnitudes) puede producir varias filas Silver de salida -- de ahí
    `mapPartitions` en vez de un simple `map` 1:1.
    """
    processed_at = datetime.fromisoformat(processed_at_iso)
    bronze_records = [row.asDict(recursive=True) for row in rows]
    silver_records, _rejected = bronze_to_silver(bronze_records, processed_at)
    return [_to_silver_row(r) for r in silver_records]


def _with_plausible_range_columns(silver_df):
    """Añade las columnas auxiliares que `ge_suite.py` valida como `<= 0`.

    GX no tiene una expectation nativa de "el rango depende del valor de
    otra columna" (ver docstring de `ge_suite.py`); se traduce aquí
    `transform.PLAUSIBLE_RANGE_BY_MAGNITUDE` a dos expresiones `when/otherwise`
    de Spark en vez de repetir la tabla como una segunda fuente de verdad --
    una magnitud sin entrada en la tabla (no debería ocurrir) usa
    `(-inf, inf)` como rango, igual que `transform.validate_magnitude_value`
    no aplica ningún tope en ese caso.
    """
    min_expr = F.lit(float("-inf"))
    max_expr = F.lit(float("inf"))
    for magnitude, (min_value, max_value) in PLAUSIBLE_RANGE_BY_MAGNITUDE.items():
        min_expr = F.when(F.col("magnitude") == magnitude, F.lit(float(min_value))).otherwise(min_expr)
        max_expr = F.when(F.col("magnitude") == magnitude, F.lit(float(max_value))).otherwise(max_expr)
    return silver_df.withColumn("value_below_plausible_min", min_expr - F.col("value")).withColumn(
        "value_over_plausible_max", F.col("value") - max_expr
    )


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
    quality_report = run_quality_report(gx_context, _with_plausible_range_columns(silver_df))
    report_key = (
        f"{args['quality_report_path'].rstrip('/')}/"
        f"meteorologia_{processed_at:%Y%m%dT%H%M%S}.json"
    )
    sc.parallelize([json.dumps(quality_report, ensure_ascii=False)], numSlices=1).saveAsTextFile(
        report_key
    )

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
