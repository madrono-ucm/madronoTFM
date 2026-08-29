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
import datetime as dt
import json
import logging
from pathlib import Path

from modelado.features import exogenas, panel
from modelado.features.athena import GOLD_DATABASE, query_df

logger = logging.getLogger(__name__)

_SILVER_DATABASE = "madrono-tfm_dev_silver"

# Calendario laboral de Madrid: el productor deja una muestra completa del
# año commiteada (no hay pipeline Silver/Gold; ver `tasks/ML_01`). Se usa
# por defecto para no depender de un flag.
_DEFAULT_FESTIVOS = (
    Path(__file__).resolve().parents[2]
    / "ingesta"
    / "capturas"
    / "samples"
    / "calendario_laboral_madrid_sample.json"
)

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


def _es_festivo(rec: dict) -> bool:
    """Un registro del calendario laboral marca festivo -- tolerante al
    formato (`is_holiday` bool/str, o `day_type == "festivo"`)."""
    v = rec.get("is_holiday")
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "si", "sí")
    if v is not None:
        return bool(v)
    return str(rec.get("day_type", "")).strip().lower() == "festivo"


def _cargar_festivos(path: "str | Path | None") -> "set":
    """Fechas festivas de Madrid desde el JSON de
    `calendario_laboral_madrid` (lista de registros con `date`/`fecha` +
    `is_holiday`). Solo entran los días efectivamente festivos -- no todo el
    calendario."""
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        logger.warning("fichero de festivos no encontrado: %s -- sin feature de festivo", p)
        return set()

    data = json.loads(p.read_text(encoding="utf-8"))
    registros = data if isinstance(data, list) else data.get("dias", data.get("data", []))
    fechas = set()
    for rec in registros:
        if not isinstance(rec, dict) or not _es_festivo(rec):
            continue
        raw = rec.get("fecha") or rec.get("date")
        try:
            fechas.add(dt.date.fromisoformat(str(raw)[:10]))
        except (ValueError, TypeError):
            continue
    return fechas


_METEO_SQL = """
    SELECT station_id, date, hour, magnitude, avg_value, lat, lon
    FROM meteorologia_por_estacion_magnitud_hora
    WHERE date BETWEEN '{desde}' AND '{hasta}'
      AND avg_value IS NOT NULL
      AND magnitude IN ({magnitudes})
"""

_PREVISION_SQL = """
    SELECT valid_date, elaborated_at, temperature_max_c, temperature_min_c,
           precipitation_probability_pct, wind_speed_kmh, humidity_max_pct
    FROM aemet_prevision
    WHERE fecha BETWEEN '{desde_ext}' AND '{hasta}'
"""


def _meteo_long(desde: str, hasta: str, *, athena_client=None):
    """Formato largo de la meteo Gold para la ventana: `station_id`, `ts`,
    `magnitude`, `avg_value`, `lat`, `lon`."""
    import pandas as pd

    mags = ", ".join(f"'{m}'" for m in exogenas.MAGNITUDES_METEO)
    df = query_df(
        _METEO_SQL.format(desde=desde, hasta=hasta, magnitudes=mags),
        athena_client=athena_client,
    )
    if df.empty:
        return df
    df["station_id"] = df["station_id"].astype(str)
    df["ts"] = pd.to_datetime(df["date"]) + pd.to_timedelta(df["hour"].astype(int), unit="h")
    df["avg_value"] = pd.to_numeric(df["avg_value"], errors="coerce")
    return df[["station_id", "ts", "magnitude", "avg_value", "lat", "lon"]]


def _prevision_diaria(desde: str, hasta: str, *, athena_client=None):
    """Panel de previsión AEMET por día (`forecast_panel`). Se pide una
    semana extra hacia atrás para tener elaboraciones previas al primer día
    de la ventana."""
    import pandas as pd

    desde_ext = (dt.date.fromisoformat(desde) - dt.timedelta(days=7)).isoformat()
    raw = query_df(
        _PREVISION_SQL.format(desde_ext=desde_ext, hasta=hasta),
        database=_SILVER_DATABASE,
        athena_client=athena_client,
    )
    if raw.empty:
        return raw
    prev = exogenas.forecast_panel(raw)
    if prev.empty:
        return prev
    return prev[(prev["date"] >= desde) & (prev["date"] <= hasta)].reset_index(drop=True)


def _neo4j_driver():
    import os

    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    ), os.environ.get("NEO4J_DATABASE", "neo4j")


