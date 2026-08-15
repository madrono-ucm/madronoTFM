"""Puerta de calidad Great Expectations del dataset `trafico` (Silver).

**Importante**: este módulo importa `great_expectations` y `pyspark` a nivel
de módulo — deliberadamente, para que el job de Glue (`glue_bronze_to_silver.py`)
lo pueda usar tal cual. Por eso NINGÚN test de este proyecto importa este
módulo (ver `procesamiento/tests/`, y `procesamiento/README.md` sección
"Qué no se ha podido ejecutar en este entorno"): esta EC2 de desarrollo no
tiene ni Spark ni Great Expectations instalados (disco compartido y muy
limitado con el resto del pipeline, ver restricciones de la tarea), así que
el código de este módulo no se ha podido ejecutar ni importar en esta
sesión. Está escrito con el mismo cuidado que el resto del proyecto y
basado en la API pública documentada de Great Expectations (`sources.
add_or_update_spark` / `Validator`, estable en la serie 0.17-0.18), pero
antes del primer `terraform apply` real de esta tarea conviene una prueba de
humo en un notebook/endpoint de desarrollo de Glue (ver README) para
confirmarlo contra una versión concreta.

## Por qué Great Expectations valida, pero no decide qué filas pasan a Silver

La decisión de qué registros llegan a Silver la toma
`transform.validate_record` (Python puro, sin dependencias, probado con
`unittest` en `procesamiento/tests/test_transform.py`) — no este módulo.
Great Expectations se ejecuta **después** del filtro, sobre el DataFrame de
Silver ya filtrado, como una capa de **observabilidad y auditoría**: genera
un informe de validación estructurado (`ExpectationSuiteValidationResult`,
serializable a JSON) que el job escribe junto a la partición de Silver
correspondiente, para poder confirmar más adelante (sin releer los datos
crudos) que un lote de Silver cumplía las expectativas declaradas en el
momento en que se procesó.

Se ha descartado la alternativa de que GX sea el único mecanismo de
filtrado (validar con GX y descartar las filas que fallen sus expectations)
por dos motivos:

- **Testabilidad en este entorno**: la lógica de negocio de la puerta de
  calidad (rangos plausibles, bounding box de Madrid tras reproyectar, etc.)
  necesita poder probarse sin Spark ni GX instalados — ver
  `procesamiento/README.md`. Si GX fuera la única fuente de verdad del
  filtro, esa lógica no sería testable en este repo sin instalar el stack
  completo.
- **Una sola fuente de verdad por regla, deliberadamente duplicada en dos
  formas**: cada expectation de este módulo tiene una anotación en su
  docstring señalando qué regla de `transform.validate_record` reproduce.
  No son independientes — es la misma regla de negocio expresada dos veces
  a propósito (una ejecutable/testable sin GX, otra declarativa y con
  informe versionado) — para que un cambio futuro en una sin la otra se
  note enseguida en cuanto alguien lea ambos módulos uno junto al otro.

## Por qué dentro del mismo job de Glue, no como un job/paso separado

Se ejecuta en el mismo `SparkSession` que hace la transformación
Bronze->Silver, inmediatamente después de escribir la puerta de calidad de
`transform.py` y antes de persistir Silver, en vez de un Glue Job / paso de
Step Functions independiente que lea Silver ya escrito:

- El volumen de este piloto (un único dataset, sensores de tráfico cada
  ~5 min) no justifica el coste operativo de una orquestación adicional
  (Step Functions, un segundo Glue Job con su propio arranque de cluster
  Spark serverless) solo para validar.
- Validar en el mismo `SparkSession` evita una vuelta extra de lectura/
  escritura a S3 (leer Silver otra vez desde un job separado).
- Las dependencias de GX se instalan igualmente en tiempo de job vía
  `--additional-python-modules` (ver Terraform, `glue.tf`), así que separar
  el job no evita ningún problema de empaquetado — la única razón real para
  separarlo sería aislar fallos de GX de la escritura de Silver, y con un
  solo dataset piloto ese aislamiento no compensa la complejidad añadida.

Si en una tarea futura el número de datasets/volumen crece lo bastante como
para que la validación se convierta en un cuello de botella del job
principal, separar la validación en un job propio (o incluso migrar a
Glue Data Quality, el servicio gestionado de AWS basado también en DQDL/GX)
es la evolución natural — documentado aquí para no repetir esta discusión.
"""

