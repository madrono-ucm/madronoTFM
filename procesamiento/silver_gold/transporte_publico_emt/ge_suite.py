"""Puerta de calidad Great Expectations del dataset `transporte_publico_emt` (Silver).

**Importante**: este módulo importa `great_expectations` y `pyspark` a nivel
de módulo -- deliberadamente, para que el job de Glue
(`glue_bronze_to_silver.py`) lo pueda usar tal cual. Por eso NINGÚN test de
este proyecto importa este módulo (ver `procesamiento/tests/`, y
`procesamiento/README.md`, sección "Qué no se ha podido ejecutar en este
entorno"): esta EC2 de desarrollo no tiene ni Spark ni Great Expectations
instalados, así que el código de este módulo no se ha podido ejecutar ni
importar en esta sesión -- mismas condiciones que
`trafico/ge_suite.py` (tarea 041), ver ese módulo para el razonamiento
completo de por qué GX valida pero no decide qué filas pasan a Silver, y por
qué corre en el mismo job/`SparkSession` en vez de en un paso separado (se
aplica sin cambios a este dataset, no se repite aquí).

Cada expectation está anotada con qué regla de
`transform.validate_record` reproduce -- la misma regla de negocio expresada
dos veces a propósito (una testable sin GX, otra declarativa y con informe
versionado), ver `trafico/ge_suite.py` para el motivo completo.
"""

from __future__ import annotations

from typing import Any

import great_expectations as gx  # noqa: F401  (import real, ver docstring del módulo)
from pyspark.sql import DataFrame  # noqa: F401  (import real, ver docstring del módulo)

from .transform import MAX_PLAUSIBLE_WAIT_SEC, MIN_PLAUSIBLE_WAIT_SEC

EXPECTATION_SUITE_NAME = "transporte_publico_emt_silver_suite"


def build_validator(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame"):
    """Construye un `Validator` de GX sobre el DataFrame de Silver ya filtrado.

    `context` se crea en modo "ephemeral" (`gx.get_context(mode="ephemeral")`
    en `glue_bronze_to_silver.py`), mismo criterio que `trafico/ge_suite.py`.
    """
    datasource = context.sources.add_or_update_spark(name="glue_transporte_publico_emt_silver")
    data_asset = datasource.add_dataframe_asset(name="transporte_publico_emt_silver")
    batch_request = data_asset.build_batch_request(dataframe=silver_df)

    suite = context.add_or_update_expectation_suite(EXPECTATION_SUITE_NAME)
    validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

    # Reproduce transform.validate_record: "stop_id_missing".
    validator.expect_column_values_to_not_be_null("stop_id")
    # Reproduce transform.validate_record: "line_missing".
    validator.expect_column_values_to_not_be_null("line")
    # Reproduce transform.validate_record: "ingested_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("ingested_at")

    # Reproduce transform.validate_record: "estimate_arrive_sec_out_of_range".
    validator.expect_column_values_to_be_between(
        "estimate_arrive_sec",
        min_value=MIN_PLAUSIBLE_WAIT_SEC,
        max_value=MAX_PLAUSIBLE_WAIT_SEC,
        mostly=1.0,
    )
    # Reproduce transform.validate_record: "distance_bus_m_negative".
    validator.expect_column_values_to_be_between(
        "distance_bus_m", min_value=0, mostly=1.0
    )

    return validator


def run_quality_report(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame") -> "dict[str, Any]":
    """Ejecuta la suite y devuelve el resultado ya serializado a `dict` (JSON-friendly)."""
    validator = build_validator(context, silver_df)
    result = validator.validate()
    return result.to_json_dict()
