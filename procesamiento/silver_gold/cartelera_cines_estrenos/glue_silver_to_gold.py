"""Job de AWS Glue: Silver -> Gold del dataset `cartelera_cines_estrenos`
(número de sesiones por película, cine y día).

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
  `s3://madrono-tfm-dev-silver-222234418587/cartelera_cines_estrenos/`.
- `gold_path`: prefijo S3 de destino, p.ej.
  `s3://madrono-tfm-dev-gold-222234418587/cartelera_cines_estrenos_por_pelicula_cine_fecha/`.
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
    # Bronze->Silver (tarea 072). `fecha` en Silver es la del propio dia de
    # la sesion (`showtime_datetime`), no la de ingestion (ver
    # glue_bronze_to_silver.py) -- pero por como funciona realmente
    # SensaCine (la cartelera scrapeada es de sesiones de hoy/muy cercanas,
    # ver "showtime_already_passed" en transform.py, nunca semanas vista),
    # cada particion `fecha=<dia>` recibe practicamente todos sus datos el
    # mismo dia (o el dia anterior), y esta lectura la visita el dia en que
    # ese dia es "hoy" -- si alguna sesion quedase en una particion futura no
    # visitada aun, se recogeria igual cuando esa particion se convierta en
    # "hoy" (Silver es un almacen persistente, no se borra entre
    # ejecuciones).
    fecha = today(processed_at)
    silver_partition_path = daily_partition_uri(args["silver_path"], fecha)
    if not partition_has_objects(boto3.client("s3"), silver_partition_path):
        job.commit()
        return

    # `fecha` es columna de partición física de Silver (ver
    # glue_bronze_to_silver.py), pero al acotar la lectura a una única
    # partición `fecha=<fecha>/` (tarea 076, lectura incremental) Spark deja
    # de inferirla como columna -- solo `hora=` varía bajo esa ruta, mismo
    # motivo por el que `aparcamientos_silver_to_gold.py` recalcula sus
    # columnas de partición tras acotar la lectura (tarea 072). Se añade de
    # vuelta con el valor ya conocido (`fecha`, calculado arriba) en vez de
    # asumir que Spark la habría inferido -- bug real encontrado en la
    # verificación contra datos reales de la tarea 090 (`AnalysisException:
    # Column 'fecha' does not exist`).
    silver_df = spark.read.parquet(silver_partition_path).withColumn("fecha", F.lit(fecha))

    # `movie_url`/`cinema_id` entran en la clave de agrupación junto a
    # `fecha` (mismo criterio que `aggregate.py`: incluir ambas dimensiones
    # deja disponibles tanto la vista "por película" como "por cine" sin
    # perder información en la propia agregación de Gold).
    gold_df = (
        silver_df.groupBy("movie_url", "cinema_id", "fecha")
        .agg(
            F.count(F.lit(1)).alias("samples_count"),
            F.countDistinct("showtime_id").alias("sessions_count"),
            F.first("movie_title", ignorenulls=True).alias("movie_title"),
            F.first("chain", ignorenulls=True).alias("chain"),
            F.first("cinema_name", ignorenulls=True).alias("cinema_name"),
            F.first("address", ignorenulls=True).alias("address"),
            F.first("postal_code", ignorenulls=True).alias("postal_code"),
            F.first("locality", ignorenulls=True).alias("locality"),
            F.min("showtime_datetime").alias("first_showtime_datetime"),
            F.max("showtime_datetime").alias("last_showtime_datetime"),
            F.sort_array(F.collect_set("language_version")).alias("language_versions"),
        )
        .withColumnRenamed("fecha", "date")
        .withColumn("schema_version", F.lit(1))
        .withColumn("processed_at", F.lit(processed_at.isoformat()))
    )

    # Gold es órdenes de magnitud más pequeño que Silver (una fila por
    # película, cine y día, no una por sesión): particionar solo por `date`
    # es suficiente para podar particiones sin generar ficheros diminutos.
    gold_df.write.mode("append").partitionBy("date").parquet(args["gold_path"])

    job.commit()


if __name__ == "__main__":
    main()
