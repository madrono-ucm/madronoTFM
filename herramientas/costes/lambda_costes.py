"""Estimación de coste de Lambda, basada en uso (`CloudWatch`
`Invocations`/`Duration`), como complemento ligero al desglose de Glue de
`desglose_glue.py` (tarea 078).

Lambda no tiene un equivalente directo a `glue:GetJobRuns` (no hay una API
que liste "ejecuciones" con coste ya calculado); el coste se deriva de dos
métricas estándar de CloudWatch por función (`Invocations`, `Duration`) más
la memoria configurada (`lambda:GetFunctionConfiguration`), aplicando la
fórmula pública de precio de Lambda (tramo x86, on-demand):

  coste = coste_peticiones + coste_computo
  coste_peticiones = invocaciones × precio_por_peticion
  coste_computo     = GB-segundo × precio_por_gb_segundo
  GB-segundo        = invocaciones × duracion_media_s × (memoria_mb / 1024)

No se resta el tramo gratuito (1M peticiones + 400 000 GB-s/mes) -- se dejan
ambos números (coste "bruto", sin descontar free tier) explícitos en la
salida para que quien lo lea aplique el descuento si le interesa; con el
volumen real de esta cuenta (cron interno disparando funciones cortas cada
hora, no tráfico de usuario) es muy probable que el coste real esté cubierto
por el tramo gratuito casi por completo.
"""

from __future__ import annotations

import os
import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3

DEFAULT_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-west-1"
DEFAULT_WINDOW_DAYS = int(os.environ.get("LAMBDA_COST_WINDOW_DAYS", "14"))
PRICE_PER_REQUEST_USD = float(os.environ.get("LAMBDA_PRICE_PER_REQUEST_USD", "0.0000002"))
PRICE_PER_GB_SECOND_USD = float(os.environ.get("LAMBDA_PRICE_PER_GB_SECOND_USD", "0.0000166667"))
PROJECTION_MONTH_DAYS = 30


def list_function_names(lambda_client=None) -> "list[str]":
    client = lambda_client or boto3.client("lambda", region_name=DEFAULT_REGION)
    names: "list[str]" = []
    for page in client.get_paginator("list_functions").paginate():
        names.extend(fn["FunctionName"] for fn in page["Functions"])
    return names


def _function_memory_mb(function_name: str, lambda_client) -> int:
    return lambda_client.get_function_configuration(FunctionName=function_name)["MemorySize"]


def _metric_sum_and_count(
    function_name: str, metric_name: str, window_days: int, cloudwatch_client
) -> "tuple[float, float]":
    """Suma total y nº de datapoints de `metric_name` en la ventana, agregando
    en periodos diarios (evita el límite de 1440 puntos/consulta de
    CloudWatch para ventanas largas)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=window_days)
    response = cloudwatch_client.get_metric_statistics(
        Namespace="AWS/Lambda",
        MetricName=metric_name,
        Dimensions=[{"Name": "FunctionName", "Value": function_name}],
        StartTime=start,
        EndTime=end,
        Period=86400,
        Statistics=["Sum", "SampleCount"],
    )
    datapoints = response["Datapoints"]
    total = sum(dp["Sum"] for dp in datapoints)
    sample_count = sum(dp["SampleCount"] for dp in datapoints)
    return total, sample_count


def summarize_function(
    function_name: str,
    lambda_client=None,
    cloudwatch_client=None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict:
    lambda_client = lambda_client or boto3.client("lambda", region_name=DEFAULT_REGION)
    cloudwatch_client = cloudwatch_client or boto3.client("cloudwatch", region_name=DEFAULT_REGION)

    memory_mb = _function_memory_mb(function_name, lambda_client)
    invocations, _ = _metric_sum_and_count(function_name, "Invocations", window_days, cloudwatch_client)
    duration_ms_total, duration_samples = _metric_sum_and_count(
        function_name, "Duration", window_days, cloudwatch_client
    )
    errors, _ = _metric_sum_and_count(function_name, "Errors", window_days, cloudwatch_client)

    avg_duration_s = (duration_ms_total / duration_samples / 1000.0) if duration_samples else 0.0
    gb_seconds = invocations * avg_duration_s * (memory_mb / 1024.0)
    cost_requests = invocations * PRICE_PER_REQUEST_USD
    cost_compute = gb_seconds * PRICE_PER_GB_SECOND_USD
    total_cost = cost_requests + cost_compute

    return {
        "function_name": function_name,
        "memory_mb": memory_mb,
        "window_days": window_days,
        "invocations": invocations,
        "errors": errors,
        "avg_duration_s": round(avg_duration_s, 3),
        "gb_seconds": round(gb_seconds, 4),
        "total_cost_usd_ventana": round(total_cost, 6),
        "cost_per_day_usd": round(total_cost / window_days, 6) if window_days else 0.0,
        "cost_per_month_usd": round(total_cost / window_days * PROJECTION_MONTH_DAYS, 4) if window_days else 0.0,
    }


def build_report(
    lambda_client=None,
    cloudwatch_client=None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict:
    """Recorre todas las funciones Lambda reales de la cuenta y estima su
    coste por peticiones + cómputo en la ventana de `window_days` días.
    Clientes inyectables para tests -- ver
    `herramientas/costes/tests/test_lambda_costes.py`."""
    lambda_client = lambda_client or boto3.client("lambda", region_name=DEFAULT_REGION)
    cloudwatch_client = cloudwatch_client or boto3.client("cloudwatch", region_name=DEFAULT_REGION)

    functions = [
        summarize_function(name, lambda_client, cloudwatch_client, window_days)
        for name in list_function_names(lambda_client)
    ]
    functions.sort(key=lambda f: f["total_cost_usd_ventana"], reverse=True)

    return {
        "window_days": window_days,
        "assumptions": {
            "price_per_request_usd": PRICE_PER_REQUEST_USD,
            "price_per_gb_second_usd": PRICE_PER_GB_SECOND_USD,
            "free_tier_descontado": False,
        },
        "total_cost_usd_ventana": round(sum(f["total_cost_usd_ventana"] for f in functions), 6),
        "total_cost_per_month_usd": round(sum(f["cost_per_month_usd"] for f in functions), 4),
        "functions": functions,
    }


def format_table(report: dict) -> str:
    lines = [
        f"Desglose de coste estimado de Lambda -- ventana de {report['window_days']} días "
        f"(sin descontar tramo gratuito, ver README)",
        f"Coste estimado en la ventana: {report['total_cost_usd_ventana']:.4f} USD"
        f"  |  proyección/mes: {report['total_cost_per_month_usd']:.2f} USD",
        "",
        f"  {'función':<38}{'invocaciones':>13}{'errores':>9}{'dur. media s':>13}{'coste/mes~':>12}",
    ]
    for f in report["functions"]:
        lines.append(
            f"  {f['function_name']:<38}{f['invocations']:>13.0f}{f['errors']:>9.0f}"
            f"{f['avg_duration_s']:>13.3f}{f['cost_per_month_usd']:>12.4f}"
        )
    return "\n".join(lines)
