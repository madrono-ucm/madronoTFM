"""Job de AWS Glue: Bronze -> Silver del dataset `bluesky_menciones`.

**No ejecutado en esta tarea** (mismo alcance de solo código/infraestructura,
sin `terraform apply`, que el resto de datasets del patrón, ver
`procesamiento/README.md`): este script asume el entorno de ejecución real
de un Glue Job Spark (runtime `glueetl`, `pyspark`/`awsglue`/
`great_expectations` disponibles). No se ha podido importar ni ejecutar aquí
(esta EC2 de desarrollo no tiene Spark instalado).

Reutiliza toda la lógica de negocio de `transform.py` (normalización, puerta
de calidad, deduplicación de duplicados exactos dentro del lote) tal cual --
este módulo solo es el "pegamento" de Spark/Glue: leer Bronze, aplicar
`bronze_to_silver` fila a fila vía `rdd.mapPartitions` y escribir el
resultado. La deduplicación de `transform.bronze_to_silver` opera dentro de
cada partición de Spark (ver `_process_partition`), no a través de todo el
DataFrame -- un post repetido entre términos de búsqueda solapados de
`search_district_sweep` normalmente cae en el mismo lote/objeto Bronze
(mismo `write_batch`, ver `ingesta/capturas/bronze.py`), y por tanto muy
probablemente en la misma partición de Spark al leerlo con
`multiLine=True`; un duplicado que caiga en particiones distintas no se
detecta aquí y sobrevive como una fila Silver adicional -- exactamente el
mismo caso que una reingesta entre ejecuciones distintas, que
`aggregate.py` ya resuelve contando `post_hash` distintos
(`mentions_count`). Deduplicar de verdad a través de todo el DataFrame
haría falta un `dropDuplicates(["post_hash"])` tras `mapPartitions`, pero
eso ya no sería reutilizar `transform.bronze_to_silver` tal cual -- se ha
preferido mantener la lógica de negocio en un único sitio probado por
`unittest`.

**Para el informe de Great Expectations se escribe directamente a S3 vía
`boto3`** (`_write_quality_report`), NO con
`sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
producción en la tarea 051 (el runtime de Glue no trae la clase de
committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
`saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo).

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/bluesky_menciones/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
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
from pyspark.sql.functions import date_format, to_timestamp
from pyspark.sql.types import IntegerType, StringType, StructField, StructType

from procesamiento.silver_gold.incremental import (
    daily_partition_uri,
    partition_has_objects,
    today,
)
from procesamiento.silver_gold.bluesky_menciones.ge_suite import run_quality_report
from procesamiento.silver_gold.bluesky_menciones.transform import bronze_to_silver

MADRID_TZ = ZoneInfo("Europe/Madrid")

SILVER_SCHEMA = StructType(
    [
        StructField("schema_version", IntegerType(), False),
        StructField("source", StringType(), True),
        StructField("mode", StringType(), False),
        StructField("match_term", StringType(), False),
        StructField("post_hash", StringType(), False),
        StructField("text", StringType(), False),
        StructField("lang", StringType(), True),
        StructField("created_at", StringType(), False),
        StructField("indexed_at", StringType(), True),
        StructField("like_count", IntegerType(), True),
        StructField("repost_count", IntegerType(), True),
        StructField("reply_count", IntegerType(), True),
        StructField("quote_count", IntegerType(), True),
        StructField("ingested_at", StringType(), False),
        StructField("processed_at", StringType(), False),
    ]
)


def _to_silver_row(silver_record: dict) -> Row:
    return Row(
        schema_version=silver_record["schema_version"],
        source=silver_record["source"],
        mode=silver_record["mode"],
        match_term=silver_record["match_term"],
        post_hash=silver_record["post_hash"],
        text=silver_record["text"],
        lang=silver_record["lang"],
        created_at=silver_record["created_at"],
        indexed_at=silver_record["indexed_at"],
        like_count=silver_record["like_count"],
        repost_count=silver_record["repost_count"],
        reply_count=silver_record["reply_count"],
        quote_count=silver_record["quote_count"],
        ingested_at=silver_record["ingested_at"],
        processed_at=silver_record["processed_at"],
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
    """Aplica `bronze_to_silver` a una partición de filas Bronze (ejecuta en cada executor).

    La deduplicación de duplicados exactos de `bronze_to_silver` opera solo
    dentro de esta partición -- ver docstring del módulo.
    """
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
        f"bluesky_menciones_{processed_at:%Y%m%dT%H%M%S}.json"
    )
    _write_quality_report(report_key, quality_report)

    # Particiona por la fecha/hora de la publicación (`created_at`), no por
    # `ingested_at` -- misma razón que `aggregate.py`: la pregunta natural
    # de este dataset es "cuándo se habló de este lugar", no "cuándo corrió
    # el barrido" (ver docstring de aggregate.py). `to_timestamp` sin
    # formato explícito acepta tanto el sufijo `Z` de Bluesky como el offset
    # `+02:00`/`+01:00` de `ingested_at` (parser ISO-8601 por defecto de
    # Spark 3.3/Glue 4.0) -- no verificado por ejecución real en esta EC2,
    # ver "Qué no se ha podido ejecutar" en procesamiento/README.md.
    silver_partitioned = silver_df.withColumn(
        "fecha", date_format(to_timestamp("created_at"), "yyyy-MM-dd")
    ).withColumn("hora", date_format(to_timestamp("created_at"), "HH"))

    silver_partitioned.write.mode("append").partitionBy("fecha", "hora").parquet(
        args["silver_path"]
    )

    job.commit()


if __name__ == "__main__":
    main()