def _entidades_cerca_de_lugar(tipo: str, radio_m: float = 300.0) -> "set[str]":
    """Ids (sin prefijo `<fuente>:`) de las `:EstacionMedida` de `tipo` que
    tienen un `PROXIMO_A` a un `:Lugar` dentro de `radio_m` -- el subconjunto
    que le importa al asistente / a la señal de afluencia. Ver la discusión
    en `tasks/ML_01`: para el target de congestión "de red" se usa `all`;
    para la fusión / afluencia, este subconjunto (~1.800 de ~4.700 en
    tráfico)."""
    driver, db = _neo4j_driver()
    q = (
        "MATCH (e:EstacionMedida {tipo:$t})-[p:PROXIMO_A]-(:Lugar) "
        "WHERE p.distancia_m <= $r RETURN DISTINCT e.id AS id"
    )
    try:
        with driver.session(database=db) as s:
            return {r["id"].split(":", 1)[-1] for r in s.run(q, t=tipo, r=radio_m)}
    finally:
        driver.close()


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
    scope: str = "all",
    festivos_path: "str | Path | None" = _DEFAULT_FESTIVOS,
    con_vecinos: bool = False,
    con_meteo: bool = True,
    con_prevision: bool = True,
    athena_client=None,
):
    import pandas as pd

    spec = _TARGETS[target]
    gold = query_df(spec["sql"].format(desde=desde, hasta=hasta), athena_client=athena_client)
    if gold.empty:
        raise SystemExit(f"Athena no devolvió filas para {target} en [{desde}, {hasta}]")

    # `query_df` lee el CSV de Athena con `read_csv` -> infiere tipos; hay
    # `entity_id` que son numéricos (`point_id` de tráfico) y se cargan como
    # int. El resto del pipeline los trata como str (split por `__`, merge
    # con ids del grafo).
    gold["entity_id"] = gold["entity_id"].astype(str)
    gold["ts"] = pd.to_datetime(gold["date"]) + pd.to_timedelta(gold["hour"].astype(int), unit="h")
    gold["value"] = pd.to_numeric(gold["value"], errors="coerce")
    gold = gold.dropna(subset=["value"])[["entity_id", "ts", "value", "lat", "lon"]]

    if scope == "grafo-lugares":
        if not spec["graph_tipo"]:
            raise SystemExit(f"scope=grafo-lugares no aplica a {target} (sin nodo de sensor en el grafo)")
        cerca = _entidades_cerca_de_lugar(spec["graph_tipo"])
        # `entity_id` de calidad_aire es `station__pollutant`; el grafo indexa
        # por `station` -> se compara la parte anterior a `__`.
        est = gold["entity_id"].str.split("__", n=1).str[0]
        antes = gold["entity_id"].nunique()
        gold = gold[est.isin(cerca)]
        logger.info(
            "scope=grafo-lugares: %d/%d entidades (%d estaciones cerca de un :Lugar)",
            gold["entity_id"].nunique(), antes, len(cerca),
        )
        if gold.empty:
            raise SystemExit("scope=grafo-lugares dejó el panel vacío")

    vecinos = None
    if con_vecinos and spec["graph_tipo"]:
        vecinos = _vecinos_desde_grafo(spec["graph_tipo"])
        logger.info("vecinos de grafo: %d entidades con al menos un vecino", len(vecinos))

    weather_df = None
    if con_meteo:
        entidades_latlon = {
            eid: (r.lat, r.lon)
            for eid, r in gold.drop_duplicates("entity_id").set_index("entity_id").iterrows()
        }
        meteo = _meteo_long(desde, hasta, athena_client=athena_client)
        weather_df = exogenas.weather_panel(meteo, entidades_latlon)
        cols_meteo = [c for c in weather_df.columns if c.startswith("meteo_")]
        logger.info(
            "meteo: %d filas, %d entidades con estación cercana, columnas %s",
            len(weather_df), weather_df["entity_id"].nunique() if not weather_df.empty else 0,
            cols_meteo,
        )

    daily_df = None
    if con_prevision:
        daily_df = _prevision_diaria(desde, hasta, athena_client=athena_client)
        logger.info(
            "previsión AEMET: %d días con previsión previa (%s)",
            len(daily_df),
            [c for c in daily_df.columns if c != "date"] if not daily_df.empty else [],
        )

    p = panel.build_panel(
        gold,
        holidays=_cargar_festivos(festivos_path),
        neighbours=vecinos,
        weather_df=weather_df,
        daily_df=daily_df,
    )
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", required=True, choices=sorted(_TARGETS))
    ap.add_argument("--desde", required=True, help="fecha ISO inclusive (yyyy-mm-dd)")
    ap.add_argument("--hasta", required=True, help="fecha ISO inclusive (yyyy-mm-dd)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument(
        "--scope", default="all", choices=["all", "grafo-lugares"],
        help="'all' = toda la red (target de congestión de red); 'grafo-lugares' = "
        "solo sensores con PROXIMO_A a un :Lugar (fusión / afluencia). Necesita Neo4j.",
    )
    ap.add_argument(
        "--festivos", default=str(_DEFAULT_FESTIVOS),
        help="JSON de calendario_laboral_madrid (por defecto: la muestra commiteada)",
    )
    ap.add_argument("--con-vecinos", action="store_true", help="añade features de vecinos (necesita Neo4j)")
    ap.add_argument(
        "--sin-meteo", action="store_true",
        help="no unir la meteo observada (join espacial a la estación más cercana)",
    )
    ap.add_argument(
        "--sin-prevision", action="store_true",
        help="no unir la previsión AEMET diaria (feature exógena de futuro conocido)",
    )
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    p = construir(
        args.target, args.desde, args.hasta,
        scope=args.scope, festivos_path=args.festivos, con_vecinos=args.con_vecinos,
        con_meteo=not args.sin_meteo, con_prevision=not args.sin_prevision,
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
