"""Puerta de calidad Great Expectations del dataset `calidad_aire` (Silver).

**Importante**: este módulo importa `great_expectations` y `pyspark` a nivel
de módulo -- deliberadamente, para que el job de Glue
(`glue_bronze_to_silver.py`) lo pueda usar tal cual. Por eso NINGÚN test de
este proyecto importa este módulo (ver `procesamiento/tests/`, y
`procesamiento/README.md`, sección "Qué no se ha podido ejecutar en este
entorno"): esta EC2 de desarrollo no tiene ni Spark ni Great Expectations
instalados, así que el código de este módulo no se ha podido ejecutar ni
importar en esta sesión -- mismas condiciones que el resto de `ge_suite.py`
del patrón (`trafico`, tarea 041; ver ese módulo para el razonamiento
completo de por qué GX valida pero no decide qué filas pasan a Silver, y por
qué corre en el mismo job/`SparkSession` en vez de en un paso separado).

Cada expectation está anotada con qué regla de `transform.validate_record`
reproduce.

Nota: el rango plausible por contaminante (`transform.PLAUSIBLE_MAX_BY_POLLUTANT`)
no tiene una expectation nativa de "el máximo depende del valor de otra
columna" -- se aproxima igual que en `bicimad/ge_suite.py`/
`aparcamientos/ge_suite.py`: una columna auxiliar (`value_over_plausible_max`)
calculada en `glue_bronze_to_silver.py` antes de validar (una fila por
contaminante, `value - PLAUSIBLE_MAX_BY_POLLUTANT[pollutant]`), comprobada
aquí como `<= 0`.
"""

from __future__ import annotations

from typing import Any

import great_expectations as gx  # noqa: F401  (import real, ver docstring del módulo)
from pyspark.sql import DataFrame  # noqa: F401  (import real, ver docstring del módulo)

EXPECTATION_SUITE_NAME = "calidad_aire_silver_suite"


def build_validator(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame"):
    """Construye un `Validator` de GX sobre el DataFrame de Silver ya filtrado.

    `context` se crea en modo "ephemeral" (`gx.get_context(mode="ephemeral")`
    en `glue_bronze_to_silver.py`), mismo criterio que el resto de datasets
    del patrón.

    `silver_df` debe incluir la columna auxiliar `value_over_plausible_max`
    que añade `glue_bronze_to_silver.py` antes de validar (ver docstring del
    módulo, arriba).
    """
    datasource = context.sources.add_or_update_spark(name="glue_calidad_aire_silver")
    data_asset = datasource.add_dataframe_asset(name="calidad_aire_silver")
    batch_request = data_asset.build_batch_request(dataframe=silver_df)

    suite = context.add_or_update_expectation_suite(EXPECTATION_SUITE_NAME)
    validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

    # Reproduce transform.validate_record: "station_id_missing".
    validator.expect_column_values_to_not_be_null("station_id")
    # Reproduce transform.validate_record: "pollutant_missing".
    validator.expect_column_values_to_not_be_null("pollutant")
    # Reproduce transform.validate_record: "measured_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("measured_at")
    # Reproduce transform.validate_record: "ingested_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("ingested_at")
    # Reproduce transform.validate_record: "value_missing" / "value_negative".
    validator.expect_column_values_to_not_be_null("value")
    validator.expect_column_values_to_be_between("value", min_value=0, mostly=1.0)

    # Reproduce transform.validate_record: "value_out_of_plausible_range"
    # (rango por contaminante, ver docstring del módulo, columna auxiliar
    # calculada por glue_bronze_to_silver.py).
    validator.expect_column_values_to_be_between(
        "value_over_plausible_max", max_value=0, mostly=1.0
    )

    return validator


def run_quality_report(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame") -> "dict[str, Any]":
    """Ejecuta la suite y devuelve el resultado ya serializado a `dict` (JSON-friendly)."""
    validator = build_validator(context, silver_df)
    result = validator.validate()
    return result.to_json_dict()
