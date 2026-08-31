"""FIL_33 (M2) — `viz/data/prevision_animada.parquet`: por nodo y hora, la
señal observada y la prevista por los dos STGNN de grafo, más el índice de
salud compuesto que colorea el mapa animado.

Entrada: los slices congelados en `viz/data/gold_slices/` (G1) + los ONNX
vendorizados (`asistente/prevision_grafo.py`, sin `torch`). Cero red.

    python -m viz.build_prevision_animada

## Días curados — data-driven (gap G3)

La ventana consultable son ~16 días de agosto 2026. Sin lluvia/ozono/evento
garantizados → se eligen por contraste real de congestión:

- `2026-08-19` — miércoles "normal" de la primera semana completa.
- `2026-08-23` — **domingo tranquilo** (mean service level más bajo con día completo).
- `2026-08-26` — **miércoles cargado** (mean service level más alto).

## Ruido (gap G2)

`gold.ruido_*` es **diario** por `(estación, periodo, fecha)` y sólo ~5 días.
Entra como **constante por distrito** (LAeq medio del slice), no como capa
animada.

## Índice de salud 0-100 (100 = mejor)

    carga = 0.35·norm(sl/4) + 0.30·norm(no2/200) + 0.20·norm(o3/180) + 0.15·norm((db-45)/30)
    salud = 100·(1 - carga)

norm = clip a [0, 1]. Umbrales: `sl` nivel de servicio 0..~4; `no2` 200
µg/m³ (límite horario UE); `o3` 180 µg/m³ (umbral de información); ruido
45-75 dB(A).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asistente import prevision_grafo  # noqa: E402
from modelado.features.build import _DEFAULT_FESTIVOS, _cargar_festivos  # noqa: E402

_VIZ = Path(__file__).resolve().parent
_SLICES = _VIZ / "data" / "gold_slices"
_OUT = _VIZ / "data" / "prevision_animada.parquet"
_GRAFO = json.loads((_VIZ / "grafo_madrid.json").read_text(encoding="utf-8"))

DIAS = ("2026-08-19", "2026-08-23", "2026-08-26")
HORIZONTES = (1, 3, 6)
_POLL = ("NO2", "O3")


def _serie_por_nodo(df, key_col, val_col):
    """`{clave: {datetime: valor}}` a partir de columnas `date`+`hour`."""
    df = df.dropna(subset=[val_col]).copy()
    df["ts"] = pd.to_datetime(df["date"]) + pd.to_timedelta(df["hour"], unit="h")
    out: "dict[str, dict[datetime, float]]" = {}
    for k, t, v in zip(df[key_col], df["ts"], df[val_col]):
        out.setdefault(str(k), {})[t.to_pydatetime()] = float(v)
    return out


def _idw(lat, lon, estaciones, valores, power=2.0):
    """IDW desde las ~11 estaciones de aire a un nodo. `estaciones` =
    `{station_id: (lat, lon)}`, `valores` = `{station_id: valor}`."""
    from grafo.geo import haversine_m

    num = den = 0.0
    for sid, (sla, slo) in estaciones.items():
        v = valores.get(sid)
        if v is None:
            continue
        d = max(haversine_m(lat, lon, sla, slo), 1.0)
        w = 1.0 / d**power
        num += w * v
        den += w
    return num / den if den else None


def _ruido_por_distrito() -> "dict[str, float]":
    """LAeq medio por **nombre de distrito** (la columna `district` del slice
    de ruido son nombres: "Centro", "Retiro", ...). Se prefiere el periodo
    "T" (24 h); si no hay, media de todos los periodos."""
    df = pd.read_parquet(_SLICES / "ruido_por_estacion_periodo_fecha.parquet").dropna(subset=["avg_laeq_db"])
    t = df[df["period"] == "T"]
    base = t if not t.empty else df
    return base.groupby("district")["avg_laeq_db"].mean().round(1).to_dict()


def _norm(x, hi, lo=0.0):
    if x is None:
        return 0.0
    return min(1.0, max(0.0, (x - lo) / (hi - lo)))


def _salud(sl, no2, o3, db):
    carga = (
        0.35 * _norm(sl, 4.0)
        + 0.30 * _norm(no2, 200.0)
        + 0.20 * _norm(o3, 180.0)
        + 0.15 * _norm(db, 75.0, 45.0)
    )
    return round(100.0 * (1.0 - carga), 1)


def construir() -> pd.DataFrame:
    festivos = frozenset(_cargar_festivos(_DEFAULT_FESTIVOS))

    traf = pd.read_parquet(_SLICES / "trafico_por_punto_hora.parquet")
    aire = pd.read_parquet(_SLICES / "calidad_aire_por_estacion_contaminante_hora.parquet")
    serie_traf = _serie_por_nodo(traf, "point_id", "avg_service_level")
    aire["ent"] = aire["station_id"].astype(str) + "__" + aire["pollutant"].astype(str)
    serie_aire = _serie_por_nodo(aire, "ent", "avg_value")

    est_aire = {s: (v["lat"], v["lon"]) for s, v in _GRAFO["estaciones_aire"].items()}
    ruido_dist = _ruido_por_distrito()  # keyed por nombre de distrito
    ruido_medio = round(sum(ruido_dist.values()) / len(ruido_dist), 1)  # 4 distritos sin sonómetro
    id_a_nombre = _GRAFO["distrito_id_a_nombre"]
    nodos = _GRAFO["nodos"]

    filas = []
    for dia in DIAS:
        d0 = datetime.fromisoformat(dia)
        for h in range(24):
            ancla = d0 + timedelta(hours=h)
            pred_traf, _ = prevision_grafo.predecir(serie_traf, ancla, target="trafico", festivos=festivos)
            pred_aire, _ = prevision_grafo.predecir(serie_aire, ancla, target="calidad_aire", festivos=festivos)

            # previsión de aire por estación y contaminante (h1) -> IDW a nodos
            val_est = {p: {} for p in _POLL}
            for est in est_aire:
                for p in _POLL:
                    yh = pred_aire.get(f"{est}__{p}")
                    if yh is not None:
                        val_est[p][est] = yh[0]  # h1

            for n in nodos:
                nid, la, lo, dist = n["id"], n["lat"], n["lon"], n["distrito"]
                obs = serie_traf.get(nid, {}).get(ancla)
                yh = pred_traf.get(nid, [None] * 3)
                act = {hz: serie_traf.get(nid, {}).get(ancla + timedelta(hours=hz)) for hz in HORIZONTES}
                no2 = _idw(la, lo, est_aire, val_est["NO2"])
                o3 = _idw(la, lo, est_aire, val_est["O3"])
                db = ruido_dist.get(id_a_nombre.get(dist), ruido_medio)
                filas.append(
                    {
                        "node_id": nid, "lat": la, "lon": lo, "district": dist,
                        "day": dia, "hour": h, "ts": ancla.isoformat(),
                        "dow": ancla.weekday(),
                        "y_traf_obs": None if obs is None else round(obs, 3),
                        "y_traf_persist": None if obs is None else round(obs, 3),
                        "y_traf_h1": None if yh[0] is None else round(yh[0], 3),
                        "y_traf_h3": None if yh[1] is None else round(yh[1], 3),
                        "y_traf_h6": None if yh[2] is None else round(yh[2], 3),
                        "y_traf_act_h1": None if act[1] is None else round(act[1], 3),
                        "y_traf_act_h3": None if act[3] is None else round(act[3], 3),
                        "y_traf_act_h6": None if act[6] is None else round(act[6], 3),
                        "no2": None if no2 is None else round(no2, 1),
                        "o3": None if o3 is None else round(o3, 1),
                        "noise_db": db,
                        "health_index": _salud(yh[0], no2, o3, db),
                    }
                )
        print(f"  {dia} ok ({len(filas)} filas acumuladas)", flush=True)
    return pd.DataFrame(filas)


def main() -> int:
    df = construir()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_OUT, index=False)
    print(f"\n{_OUT}  {df.shape}")
    print(df[["y_traf_obs", "y_traf_h1", "no2", "o3", "noise_db", "health_index"]].describe().round(2).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
