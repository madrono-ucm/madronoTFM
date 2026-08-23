"""Desglose de coste estimado de AWS Glue por job/dataset, y proyección
simple de tendencia (tarea 078).

## Por qué esto y no Cost Explorer

La factura de Billing (`ce:GetCostAndUsage`) es la fuente de coste oficial,
pero el rol de esta EC2 no tiene permisos de Cost Explorer -- el intento de
darlos de alta en esta misma tarea fue bloqueado por el clasificador de
seguridad del entorno (requiere confirmación explícita del usuario, no
concedida). Este script estima el coste a partir de datos de **uso** ya
accesibles con los permisos existentes (`glue:GetJobs`/`glue:GetJobRuns`):
DPU-segundos reales de cada ejecución × un precio por DPU-hora configurable
(`0.44` USD/DPU-hora por defecto -- aproximado, el precio publicado de Glue
4.0 en `eu-west-1` a fecha de esta tarea, no el dato oficial de la factura).
Ver `herramientas/costes/README.md` para más detalle de esta limitación y
qué se recomienda si en el futuro se dan de alta permisos de Cost Explorer.

## De dónde sale cada número

- `DPUSeconds` lo devuelve `get_job_runs` ya calculado por Glue por cada
  ejecución (número de DPUs asignadas × segundos de ejecución) -- no hace
  falta recalcularlo a partir de `WorkerType`/`NumberOfWorkers`.
- Las ejecuciones todavía `RUNNING` no tienen `DPUSeconds` (es `None` hasta
  que terminan) -- se cuentan aparte, no se estiman, para no inventar un
  coste todavía no cerrado.
- Las ejecuciones `FAILED`/`TIMEOUT`/`ERROR` **sí** tienen `DPUSeconds` en
  cuanto llegan a ese estado (Glue cobra igual el tiempo consumido antes de
  fallar) -- se suman al coste total como cualquier otra, y además se listan
  aparte como "coste sin resultado útil" porque es la señal más urgente para
  esta herramienta (motivo de la tarea: una factura que subía sin que
  ninguna ejecución hubiera producido dato nuevo).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from datetime import datetime, timezone
from typing import Optional

import boto3

DEFAULT_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "eu-west-1"
DEFAULT_PRICE_PER_DPU_HOUR = float(os.environ.get("GLUE_PRICE_PER_DPU_HOUR", "0.44"))
JOB_NAME_PREFIX = os.environ.get("GLUE_JOB_NAME_PREFIX", "madrono-tfm-dev-")

# Ordenados de más a menos específico: un job "agenda-eventos-gold-backfill-dedup"
# debe reconocerse como sufijo "-gold-backfill-dedup", no cortar antes en
# "-backfill-dedup" y dejar "gold" pegado al nombre del dataset.
JOB_KIND_SUFFIXES = [
    "-silver-backfill-dedup",
    "-gold-backfill-dedup",
    "-bronze-to-silver",
    "-silver-to-gold",
]

WASTED_STATES = {"FAILED", "TIMEOUT", "ERROR", "STOPPED"}
TREND_SAMPLE_SIZE = 5
PROJECTION_MONTH_DAYS = 30


def job_kind(job_name: str) -> str:
    """Sufijo reconocido (p.ej. `-bronze-to-silver`), o `"otro"` si el
    nombre no sigue la convención habitual del proyecto."""
    for suffix in JOB_KIND_SUFFIXES:
        if job_name.endswith(suffix):
            return suffix.lstrip("-")
    return "otro"


def dataset_from_job_name(job_name: str, prefix: str = JOB_NAME_PREFIX) -> str:
    """`madrono-tfm-dev-agenda-eventos-gold-backfill-dedup` -> `agenda-eventos`."""
    name = job_name[len(prefix):] if job_name.startswith(prefix) else job_name
    for suffix in JOB_KIND_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def list_job_names(glue_client=None) -> "list[str]":
    client = glue_client or boto3.client("glue", region_name=DEFAULT_REGION)
    names: "list[str]" = []
    for page in client.get_paginator("get_jobs").paginate():
        names.extend(job["Name"] for job in page["Jobs"])
    return names


def list_job_runs(job_name: str, glue_client=None) -> "list[dict]":
    """Todas las ejecuciones disponibles de `job_name`, ordenadas de más
    antigua a más reciente. Glue solo retiene un histórico limitado de
    ejecuciones (no hay parámetro para pedir "desde tal fecha"); esta
    función trae todo lo que `get_job_runs` devuelva, sin recortar."""
    client = glue_client or boto3.client("glue", region_name=DEFAULT_REGION)
    runs: "list[dict]" = []
    for page in client.get_paginator("get_job_runs").paginate(JobName=job_name):
        runs.extend(page["JobRuns"])
    runs.sort(key=lambda r: r["StartedOn"])
    return runs


def dpu_seconds(run: dict) -> float:
    return run.get("DPUSeconds") or 0.0


def cost_usd(dpu_secs: float, price_per_dpu_hour: float) -> float:
    return dpu_secs / 3600.0 * price_per_dpu_hour


def _wasted_run_summary(run: dict, price_per_dpu_hour: float) -> dict:
    return {
        "run_id": run["Id"],
        "state": run["JobRunState"],
        "started_on": run["StartedOn"].isoformat(),
        "dpu_seconds": dpu_seconds(run),
        "cost_usd": round(cost_usd(dpu_seconds(run), price_per_dpu_hour), 4),
        "error_message": run.get("ErrorMessage"),
    }


def compute_trend(runs_sorted_asc: "list[dict]", sample_size: int = TREND_SAMPLE_SIZE) -> Optional[dict]:
    """Compara el DPU-segundos medio de las primeras `sample_size`
    ejecuciones completadas con el de las últimas `sample_size`. Con pocas
    ejecuciones históricas ambas ventanas pueden solaparse -- sigue siendo
    la señal de tendencia más simple razonable (ver enunciado de la tarea),
    solo hay que leer `sample_size_real` para saber cuántas ejecuciones
    hay detrás del número."""
    completed = [r for r in runs_sorted_asc if r.get("DPUSeconds") is not None]
    if len(completed) < 2:
        return None

    k = min(sample_size, len(completed))
    first_window = completed[:k]
    last_window = completed[-k:]
    avg_first = statistics.fmean(dpu_seconds(r) for r in first_window)
    avg_last = statistics.fmean(dpu_seconds(r) for r in last_window)
    growth_pct = None if avg_first == 0 else (avg_last - avg_first) / avg_first * 100.0

    return {
        "sample_size_real": k,
        "avg_dpu_seconds_first": round(avg_first, 1),
        "avg_dpu_seconds_last": round(avg_last, 1),
        "growth_pct": None if growth_pct is None else round(growth_pct, 1),
    }


def compute_projection(
    runs_sorted_asc: "list[dict]",
    price_per_dpu_hour: float,
    sample_size: int = TREND_SAMPLE_SIZE,
) -> Optional[dict]:
    """Proyección coste/día y coste/mes: coste medio de las últimas
    `sample_size` ejecuciones completadas, extrapolado con la frecuencia de
    ejecución observada en todo el histórico disponible (tiempo entre la
    primera y la última ejecución / número de ejecuciones). Supone que el
    dataset sigue ejecutándose a ese mismo ritmo -- si un job está pausado
    (trigger `DEACTIVATED`) esta proyección sigue asumiendo el ritmo
    histórico, no el actual; revisa el estado del trigger aparte."""
    completed = [r for r in runs_sorted_asc if r.get("DPUSeconds") is not None]
    if len(completed) < 2:
        return None

    span_seconds = (completed[-1]["StartedOn"] - completed[0]["StartedOn"]).total_seconds()
    if span_seconds <= 0:
        return None

    runs_per_day = (len(completed) - 1) / (span_seconds / 86400.0)
    recent = completed[-min(sample_size, len(completed)):]
    avg_cost_recent = statistics.fmean(cost_usd(dpu_seconds(r), price_per_dpu_hour) for r in recent)
    cost_per_day = avg_cost_recent * runs_per_day

    return {
        "runs_per_day_historico": round(runs_per_day, 2),
        "avg_cost_usd_ultimas_ejecuciones": round(avg_cost_recent, 4),
        "cost_per_day_usd": round(cost_per_day, 4),
        "cost_per_month_usd": round(cost_per_day * PROJECTION_MONTH_DAYS, 2),
    }


def summarize_job(job_name: str, runs: "list[dict]", price_per_dpu_hour: float) -> dict:
    total_dpu_seconds = sum(dpu_seconds(r) for r in runs)
    running = [r for r in runs if r["JobRunState"] == "RUNNING"]
    wasted = [r for r in runs if r["JobRunState"] in WASTED_STATES]
    wasted_sorted = sorted(wasted, key=lambda r: r["StartedOn"], reverse=True)

    return {
        "job_name": job_name,
        "dataset": dataset_from_job_name(job_name),
        "kind": job_kind(job_name),
        "num_runs": len(runs),
        "num_runs_en_curso": len(running),
        "total_dpu_seconds": total_dpu_seconds,
        "total_cost_usd": round(cost_usd(total_dpu_seconds, price_per_dpu_hour), 4),
        "wasted_runs": [_wasted_run_summary(r, price_per_dpu_hour) for r in wasted_sorted[:5]],
        "wasted_cost_usd": round(cost_usd(sum(dpu_seconds(r) for r in wasted), price_per_dpu_hour), 4),
        "trend": compute_trend(runs),
        "projection": compute_projection(runs, price_per_dpu_hour),
    }


def build_report(glue_client=None, price_per_dpu_hour: Optional[float] = None) -> dict:
    """Punto de entrada principal: recorre todos los jobs de Glue reales de
    la cuenta, trae sus ejecuciones, y devuelve el desglose completo por
    job y por dataset. `glue_client` es inyectable (por defecto,
    `boto3.client("glue")`) para poder testear sin credenciales/conexión
    real -- ver `herramientas/costes/tests/test_desglose_glue.py`."""
    client = glue_client or boto3.client("glue", region_name=DEFAULT_REGION)
    price = DEFAULT_PRICE_PER_DPU_HOUR if price_per_dpu_hour is None else price_per_dpu_hour

    jobs = []
    for job_name in list_job_names(client):
        runs = list_job_runs(job_name, client)
        jobs.append(summarize_job(job_name, runs, price))

    datasets: "dict[str, dict]" = {}
    for job in jobs:
        entry = datasets.setdefault(
            job["dataset"],
            {"dataset": job["dataset"], "total_cost_usd": 0.0, "wasted_cost_usd": 0.0, "num_runs": 0, "jobs": []},
        )
        entry["total_cost_usd"] = round(entry["total_cost_usd"] + job["total_cost_usd"], 4)
        entry["wasted_cost_usd"] = round(entry["wasted_cost_usd"] + job["wasted_cost_usd"], 4)
        entry["num_runs"] += job["num_runs"]
        entry["jobs"].append(job["job_name"])

    dataset_list = sorted(datasets.values(), key=lambda d: d["total_cost_usd"], reverse=True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "price_per_dpu_hour_usd": price,
        "total_cost_usd": round(sum(j["total_cost_usd"] for j in jobs), 4),
        "total_wasted_cost_usd": round(sum(j["wasted_cost_usd"] for j in jobs), 4),
        "jobs": sorted(jobs, key=lambda j: j["total_cost_usd"], reverse=True),
        "datasets": dataset_list,
    }


def format_table(report: dict) -> str:
    lines = []
    lines.append(
        f"Desglose de coste estimado de Glue -- generado {report['generated_at']} "
        f"(precio asumido: {report['price_per_dpu_hour_usd']} USD/DPU-hora, no oficial)"
    )
    lines.append(
        f"Coste total estimado (histórico disponible): {report['total_cost_usd']:.2f} USD"
        f"  |  de los cuales sin resultado útil (FAILED/TIMEOUT/ERROR/STOPPED): "
        f"{report['total_wasted_cost_usd']:.2f} USD"
    )
    lines.append("")

    lines.append("Por dataset:")
    header = f"  {'dataset':<32}{'coste USD':>12}{'desperdiciado':>16}{'ejecuciones':>13}"
    lines.append(header)
    for d in report["datasets"]:
        lines.append(
            f"  {d['dataset']:<32}{d['total_cost_usd']:>12.2f}{d['wasted_cost_usd']:>16.2f}{d['num_runs']:>13}"
        )
    lines.append("")

    lines.append("Por job (proyección coste/mes si sigue el ritmo histórico reciente):")
    header = f"  {'job':<48}{'coste USD':>11}{'en curso':>9}{'coste/mes~':>12}{'tendencia':>11}"
    lines.append(header)
    for j in report["jobs"]:
        proj = j["projection"]
        cost_month = f"{proj['cost_per_month_usd']:.2f}" if proj else "n/d"
        trend = j["trend"]
        if trend and trend["growth_pct"] is not None:
            arrow = "+" if trend["growth_pct"] >= 0 else ""
            trend_str = f"{arrow}{trend['growth_pct']:.0f}%"
        else:
            trend_str = "n/d"
        lines.append(
            f"  {j['job_name']:<48}{j['total_cost_usd']:>11.2f}"
            f"{j['num_runs_en_curso']:>9}{cost_month:>12}{trend_str:>11}"
        )
        if j["wasted_runs"]:
            lines.append(
                f"      -> {len(j['wasted_runs'])} ejecucion(es) reciente(s) sin resultado útil "
                f"({j['wasted_cost_usd']:.2f} USD), última: {j['wasted_runs'][0]['state']} "
                f"en {j['wasted_runs'][0]['started_on']}"
            )

    return "\n".join(lines)


def parse_args(argv: "Optional[list[str]]" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Desglose de coste estimado de AWS Glue por job/dataset y proyección coste/día-mes."
    )
    parser.add_argument(
        "--precio-dpu-hora",
        type=float,
        default=None,
        help=f"Precio USD/DPU-hora asumido (por defecto: env GLUE_PRICE_PER_DPU_HOUR o {DEFAULT_PRICE_PER_DPU_HOUR}).",
    )
    parser.add_argument("--region", default=DEFAULT_REGION, help=f"Región AWS (por defecto: {DEFAULT_REGION}).")
    parser.add_argument("--formato", choices=["tabla", "json"], default="tabla")
    return parser.parse_args(argv)


def main(argv: "Optional[list[str]]" = None) -> None:
    args = parse_args(argv)
    client = boto3.client("glue", region_name=args.region)
    report = build_report(client, price_per_dpu_hour=args.precio_dpu_hora)
    if args.formato == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_table(report))


if __name__ == "__main__":
    main()
