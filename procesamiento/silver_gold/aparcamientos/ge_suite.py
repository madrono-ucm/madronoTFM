"""Puerta de calidad Great Expectations del dataset `aparcamientos` (Silver).

**Importante**: este módulo importa `great_expectations` y `pyspark` a nivel
de módulo -- deliberadamente, para que el job de Glue
(`glue_bronze_to_silver.py`) lo pueda usar tal cual. Por eso NINGÚN test de
este proyecto importa este módulo (ver `procesamiento/tests/`, y
`procesamiento/README.md`, sección "Qué no se ha podido ejecutar en este
entorno"): esta EC2 de desarrollo no tiene ni Spark ni Great Expectations
instalados, así que el código de este módulo no se ha podido ejecutar ni
importar en esta sesión -- mismas condiciones que `trafico/ge_suite.py`
(tarea 041), `transporte_publico_emt/ge_suite.py` (tarea 046) y
`bicimad/ge_suite.py` (tarea 047), ver el primero para el razonamiento
completo de por qué GX valida pero no decide qué filas pasan a Silver, y por
qué corre en el mismo job/`SparkSession` en vez de en un paso separado (se
aplica sin cambios a este dataset, no se repite aquí).

Cada expectation está anotada con qué regla de `transform.validate_record`
reproduce -- la misma regla de negocio expresada dos veces a propósito (una
testable sin GX, otra declarativa y con informe versionado), ver
`trafico/ge_suite.py` para el motivo completo.

Nota: `measured_at`/`free_spaces`/`total_spaces` se validan con
`mostly=1.0` sobre los valores NO nulos (`expect_column_values_to_be_between`
ignora nulos por defecto en GX) -- a diferencia de `bicimad`/`trafico`, aquí
NO hay ninguna expectation de "no nulo" sobre estas tres columnas, porque
`transform.validate_record` las admite a `None` a propósito (ver el
docstring de ese módulo, "Decisión explícita: ocupación no disponible NO se
descarta"). La comprobación `free_spaces <= total_spaces` (cuando ambos
están presentes) tampoco tiene una expectation nativa de "columna <=
columna" -- se aproxima igual que en `bicimad/ge_suite.py`: una columna
auxiliar (`free_spaces_over_total_spaces`) calculada en
`glue_bronze_to_silver.py` antes de validar, comprobada como `<= 0`.
"""

from __future__ import annotations

from typing import Any

import great_expectations as gx  # noqa: F401  (import real, ver docstring del módulo)
from pyspark.sql import DataFrame  # noqa: F401  (import real, ver docstring del módulo)

EXPECTATION_SUITE_NAME = "aparcamientos_silver_suite"


def build_validator(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame"):
    """Construye un `Validator` de GX sobre el DataFrame de Silver ya filtrado.

    `context` se crea en modo "ephemeral" (`gx.get_context(mode="ephemeral")`
    en `glue_bronze_to_silver.py`), mismo criterio que el resto de datasets
    del patrón.

    `silver_df` debe incluir la columna auxiliar
    `free_spaces_over_total_spaces` que añade `glue_bronze_to_silver.py`
    antes de validar (ver docstring del módulo, arriba).
    """
    datasource = context.sources.add_or_update_spark(name="glue_aparcamientos_silver")
    data_asset = datasource.add_dataframe_asset(name="aparcamientos_silver")
    batch_request = data_asset.build_batch_request(dataframe=silver_df)

    suite = context.add_or_update_expectation_suite(EXPECTATION_SUITE_NAME)
    validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

    # Reproduce transform.validate_record: "parking_id_missing".
    validator.expect_column_values_to_not_be_null("parking_id")
    # Reproduce transform.validate_record: "ingested_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("ingested_at")

    # Reproduce transform.validate_record: "free_spaces_negative" /
    # "total_spaces_negative" -- solo sobre los valores no nulos presentes
    # (ver docstring del módulo: `measured_at`/`free_spaces`/`total_spaces`
    # nulos son válidos aquí, a diferencia del resto de datasets del
    # patrón).
    validator.expect_column_values_to_be_between("free_spaces", min_value=0, mostly=1.0)
    validator.expect_column_values_to_be_between("total_spaces", min_value=0, mostly=1.0)

    # Reproduce transform.validate_record: "free_spaces_exceeds_total_spaces"
    # (ver docstring del módulo, columna auxiliar calculada por
    # glue_bronze_to_silver.py).
    validator.expect_column_values_to_be_between(
        "free_spaces_over_total_spaces", max_value=0, mostly=1.0
    )

    return validator


def run_quality_report(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame") -> "dict[str, Any]":
    """Ejecuta la suite y devuelve el resultado ya serializado a `dict` (JSON-friendly)."""
    validator = build_validator(context, silver_df)
    result = validator.validate()
    return result.to_json_dict()
