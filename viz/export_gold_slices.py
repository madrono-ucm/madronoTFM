"""Congela en el repo las ventanas de Gold que la animación necesita.

Se ejecuta una sola vez, **antes** de que la partition projection deslizante
de Athena deje de exponer esas particiones de agosto (ver `viz/PROGRESO_MAPA.md`,
gap G1). A partir de aquí toda la cadena de `viz/` trabaja offline.

Lee de Athena (workgroup `madrono-tfm-dev-silver-gold`, DB Gold) vía
`UNLOAD ... TO s3://.../gold_slices/` en Parquet, sincroniza a
`viz/data/gold_slices/<tabla>/` y consolida cada tabla en un único
`<tabla>.parquet`.

    AWS_PROFILE=madrono AWS_REGION=eu-west-1 python -m viz.export_gold_slices

Sólo LEE Gold (más un prefijo de escritura efímero en el bucket de
resultados de Athena, que se limpia al final). Cero infra. Idempotente.
"""

from __future__ import annotations

import io
import json
import sys
import uuid
from pathlib import Path

import boto3
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asistente.athena import GOLD_DATABASE, run_athena_query  # noqa: E402

_RESULTS_BUCKET = "madrono-tfm-athena-results"
_OUT = Path(__file__).resolve().parent / "data" / "gold_slices"
_META_TRAFICO = (
    Path(__file__).resolve().parents[1]
    / "asistente" / "modelos" / "stgnn_trafico.meta.json"
)

# columnas mínimas por tabla (el resto no lo usa la animación)
_TABLAS = {
    "trafico_por_punto_hora": (
        "point_id, date, hour, avg_service_level, avg_intensity_vph, lat, lon"
    ),
    "calidad_aire_por_estacion_contaminante_hora": (
        "station_id, pollutant, date, hour, avg_value, unit, lat, lon"
    ),
    "meteorologia_por_estacion_magnitud_hora": (
        "station_id, magnitude, date, hour, avg_value, lat, lon"
    ),
    "ruido_por_estacion_periodo_fecha": (
        "station_id, district, neighbourhood, period, period_name, date, "
        "avg_laeq_db, lat, lon"
    ),
}


def _nodos_stgnn_trafico() -> "list[str]":
    meta = json.loads(_META_TRAFICO.read_text(encoding="utf-8"))
    return sorted(meta["node_index"])


def _unload(tabla: str, columnas: str, run_id: str) -> str:
    where = ""
    if tabla == "trafico_por_punto_hora":
        ids = ", ".join(f"'{p}'" for p in _nodos_stgnn_trafico())
        where = f" WHERE point_id IN ({ids})"
    prefix = f"gold_slices/{run_id}/{tabla}/"
    sql = (
        f"UNLOAD (SELECT {columnas} FROM {tabla}{where}) "
        f"TO 's3://{_RESULTS_BUCKET}/{prefix}' WITH (format='PARQUET', compression='SNAPPY')"
    )
    run_athena_query(sql, GOLD_DATABASE, max_wait_seconds=300)
    return prefix


def _consolida(tabla: str, s3_prefix: str, s3) -> Path:
    """UNLOAD escribe uno o varios parquet **sin extensión** bajo `s3_prefix`.
    Los lee en memoria y los consolida en un único `<tabla>.parquet` local."""
    keys = [
        o["Key"]
        for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=_RESULTS_BUCKET, Prefix=s3_prefix
        )
        for o in page.get("Contents", [])
        if not o["Key"].endswith(("_manifest", ".metadata"))
    ]
    if not keys:
        raise RuntimeError(f"UNLOAD de {tabla} no dejó objetos en s3://{_RESULTS_BUCKET}/{s3_prefix}")
    frames = []
    for k in keys:
        body = s3.get_object(Bucket=_RESULTS_BUCKET, Key=k)["Body"].read()
        frames.append(pd.read_parquet(io.BytesIO(body)))
    df = pd.concat(frames, ignore_index=True)
    out = _OUT / f"{tabla}.parquet"
    df.to_parquet(out, index=False)
    return out


def main() -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    s3 = boto3.client("s3")
    resumen = {}
    prefijos = []
    try:
        for tabla, columnas in _TABLAS.items():
            print(f"UNLOAD {tabla} ...", flush=True)
            prefix = _unload(tabla, columnas, run_id)
            prefijos.append(prefix)
            out = _consolida(tabla, prefix, s3)
            n = len(pd.read_parquet(out))
            resumen[tabla] = {"parquet": str(out.relative_to(_OUT.parents[1])), "filas": n}
            print(f"  -> {out}  ({n} filas)", flush=True)
    finally:
        # limpia los prefijos efímeros del bucket de resultados
        for prefix in prefijos:
            for page in s3.get_paginator("list_objects_v2").paginate(
                Bucket=_RESULTS_BUCKET, Prefix=prefix
            ):
                objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                if objs:
                    s3.delete_objects(Bucket=_RESULTS_BUCKET, Delete={"Objects": objs})

    (_OUT / "MANIFEST.json").write_text(
        json.dumps(
            {
                "generado": pd.Timestamp.utcnow().isoformat(),
                "origen": f"Athena {GOLD_DATABASE} (workgroup madrono-tfm-dev-silver-gold)",
                "motivo": "G1 - congelar Gold antes de que la partition projection deslizante lo tire",
                "tablas": resumen,
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print("\nMANIFEST:", json.dumps(resumen, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
