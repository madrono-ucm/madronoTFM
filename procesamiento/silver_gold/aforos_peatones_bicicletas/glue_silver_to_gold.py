"""Job de AWS Glue: Silver -> Gold del dataset `aforos_peatones_bicicletas`
(conteo total/medio por estación, modo y hora).

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

Parámetros del job (`--<nombre>`, ver `glue.tf`):

- `JOB_NAME`: nombre del job (estándar de Glue).
- `silver_path`: prefijo S3 de origen, p.ej.
  `s3://madrono-tfm-dev-silver-222234418587/aforos_peatones_bicicletas/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/aforos_peatones_bicicletas_por_estacion_modo_hora/`.
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

from procesamiento.silver_gold.incremental import daily_partition_uri, partition_has_objects, today

MADRID_TZ = ZoneInfo("Europe/Madrid")


def main() -> None:
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "silver_path", "gold_path"])

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark: SparkSession = glue_context.spark_session
    # Ver doc/072-arreglo-lectura-incremental-glue.md: sin esto, cualquier
    # `date_format(to_timestamp(...), ...)` de este job calcularia en UTC,
    # desalineado con `today()` (Python, Europe/Madrid).
    spark.conf.set("spark.sql.session.timeZone", "Europe/Madrid")
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    processed_at = datetime.now(MADRID_TZ)

    # Lectura incremental (tarea 076): solo la particion de Silver `fecha=hoy`,
    # nunca la raiz completa del dataset -- mismo motivo de coste que
    # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio conteo
    # (`measured_at`, ver glue_bronze_to_silver.py), que coincide con el dia
    # de ingestion para este dataset (conteos casi en tiempo real, sin
    # horizonte futuro) -- cada particion `fecha=<dia>` se visita una unica
    # vez, el dia en que ese dia es "hoy".
    fecha = today(processed_at)
    silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
    if not partition_has_objects(boto3.client("s3"), silver_partition_path):
        job.commit()
        return

    # `hora` sí se infiere como columna de partición física (es el nivel
    # inmediato bajo la ruta leída), pero `fecha` no -- al acotar la lectura
    # a `fecha=<fecha>/` (tarea 076) esa partición queda fija en la propia
    # ruta y Spark deja de exponerla como columna, igual que
    # `aparcamientos_silver_to_gold.py` (tarea 072). Se añade de vuelta con
    # el valor ya conocido en vez de asumir que Spark la habría inferido --
    # mismo bug real que `cartelera_cines_estrenos_silver_to_gold.py`
    # (`AnalysisException: Column 'fecha' does not exist`), encontrado y
    # corregido en la tarea 090 en los 3 jobs del patrón que lo tenían
    # latente; este en concreto no había fallado aún en producción porque la
    # fuente de `aforos_peatones_bicicletas` está descontinuada desde
    # 2026-06-30 (ver doc/087) y `partition_has_objects` nunca deja pasar
    # ninguna ejecución real hasta aquí.
    silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))

    # `mode` entra en la clave de agrupación (mismo criterio que `pollutant`
    # en `calidad_aire`/`magnitude` en `meteorologia`): peatones y bicicletas
    # se miden en redes de estaciones distintas, ver docstring de
    # `aggregate.py`.
    gold_df = (
        silver_df.groupBy("station_id", "mode", "fecha", "hora")
        .agg(
            F.count(F.lit(1)).alias("samples_count"),
            F.first("district_code", ignorenulls=True).alias("district_code"),
            F.first("district", ignorenulls=True).alias("district"),
            F.first("address", ignorenulls=True).alias("address"),
            F.first("address_notes", ignorenulls=True).alias("address_notes"),
            F.min("measured_at").alias("first_measured_at"),
            F.max("measured_at").alias("last_measured_at"),
            F.sum("count").alias("total_count"),
            F.avg("count").alias("avg_count"),
            F.max("count").alias("max_count"),
            F.min("count").alias("min_count"),
            F.first("location.lat", ignorenulls=True).alias("lat"),
            F.first("location.lon", ignorenulls=True).alias("lon"),
        )
        .withColumnRenamed("fecha", "date")
        .withColumn("hour", F.col("hora").cast("int"))
        .drop("hora")
        .withColumn("schema_version", F.lit(1))
        .withColumn("processed_at", F.lit(processed_at.isoformat()))
    )

    # Gold es órdenes de magnitud más pequeño que Silver (una fila por
    # estación, modo y hora, no cada ~5 minutos): particionar solo por
    # `date` es suficiente para podar particiones sin generar ficheros
    # diminutos.
    gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