from __future__ import annotations

from typing import Any

import great_expectations as gx  # noqa: F401  (import real, ver docstring del módulo)
from pyspark.sql import DataFrame  # noqa: F401  (import real, ver docstring del módulo)

from .geo import MADRID_BBOX_LAT, MADRID_BBOX_LON
from .transform import MAX_PLAUSIBLE_INTENSITY_VPH, MAX_PLAUSIBLE_SERVICE_LEVEL

EXPECTATION_SUITE_NAME = "trafico_silver_suite"


def build_validator(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame"):
    """Construye un `Validator` de GX sobre el DataFrame de Silver ya filtrado.

    `context` se crea en modo "ephemeral" (`gx.get_context(mode="ephemeral")`
    en `glue_bronze_to_silver.py`): no requiere ningún directorio de
    proyecto GX (`great_expectations.yml`) ni almacenamiento persistente de
    configuración — todo se define aquí, como código, coherente con el
    resto de este proyecto (Terraform/Python como única fuente de verdad,
    sin ficheros de configuración generados a mano).
    """
    datasource = context.sources.add_or_update_spark(name="glue_trafico_silver")
    data_asset = datasource.add_dataframe_asset(name="trafico_silver")
    batch_request = data_asset.build_batch_request(dataframe=silver_df)

    suite = context.add_or_update_expectation_suite(EXPECTATION_SUITE_NAME)
    validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

    # Reproduce transform.validate_record: "point_id_missing".
    validator.expect_column_values_to_not_be_null("point_id")
    # Reproduce transform.validate_record: "measured_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("measured_at")
    # Reproduce transform.validate_record: "ingested_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("ingested_at")

    # Reproduce transform.validate_record: "location_missing_or_outside_madrid_bbox".
    validator.expect_column_values_to_not_be_null("location.lat")
    validator.expect_column_values_to_not_be_null("location.lon")
    validator.expect_column_values_to_be_between(
        "location.lat", min_value=MADRID_BBOX_LAT[0], max_value=MADRID_BBOX_LAT[1]
    )
    validator.expect_column_values_to_be_between(
        "location.lon", min_value=MADRID_BBOX_LON[0], max_value=MADRID_BBOX_LON[1]
    )

    # Reproduce transform.validate_record: "intensity_vph_out_of_range".
    validator.expect_column_values_to_be_between(
        "intensity_vph", min_value=0, max_value=MAX_PLAUSIBLE_INTENSITY_VPH, mostly=1.0
    )
    # Reproduce transform.validate_record: "occupancy_pct_out_of_range".
    validator.expect_column_values_to_be_between(
        "occupancy_pct", min_value=0, max_value=100, mostly=1.0
    )
    # Reproduce transform.validate_record: "load_pct_out_of_range".
    validator.expect_column_values_to_be_between(
        "load_pct", min_value=0, max_value=100, mostly=1.0
    )
    # Reproduce transform.validate_record: "service_level_out_of_range".
    validator.expect_column_values_to_be_between(
        "service_level", min_value=0, max_value=MAX_PLAUSIBLE_SERVICE_LEVEL, mostly=1.0
    )

    return validator


def run_quality_report(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame") -> "dict[str, Any]":
    """Ejecuta la suite y devuelve el resultado ya serializado a `dict` (JSON-friendly)."""
    validator = build_validator(context, silver_df)
    result = validator.validate()
    return result.to_json_dict()
