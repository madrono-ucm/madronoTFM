"""Estimación de coste de almacenamiento S3 por bucket, vía la métrica
diaria `BucketSizeBytes` de CloudWatch (namespace `AWS/S3`) -- complemento
ligero al desglose de Glue de `desglose_glue.py` (tarea 078).

Solo cubre **almacenamiento** (`GB × precio/GB-mes`, clase Standard), no
peticiones (`PUT`/`GET`/...) ni transferencia de salida: CloudWatch no
publica esas dos como métricas gratuitas de bucket (a diferencia de
`BucketSizeBytes`/`NumberOfObjects`, que sí lo son) -- medirlas exigiría
S3 Server Access Logging o CloudTrail data events, ninguno de los dos
habilitado en esta cuenta y activarlos tiene coste propio. Con el patrón de
uso real de este proyecto (jobs de Glue que leen/escriben en lotes, no
servicio de alto tráfico), el almacenamiento es previsiblemente el
componente dominante del coste de S3 -- ver README para el detalle de esta
limitación.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import boto3

DEFAULT_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-west-1"
PRICE_PER_GB_MONTH_USD = float(os.environ.get("S3_PRICE_PER_GB_MONTH_USD", "0.023"))
STORAGE_TYPES = ["StandardStorage", "StandardIAStorage", "GlacierStorage"]


def list_bucket_names(s3_client=None) -> "list[str]":
    client = s3_client or boto3.client("s3", region_name=DEFAULT_REGION)
    return [b["Name"] for b in client.list_buckets()["Buckets"]]


def _latest_bucket_size_bytes(bucket_name: str, storage_type: str, cloudwatch_client) -> float:
    """Último valor disponible de `BucketSizeBytes` (la métrica solo se
    publica una vez al día, con retraso de hasta 48h) -- se pide una
    ventana de 3 días para no perderla si la última publicación aún no ha
    llegado."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=3)
    response = cloudwatch_client.get_metric_statistics(
        Namespace="AWS/S3",
        MetricName="BucketSizeBytes",
        Dimensions=[
            {"Name": "BucketName", "Value": bucket_name},
            {"Name": "StorageType", "Value": storage_type},
        ],
        StartTime=start,
        EndTime=end,
        Period=86400,
        Statistics=["Average"],
    )
    datapoints = sorted(response["Datapoints"], key=lambda dp: dp["Timestamp"])
    return datapoints[-1]["Average"] if datapoints else 0.0


def summarize_bucket(bucket_name: str, cloudwatch_client=None) -> dict:
    cloudwatch_client = cloudwatch_client or boto3.client("cloudwatch", region_name=DEFAULT_REGION)
    total_bytes = sum(
        _latest_bucket_size_bytes(bucket_name, storage_type, cloudwatch_client) for storage_type in STORAGE_TYPES
    )
    size_gb = total_bytes / (1024**3)
    return {
        "bucket_name": bucket_name,
        "size_gb": round(size_gb, 3),
        "cost_per_month_usd": round(size_gb * PRICE_PER_GB_MONTH_USD, 4),
    }


def build_report(s3_client=None, cloudwatch_client=None) -> dict:
    """Recorre todos los buckets reales de la cuenta y estima su coste de
    almacenamiento mensual a partir del último `BucketSizeBytes` publicado.
    Clientes inyectables para tests -- ver
    `herramientas/costes/tests/test_s3_costes.py`."""
    s3_client = s3_client or boto3.client("s3", region_name=DEFAULT_REGION)
    cloudwatch_client = cloudwatch_client or boto3.client("cloudwatch", region_name=DEFAULT_REGION)

    buckets = [summarize_bucket(name, cloudwatch_client) for name in list_bucket_names(s3_client)]
    buckets.sort(key=lambda b: b["cost_per_month_usd"], reverse=True)

    return {
        "assumptions": {
            "price_per_gb_month_usd": PRICE_PER_GB_MONTH_USD,
            "cubre_peticiones_y_transferencia": False,
        },
        "total_cost_per_month_usd": round(sum(b["cost_per_month_usd"] for b in buckets), 4),
        "buckets": buckets,
    }


def format_table(report: dict) -> str:
    lines = [
        f"Desglose de coste estimado de almacenamiento S3 (solo storage, ver README) "
        f"-- proyección/mes: {report['total_cost_per_month_usd']:.2f} USD",
        "",
        f"  {'bucket':<48}{'tamaño GB':>12}{'coste/mes~':>12}",
    ]
    for b in report["buckets"]:
        lines.append(f"  {b['bucket_name']:<48}{b['size_gb']:>12.3f}{b['cost_per_month_usd']:>12.4f}")
    return "\n".join(lines)
