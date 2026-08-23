"""Job de AWS Glue de UN SOLO USO: reconstrucción deduplicada de Silver de
`bluesky_menciones` (tarea 077, mismo patrón que
`procesamiento/silver_gold/bicimad/glue_backfill_dedup.py`, tareas 073/074).

**No es parte del pipeline de producción incremental.** `glue_bronze_to_silver.py`
(tarea 057, arreglado en la tarea 076) lee solo la partición Bronze del día
de ejecución -- no acepta un `--bronze_path` que apunte a "todo el
histórico", así que no sirve para reconstruir Silver desde cero. Este script
existe únicamente para eso: leer TODO el histórico de Bronze de una vez y
deduplicar de verdad, tras el bug de lectura incremental (tarea 072/076) que
hizo que cada ejecución del pipeline reprocesara y reescribiera (`append`)
todo el histórico acumulado en vez de solo el día nuevo -- confirmado con
Athena real (`doc/076-arreglo-lectura-incremental-glue-grupo-diario.md`):
`n=19` para el mismo post. Se lanza una sola vez a mano (`aws glue
start-job-run`), nunca vía trigger ni schedule.

Requiere que el prefijo de destino (`--silver_path`) ya esté vacío antes de
lanzarlo (borrado manual con `aws s3 rm --recursive` -- ver doc/074).

`post_hash` es la clave natural del dataset (SHA-256 truncado del texto, ver
docstring de `transform.py`, "añadió `post_hash`... precisamente como" clave
de deduplicación) -- `dropDuplicates(["post_hash"])` es la misma
deduplicación de reingestas que ya hace `aggregate.py` en tiempo de
agregación (contando `post_hash` distintos), aplicada aquí a nivel de Silver
para que no siga creciendo sin límite. A diferencia de la deduplicación
dentro de partición que ya hace `transform.bronze_to_silver` (ver docstring
de `glue_bronze_to_silver.py`), este `dropDuplicates` opera sobre el
DataFrame completo, así que también colapsa duplicados que cayeron en
particiones de Spark distintas -- justo lo que necesita una reconstrucción
completa.

Reutiliza (no reimplementa) la normalización y las piezas de infraestructura
de Spark/GX que ya usa el pipeline de producción (`glue_bronze_to_silver.py`):
`SILVER_SCHEMA`, `_process_partition`, `_write_quality_report`.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `bronze_path`: prefijo S3 de origen completo, p.ej.
  `s3://madrono-tfm-dev-bronze-222234418587/bluesky_menciones/`.
- `silver_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/bluesky_menciones/`.
- `quality_report_path`: prefijo S3 donde se escribe el informe de
  validación de Great Expectations (un JSON, igual que el pipeline de
  producción).
"""

from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import great_expectations as gx
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql.functions import date_format, to_timestamp

from procesamiento.silver_gold.bluesky_menciones.glue_bronze_to_silver import (
    SILVER_SCHEMA,
    _process_partition,
    _write_quality_report,
)
from procesamiento.silver_gold.bluesky_menciones.ge_suite import run_quality_report

MADRID_TZ = ZoneInfo("Europe/Madrid")


def main() -> None:
    args = getResolvedOptions(
        sys.argv, ["JOB_NAME", "bronze_path", "silver_path", "quality_report_path"]
    )

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # A diferencia del pipeline incremental, este job de un solo uso lee TODO
    # el histórico de Bronze de una vez.
    bronze_df = spark.read.option("multiLine", True).json(args["bronze_path"])

    silver_rdd = bronze_df.rdd.mapPartitions(
        lambda rows: _process_partition(rows, processed_at.isoformat())
    )
    silver_df = spark.createDataFrame(silver_rdd, schema=SILVER_SCHEMA)

    # La deduplicación real que faltaba, a través de todo el DataFrame (no
    # solo dentro de partición, ver docstring del módulo). `post_hash` es la
    # clave natural del dataset.
    silver_df = silver_df.dropDuplicates(["post_hash"])
    silver_df.cache()

    gx_context = gx.get_context(mode="ephemeral")
    quality_report = run_quality_report(gx_context, silver_df)
    report_key = (
        f"{args['quality_report_path'].rstrip('/')}/"
        f"bluesky_menciones_backfill_dedup_{processed_at:%Y%m%dT%H%M%S}.json"
    )
    _write_quality_report(report_key, quality_report)

    # Mismo esquema de partición que el pipeline de producción (fecha=/hora=
    # de `created_at`).
    silver_partitioned = silver_df.withColumn(
        "fecha", date_format(to_timestamp("created_at"), "yyyy-MM-dd")
    ).withColumn("hora", date_format(to_timestamp("created_at"), "HH"))

    # `overwrite`, no `append`: este job reconstruye Silver desde cero. El
    # prefijo de destino debe estar vacío antes de lanzarlo (ver docstring
    # del módulo).
    silver_partitioned.write.mode("overwrite").partitionBy("fecha", "hora").parquet(
        args["silver_path"]
    )

    job.commit()


if __name__ == "__main__":
    main()
