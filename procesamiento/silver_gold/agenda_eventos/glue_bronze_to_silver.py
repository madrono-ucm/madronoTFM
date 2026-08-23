"""Job de AWS Glue: Bronze -> Silver del dataset `agenda_eventos`.

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

**Para el informe de Great Expectations se escribe directamente a S3 vía
`boto3`** (`_write_quality_report`), NO con
`sc.parallelize(...).saveAsTextFile(...)`: ese patrón causó un bug real de
producción en la tarea 051 (el runtime de Glue no trae la clase de
committer `org.apache.hadoop.mapred.DirectOutputCommitter` que
`saveAsTextFile` necesita -- ver esa tarea para el diagnóstico completo).

Silver se particiona solo por `fecha` (derivada de `start_datetime`), sin
`hora`: a diferencia del resto del patrón, una de las dos fuentes
(`agenda_turismo_esmadrid`) no publica ninguna hora en `start_datetime`
(solo fecha, ver `transform.py`) -- forzar una `hora` inventada (p.ej.
"00" por defecto del parseo) sería engañoso, mismo criterio que ya aplicó
`ruido` (tarea 053) para una fuente sin granularidad horaria. `fecha` se
deriva con `substring(start_datetime, 1, 10)` en vez de `to_date(...)`:
ambos formatos de origen (`"2026-08-21T22:00:00"` del dataset municipal,
`"2026-11-15"` de esMadrid) siempre empiezan por `YYYY-MM-DD`, así que un
recorte de texto es más simple y evita cualquier ambigüedad de parseo de
fecha mixta en Spark.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/agenda_eventos/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/agenda_eventos/`.
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
from pyspark.sql.functions import substring
from pyspark.sql.types import (
    BooleanType,
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
from procesamiento.silver_gold.agenda_eventos.ge_suite import run_quality_report
from procesamiento.silver_gold.agenda_eventos.transform import bronze_to_silver

MADRID_TZ = ZoneInfo("Europe/Madrid")

SILVER_SCHEMA = StructType(
    [
        StructField("schema_version", IntegerType(), False),
        StructField("source", StringType(), False),
        StructField("event_id", StringType(), False),
        StructField("title", StringType(), False),
        StructField("description", StringType(), True),
        StructField("category", StringType(), True),
        StructField("start_datetime", StringType(), False),
        StructField("end_datetime", StringType(), True),
        StructField("schedule_text", StringType(), True),
        StructField("free", BooleanType(), True),
        StructField("price_info", StringType(), True),
        StructField("venue_name", StringType(), True),
        StructField("address", StringType(), True),
        StructField("district", StringType(), True),
        StructField("neighborhood", StringType(), True),
        StructField("postal_code", StringType(), True),
        StructField("lat", DoubleType(), True),
        StructField("lon", DoubleType(), True),
        StructField("url", StringType(), True),
        StructField("ingested_at", StringType(), False),
        StructField("processed_at", StringType(), False),
    ]
)


def _to_silver_row(silver_record: dict) -> Row:
    return Row(
        schema_version=silver_record["schema_version"],
        source=silver_record["source"],
        event_id=silver_record["event_id"],
        title=silver_record["title"],
        description=silver_record["description"],
        category=silver_record["category"],
        start_datetime=silver_record["start_datetime"],
        end_datetime=silver_record["end_datetime"],
        schedule_text=silver_record["schedule_text"],
        free=silver_record["free"],
        price_info=silver_record["price_info"],
        venue_name=silver_record["venue_name"],
        address=silver_record["address"],
        district=silver_record["district"],
        neighborhood=silver_record["neighborhood"],
        postal_code=silver_record["postal_code"],
        lat=silver_record["lat"],
        lon=silver_record["lon"],
        url=silver_record["url"],
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
        f"agenda_eventos_{processed_at:%Y%m%dT%H%M%S}.json"
    )
    _write_quality_report(report_key, quality_report)

    # Particiona solo por `fecha` (sin `hora`, ver docstring del módulo):
    # una de las dos fuentes no publica hora de celebración.
    silver_partitioned = silver_df.withColumn("fecha", substring("start_datetime", 1, 10))

    silver_partitioned.write.mode("append").partitionBy("fecha").parquet(args["silver_path"])

    job.commit()


if __name__ == "__main__":
    main()
