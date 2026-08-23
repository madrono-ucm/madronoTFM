"""Job de AWS Glue: Silver -> Gold del dataset `afluencia_lugares` (afluencia
en vivo media y valor típico por lugar, fecha y hora).

**No ejecutado en esta tarea** (mismas condiciones que
`glue_bronze_to_silver.py`: piloto de solo código/infraestructura, sin Spark
disponible en esta EC2 de desarrollo -- ver `procesamiento/README.md`).

A diferencia de `glue_bronze_to_silver.py`, este job **no** reutiliza
`aggregate.py` en tiempo de ejecución: una agregación `groupBy` correcta a
través de múltiples particiones/ficheros de Silver necesita las primitivas
nativas de reduce distribuido de Spark, no un `mapPartitions` fila a fila --
mismo motivo que el resto de datasets del patrón. `aggregate.py` sigue
siendo la fuente de verdad **documental y de test** de qué agrega Gold; las
expresiones de Spark de este job están escritas para producir exactamente el
mismo esquema de salida que `aggregate.aggregate_silver_to_gold`; un cambio
en uno debe reflejarse en el otro.

`typical_by_hour` es un struct con un array por día de la semana -- no hay
forma de indexar un campo de struct por el nombre contenido en otra columna
directamente en Spark SQL, así que `_typical_value_expr` construye una
cadena `when/otherwise` por día (mismo patrón que la columna auxiliar de
`glue_bronze_to_silver.py`), equivalente a `aggregate._typical_value_for`.

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/afluencia_lugares/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/afluencia_lugares_por_lugar_fecha_hora/`.
"""

from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from procesamiento.silver_gold.afluencia_lugares.transform import WEEKDAY_KEYS_ES
from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today

MADRID_TZ = ZoneInfo("Europe/Madrid")

# `F.dayofweek` de Spark numera domingo=1 ... sábado=7; se traduce aquí a
# las mismas claves en español que usa `datetime.weekday()` (lunes=0) en
# `aggregate.py`, vía `WEEKDAY_KEYS_ES`.
_SPARK_DAYOFWEEK_TO_WEEKDAY_KEY = {
    2: WEEKDAY_KEYS_ES[0],  # lunes
    3: WEEKDAY_KEYS_ES[1],  # martes
    4: WEEKDAY_KEYS_ES[2],  # miercoles
    5: WEEKDAY_KEYS_ES[3],  # jueves
    6: WEEKDAY_KEYS_ES[4],  # viernes
    7: WEEKDAY_KEYS_ES[5],  # sabado
    1: WEEKDAY_KEYS_ES[6],  # domingo
}


def _day_of_week_expr(timestamp_col):
    expr = F.lit(None).cast("string")
    for dayofweek_number, day_key in _SPARK_DAYOFWEEK_TO_WEEKDAY_KEY.items():
        expr = F.when(F.dayofweek(timestamp_col) == dayofweek_number, day_key).otherwise(expr)
    return expr


def _typical_value_expr(hour_col):
    """Equivalente a `aggregate._typical_value_for`: valor de `typical_by_hour` para el día/hora de cada fila."""
    expr = F.lit(None).cast("int")
    for day in WEEKDAY_KEYS_ES:
        value_for_day = F.element_at(F.col(f"typical_by_hour.{day}"), hour_col + 1)
        expr = F.when(F.col("day_of_week") == day, value_for_day).otherwise(expr)
    return expr


def main() -> None:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto,
    # `date_format`/`hour` de mas abajo calcularian en UTC, desalineado con
    # `today()` (Python, Europe/Madrid).
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
    # nunca la raiz completa del dataset -- mismo motivo de coste que
    # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio instante
    # de captura (`ingested_at`, unico timestamp de este dataset, ver
    # glue_bronze_to_silver.py) -- coincide siempre con el dia de ingestion,
    # cada particion `fecha=<dia>` se visita una unica vez, el dia en que ese
    # dia es "hoy".
    fecha = today(processed_at)
    silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
    if not partition_has_objects(boto3.client("s3"), silver_partition_path):
        job.commit()
        return

    silver_df = spark.read.parquet(silver_partition_path)

    ingested_at_ts = F.to_timestamp("ingested_at")
    silver_with_period = (
        silver_df.withColumn("date", F.date_format(ingested_at_ts, "yyyy-MM-dd"))
        .withColumn("hour", F.hour(ingested_at_ts))
        .withColumn("day_of_week", _day_of_week_expr(ingested_at_ts))
    )
    silver_with_typical = silver_with_period.withColumn(
        "typical_value", _typical_value_expr(F.col("hour"))
    )

    gold_df = (
        silver_with_typical.groupBy("place_id", "date", "hour")
        .agg(
            F.first("name", ignorenulls=True).alias("name"),
            F.first("day_of_week", ignorenulls=True).alias("day_of_week"),
            F.count(F.lit(1)).alias("samples_count"),
            F.avg("live_pct").alias("avg_live_pct"),
            F.avg("typical_value").alias("typical_pct"),
            F.first("lat", ignorenulls=True).alias("lat"),
            F.first("lon", ignorenulls=True).alias("lon"),
            F.min("ingested_at").alias("first_ingested_at"),
            F.max("ingested_at").alias("last_ingested_at"),
        )
        .withColumn("schema_version", F.lit(1))
        .withColumn("processed_at", F.lit(processed_at.isoformat()))
    )

    # Gold es mucho más pequeño que Silver (una fila por lugar/fecha/hora,
    # no por captura): particionar solo por `date` basta -- mismo criterio
    # que `trafico`.
    gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
