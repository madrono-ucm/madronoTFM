"""Puerta de calidad Great Expectations del dataset `aemet_prevision_avisos`
(Silver): dos suites independientes, una por forma de dato (ver
`transform.py`).

**Importante**: este módulo importa `great_expectations` y `pyspark` a nivel
de módulo -- deliberadamente, para que el job de Glue
(`glue_bronze_to_silver.py`) lo pueda usar tal cual. Por eso NINGÚN test de
este proyecto importa este módulo (ver `procesamiento/tests/`, y
`procesamiento/README.md`, sección "Qué no se ha podido ejecutar en este
entorno"): esta EC2 de desarrollo no tiene ni Spark ni Great Expectations
instalados, así que el código de este módulo no se ha podido ejecutar ni
importar en esta sesión -- mismas condiciones que el resto de `ge_suite.py`
del patrón (`trafico`, tarea 041; ver ese módulo para el razonamiento
completo de por qué GX valida pero no decide qué filas pasan a Silver).

Cada expectation está anotada con qué regla de `transform.validate_prevision_record`/
`transform.validate_aviso_record` reproduce. La comprobación
`valid_date_already_passed` (comparación entre dos columnas de texto
ISO-8601, no `TimestampType`) se reproduce con
`expect_column_pair_values_a_to_be_greater_than_b(or_equal=True)`, mismo
patrón -- y misma limitación documentada -- que
`cartelera_cines_estrenos/ge_suite.py` (comparación lexicográfica de texto,
no de instantes reales; observabilidad, la decisión real la toma
`transform.validate_prevision_record` con objetos `date`/`datetime`
comparados de verdad).
"""

from __future__ import annotations

from typing import Any

import great_expectations as gx  # noqa: F401  (import real, ver docstring del módulo)
from pyspark.sql import DataFrame  # noqa: F401  (import real, ver docstring del módulo)

from .transform import (
    PRECIPITATION_PROBABILITY_MAX_PCT,
    PRECIPITATION_PROBABILITY_MIN_PCT,
    TEMPERATURE_MAX_C,
    TEMPERATURE_MIN_C,
    VALID_LEVELS,
)

PREVISION_EXPECTATION_SUITE_NAME = "aemet_prevision_silver_suite"
AVISOS_EXPECTATION_SUITE_NAME = "aemet_avisos_silver_suite"


def build_prevision_validator(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame"):
    """Construye un `Validator` de GX sobre el DataFrame de Silver de previsión ya filtrado."""
    datasource = context.sources.add_or_update_spark(name="glue_aemet_prevision_silver")
    data_asset = datasource.add_dataframe_asset(name="aemet_prevision_silver")
    batch_request = data_asset.build_batch_request(dataframe=silver_df)

    suite = context.add_or_update_expectation_suite(PREVISION_EXPECTATION_SUITE_NAME)
    validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

    # Reproduce transform.validate_prevision_record: "municipio_code_missing".
    validator.expect_column_values_to_not_be_null("municipio_code")
    # Reproduce transform.validate_prevision_record: "valid_date_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("valid_date")
    # Reproduce transform.validate_prevision_record: "ingested_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("ingested_at")
    # Reproduce transform.validate_prevision_record: "valid_date_already_passed" -- ver
    # docstring del módulo para la limitación de comparación lexicográfica.
    validator.expect_column_pair_values_a_to_be_greater_than_b(
        column_A="valid_date", column_B="ingested_at", or_equal=True
    )
    # Reproduce transform.validate_prevision_record: "temperature_max_c_missing_or_out_of_range".
    validator.expect_column_values_to_be_between(
        "temperature_max_c", min_value=TEMPERATURE_MIN_C, max_value=TEMPERATURE_MAX_C
    )
    # Reproduce transform.validate_prevision_record: "temperature_min_c_missing_or_out_of_range".
    validator.expect_column_values_to_be_between(
        "temperature_min_c", min_value=TEMPERATURE_MIN_C, max_value=TEMPERATURE_MAX_C
    )
    # Reproduce transform.validate_prevision_record: "precipitation_probability_pct_missing_or_out_of_range".
    validator.expect_column_values_to_be_between(
        "precipitation_probability_pct",
        min_value=PRECIPITATION_PROBABILITY_MIN_PCT,
        max_value=PRECIPITATION_PROBABILITY_MAX_PCT,
    )

    return validator


def build_avisos_validator(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame"):
    """Construye un `Validator` de GX sobre el DataFrame de Silver de avisos ya filtrado."""
    datasource = context.sources.add_or_update_spark(name="glue_aemet_avisos_silver")
    data_asset = datasource.add_dataframe_asset(name="aemet_avisos_silver")
    batch_request = data_asset.build_batch_request(dataframe=silver_df)

    suite = context.add_or_update_expectation_suite(AVISOS_EXPECTATION_SUITE_NAME)
    validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

    # Reproduce transform.validate_aviso_record: "identifier_missing".
    validator.expect_column_values_to_not_be_null("identifier")
    # Reproduce transform.validate_aviso_record: "zone_missing".
    validator.expect_column_values_to_not_be_null("zone")
    # Reproduce transform.validate_aviso_record: "level_missing_or_invalid" -- catálogo
    # cerrado de AEMET (amarillo/naranja/rojo).
    validator.expect_column_values_to_be_in_set("level", list(VALID_LEVELS))
    # Reproduce transform.validate_aviso_record: "phenomenon_missing".
    validator.expect_column_values_to_not_be_null("phenomenon")
    # Reproduce transform.validate_aviso_record: "effective_from_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("effective_from")
    # Reproduce transform.validate_aviso_record: "ingested_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("ingested_at")

    return validator


def run_prevision_quality_report(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame") -> "dict[str, Any]":
    """Ejecuta la suite de previsión y devuelve el resultado ya serializado a `dict`."""
    validator = build_prevision_validator(context, silver_df)
    result = validator.validate()
    return result.to_json_dict()


def run_avisos_quality_report(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame") -> "dict[str, Any]":
    """Ejecuta la suite de avisos y devuelve el resultado ya serializado a `dict`."""
    validator = build_avisos_validator(context, silver_df)
    result = validator.validate()
    return result.to_json_dict()
