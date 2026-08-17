"""Puerta de calidad Great Expectations del dataset `bluesky_menciones`
(Silver).

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
(o de `transform.bronze_to_silver`, para el duplicado exacto) reproduce.

- `"text_missing_or_empty"` (`text` vacío o solo espacios) se reproduce con
  `expect_column_values_to_match_regex(regex=r"\\S")` en vez de
  `expect_column_values_to_not_be_null`: GX no tiene una expectation nativa
  de "cadena no vacía tras recortar espacios", y `not_be_null` dejaría pasar
  un `text` de solo espacios en blanco -- el regex `\\S` (al menos un
  carácter que no sea espacio) es la aproximación nativa más cercana a
  `str.strip()` de `validate_record`.
- `"duplicate_exact_content"` se reproduce con
  `expect_column_values_to_be_unique("post_hash")`. A diferencia del resto
  de expectations de este módulo, esta corre sobre un DataFrame que
  `transform.bronze_to_silver` **ya deduplicó** dentro del lote (ver ese
  módulo) -- así que en circunstancias normales siempre pasa; es una
  confirmación de que la deduplicación de `bronze_to_silver` hizo su trabajo
  (observabilidad/auditoría), no el mecanismo que decide qué fila sobrevive
  -- mismo principio que el resto del patrón ("GX valida, pero no decide",
  ver `procesamiento/README.md`).
"""

from __future__ import annotations

from typing import Any

import great_expectations as gx  # noqa: F401  (import real, ver docstring del módulo)
from pyspark.sql import DataFrame  # noqa: F401  (import real, ver docstring del módulo)

from .transform import VALID_MODES

EXPECTATION_SUITE_NAME = "bluesky_menciones_silver_suite"


def build_validator(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame"):
    """Construye un `Validator` de GX sobre el DataFrame de Silver ya filtrado.

    `context` se crea en modo "ephemeral" (`gx.get_context(mode="ephemeral")`
    en `glue_bronze_to_silver.py`), mismo criterio que el resto de datasets
    del patrón.
    """
    datasource = context.sources.add_or_update_spark(name="glue_bluesky_menciones_silver")
    data_asset = datasource.add_dataframe_asset(name="bluesky_menciones_silver")
    batch_request = data_asset.build_batch_request(dataframe=silver_df)

    suite = context.add_or_update_expectation_suite(EXPECTATION_SUITE_NAME)
    validator = context.get_validator(batch_request=batch_request, expectation_suite=suite)

    # Reproduce transform.validate_record: "mode_missing_or_invalid".
    validator.expect_column_values_to_be_in_set("mode", list(VALID_MODES))
    # Reproduce transform.validate_record: "match_term_missing".
    validator.expect_column_values_to_not_be_null("match_term")
    # Reproduce transform.validate_record: "text_missing_or_empty" -- ver
    # docstring del módulo para la limitación frente a str.strip().
    validator.expect_column_values_to_match_regex("text", regex=r"\S")
    # Reproduce transform.validate_record: "post_hash_missing".
    validator.expect_column_values_to_not_be_null("post_hash")
    # Reproduce transform.bronze_to_silver: "duplicate_exact_content" -- ver
    # docstring del módulo para por qué esto es una confirmación, no el
    # mecanismo real de deduplicación.
    validator.expect_column_values_to_be_unique("post_hash")
    # Reproduce transform.validate_record: "created_at_missing_or_unparseable".
    validator.expect_column_values_to_not_be_null("created_at")
    # Reproduce transform.validate_record: "captured_at_missing_or_unparseable"
    # (ya renombrado a `ingested_at` en Silver, ver transform.to_silver_record).
    validator.expect_column_values_to_not_be_null("ingested_at")

    return validator


def run_quality_report(context: "gx.data_context.AbstractDataContext", silver_df: "DataFrame") -> "dict[str, Any]":
    """Ejecuta la suite y devuelve el resultado ya serializado a `dict` (JSON-friendly)."""
    validator = build_validator(context, silver_df)
    result = validator.validate()
    return result.to_json_dict()
