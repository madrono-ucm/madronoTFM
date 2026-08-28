"""Entry point del feature store (ML_01): Athena (Gold) -> panel horario ->
Parquet.

    python -m modelado.features.build --target calidad_aire \
        --desde 2026-08-15 --hasta 2026-08-27 \
        --out modelado/_data/panel_calidad_aire.parquet

Credenciales: `AWS_PROFILE=madrono` (`eu-west-1`) -- ver `infra/OPERACION.md`.
Los enriquecedores que necesitan el grafo (features de vecinos) o ficheros
externos (festivos) son opcionales por flag; el panel base (calendario +
lags + rolling + targets) no necesita nada más que Athena.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from modelado.features import panel
from modelado.features.athena import query_df

logger = logging.getLogger(__name__)

# (tabla Gold, SQL que proyecta a entity_id / ts / value). `ts` se compone en
# pandas a partir de `date` + `hour`; aquí solo se traen las columnas crudas.
_TARGETS = {
    "calidad_aire": {
        "sql": """
            SELECT concat(station_id, '__', pollutant) AS entity_id,
                   date, hour, avg_value AS value, lat, lon
            FROM calidad_aire_por_estacion_contaminante_hora
            WHERE date BETWEEN '{desde}' AND '{hasta}' AND avg_value IS NOT NULL
        """,
        "graph_tipo": "calidad_aire",
    },
    "trafico": {
        "sql": """
            SELECT point_id AS entity_id, date, hour,
                   avg_service_level AS value, lat, lon
            FROM trafico_por_punto_hora
            WHERE date BETWEEN '{desde}' AND '{hasta}' AND avg_service_level IS NOT NULL
        """,
        "graph_tipo": "trafico",
    },
    "afluencia": {
        # tabla Gold de FIL_06. `nivel_estimado` (bajo/medio/alto/sin_datos)
        # -> 0/1/2/NULL.
        "sql": """
            SELECT lugar_id AS entity_id, date, cast(hora AS integer) AS hour,
                   CASE nivel_estimado WHEN 'bajo' THEN 0 WHEN 'medio' THEN 1
                        WHEN 'alto' THEN 2 ELSE NULL END AS value,
                   lat, lon
            FROM afluencia_lugares_por_lugar_fecha_hora
            WHERE date BETWEEN '{desde}' AND '{hasta}'
        """,
        "graph_tipo": None,
    },
}


def _cargar_festivos(path: "str | None") -> "set":
    if not path:
        return set()
    import datetime as dt

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    fechas = set()
    for rec in data if isinstance(data, list) else data.get("dias", []):
        raw = rec.get("fecha") or rec.get("date") if isinstance(rec, dict) else rec
        try:
            fechas.add(dt.date.fromisoformat(str(raw)[:10]))
        except ValueError:
            continue
    return fechas


def _vecinos_desde_grafo(tipo: str, radio_m: float = 300.0) -> "dict[str, list[str]]":
    """`{entity_id: [entity_id de vecinos]}` para estaciones del mismo `tipo`
    conectadas por `PROXIMO_A` dentro de `radio_m`. `entity_id` = id del nodo
    sin el prefijo `<fuente>:` (mismo criterio que
    `procesamiento/silver_gold/afluencia_lugares/estimada.py`)."""
    import os

    from neo4j import GraphDatabase

    uri, user = os.environ["NEO4J_URI"], os.environ["NEO4J_USERNAME"]
    pwd, db = os.environ["NEO4J_PASSWORD"], os.environ.get("NEO4J_DATABASE", "neo4j")
    q = (
        "MATCH (a:EstacionMedida {tipo:$t})-[p:PROXIMO_A]-(b:EstacionMedida {tipo:$t}) "
        "WHERE p.distancia_m <= $r RETURN a.id AS a, b.id AS b"
    )
    out: "dict[str, list[str]]" = {}
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    try:
        with driver.session(database=db) as s:
            for rec in s.run(q, t=tipo, r=radio_m):
                a = rec["a"].split(":", 1)[-1]
                b = rec["b"].split(":", 1)[-1]
                out.setdefault(a, []).append(b)
    finally:
        driver.close()
    return out


def construir(
    target: str,
    desde: str,
    hasta: str,
    *,
    festivos_path: "str | None" = None,
    con_vecinos: bool = False,
    athena_client=None,
):
    import pandas as pd

    spec = _TARGETS[target]
    gold = query_df(spec["sql"].format(desde=desde, hasta=hasta), athena_client=athena_client)
    if gold.empty:
        raise SystemExit(f"Athena no devolvió filas para {target} en [{desde}, {hasta}]")

    gold["ts"] = pd.to_datetime(gold["date"]) + pd.to_timedelta(gold["hour"].astype(int), unit="h")
    gold["value"] = pd.to_numeric(gold["value"], errors="coerce")
    gold = gold.dropna(subset=["value"])[["entity_id", "ts", "value", "lat", "lon"]]

    vecinos = None
    if con_vecinos and spec["graph_tipo"]:
        vecinos = _vecinos_desde_grafo(spec["graph_tipo"])
        logger.info("vecinos de grafo: %d entidades con al menos un vecino", len(vecinos))

    p = panel.build_panel(
        gold,
        holidays=_cargar_festivos(festivos_path),
        neighbours=vecinos,
    )
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", required=True, choices=sorted(_TARGETS))
    ap.add_argument("--desde", required=True, help="fecha ISO inclusive (yyyy-mm-dd)")
    ap.add_argument("--hasta", required=True, help="fecha ISO inclusive (yyyy-mm-dd)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--festivos", default=None, help="JSON de calendario_laboral_madrid (opcional)")
    ap.add_argument("--con-vecinos", action="store_true", help="añade features de vecinos (necesita Neo4j)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    p = construir(
        args.target, args.desde, args.hasta,
        festivos_path=args.festivos, con_vecinos=args.con_vecinos,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    p.to_parquet(args.out, index=False)

    feat_cols = [c for c in p.columns if c not in ("entity_id", "ts") and not c.startswith("target_h")]
    logger.info(
        "panel %s: %d filas, %d entidades, %s..%s, %d features, targets=%s -> %s",
        args.target, len(p), p["entity_id"].nunique(),
        p["ts"].min(), p["ts"].max(), len(feat_cols),
        [c for c in p.columns if c.startswith("target_h")], args.out,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
