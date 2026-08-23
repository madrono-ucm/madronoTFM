"""Punto de entrada único: desglose de coste estimado de Glue (principal,
tarea 078) más, opcionalmente, Lambda y S3. Combina
`desglose_glue.py`/`lambda_costes.py`/`s3_costes.py` -- ver el docstring de
cada uno para de dónde sale cada número y qué NO cubre (ninguno es el dato
oficial de Cost Explorer/Billing, ver `herramientas/costes/README.md`).

Uso:

    python3 -m herramientas.costes.resumen_costes
    python3 -m herramientas.costes.resumen_costes --incluir-lambda --incluir-s3
    python3 -m herramientas.costes.resumen_costes --formato json > costes.json
"""

from __future__ import annotations

import argparse
import json

import boto3

from herramientas.costes import desglose_glue, lambda_costes, s3_costes


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--region", default=desglose_glue.DEFAULT_REGION)
    parser.add_argument("--precio-dpu-hora", type=float, default=None, help="Ver desglose_glue.py.")
    parser.add_argument("--incluir-lambda", action="store_true")
    parser.add_argument("--incluir-s3", action="store_true")
    parser.add_argument("--formato", choices=["tabla", "json"], default="tabla")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)

    glue_client = boto3.client("glue", region_name=args.region)
    report = {"glue": desglose_glue.build_report(glue_client, price_per_dpu_hour=args.precio_dpu_hora)}

    if args.incluir_lambda:
        lambda_client = boto3.client("lambda", region_name=args.region)
        cloudwatch_client = boto3.client("cloudwatch", region_name=args.region)
        report["lambda"] = lambda_costes.build_report(lambda_client, cloudwatch_client)

    if args.incluir_s3:
        s3_client = boto3.client("s3", region_name=args.region)
        cloudwatch_client = boto3.client("cloudwatch", region_name=args.region)
        report["s3"] = s3_costes.build_report(s3_client, cloudwatch_client)

    if args.formato == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    print(desglose_glue.format_table(report["glue"]))
    if "lambda" in report:
        print()
        print(lambda_costes.format_table(report["lambda"]))
    if "s3" in report:
        print()
        print(s3_costes.format_table(report["s3"]))


if __name__ == "__main__":
    main()
