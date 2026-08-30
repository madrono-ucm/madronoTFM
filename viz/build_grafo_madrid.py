"""FIL_32 — grafo canónico de Madrid: el artefacto que comparten la
visualización animada (`FIL_34`) y, si se hace, `ruta_saludable` (`FIL_37`).

Se deriva de lo que **ya usan los modelos** — sin construir un grafo nuevo:

- nodos + coordenadas + grafo `coords-knn8`: de
  `asistente/modelos/stgnn_trafico.meta.json` (`node_coords`, `edge_index`,
  `edge_weight`, `importancia_aristas`).
- distrito por nodo: point-in-polygon contra
  `viz/assets/distritos_madrid.geojson` (21 distritos, Bronce
  `barrios_distritos`), con `grafo/geo.py` (puro Python).
- estaciones de calidad del aire: de `stgnn_calidad_aire.meta.json`.
- estaciones de ruido: del slice congelado `viz/data/gold_slices/` (G1).

Salida: `viz/grafo_madrid.json`.

    python -m viz.build_grafo_madrid

Función pura sobre ficheros del repo — sin credenciales, sin red.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grafo.geo import haversine_m, point_in_geometry  # noqa: E402

_RAIZ = Path(__file__).resolve().parents[1]
_MODELOS = _RAIZ / "asistente" / "modelos"
_ASSETS = Path(__file__).resolve().parent / "assets"
_SLICES = Path(__file__).resolve().parent / "data" / "gold_slices"
_OUT = Path(__file__).resolve().parent / "grafo_madrid.json"


def _distrito_por_punto(lat, lon, features):
    for f in features:
        if point_in_geometry(lat, lon, f["geometry"]):
            return f["properties"]["district_id"]
    return None


def _nodos(node_coords, features):
    nodos = []
    for nid, (lat, lon) in node_coords.items():
        nodos.append(
            {
                "id": nid,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "distrito": _distrito_por_punto(lat, lon, features),
            }
        )
    # Fallback: los polígonos vienen simplificados (tol 1e-4 deg ~ 11 m) y
    # dejan micro-huecos en las fronteras entre distritos. Un nodo que no cae
    # en ningún polígono hereda el distrito de su vecino más cercano que sí.
    con = [n for n in nodos if n["distrito"] is not None]
    for n in nodos:
        if n["distrito"] is None and con:
            cercano = min(con, key=lambda c: haversine_m(n["lat"], n["lon"], c["lat"], c["lon"]))
            n["distrito"] = cercano["distrito"]
            n["distrito_por_vecino"] = True
    return nodos


def _aristas(edge_index, edge_weight, node_coords, idx_a_id):
    """`edge_index` es `[2, E]` dirigido y simétrico; se pliega a no dirigido,
    se queda el peso máximo por par y calcula la longitud haversine."""
    plegado: "dict[tuple[str, str], float]" = {}
    src, dst = edge_index
    for k in range(len(src)):
        a, b = idx_a_id[src[k]], idx_a_id[dst[k]]
        if a == b:
            continue
        clave = (a, b) if a < b else (b, a)
        plegado[clave] = max(plegado.get(clave, 0.0), float(edge_weight[k]))
    aristas = []
    for (a, b), w in sorted(plegado.items()):
        (la1, lo1), (la2, lo2) = node_coords[a], node_coords[b]
        aristas.append(
            {
                "a": a,
                "b": b,
                "peso": round(w, 6),
                "length_m": round(haversine_m(la1, lo1, la2, lo2), 1),
            }
        )
    return aristas


def _estaciones_aire(meta_aire, node_coords):
    """`station_id -> {lat, lon, nodo_mas_cercano}` (una fila por estación,
    no por `station__contaminante`)."""
    por_estacion: "dict[str, tuple[float, float]]" = {}
    for clave, (lat, lon) in meta_aire["node_coords"].items():
        est = clave.split("__", 1)[0]
        por_estacion.setdefault(est, (lat, lon))
    out = {}
    for est, (lat, lon) in por_estacion.items():
        nodo = min(node_coords, key=lambda nid: haversine_m(lat, lon, *node_coords[nid]))
        out[est] = {"lat": round(lat, 6), "lon": round(lon, 6), "nodo_mas_cercano": nodo}
    return out


def _estaciones_ruido(features):
    """`station_id -> {lat, lon, distrito}` del slice congelado de ruido.
    El ruido es diario y se usa **por distrito** (gap G2) — no mapea a nodo."""
    import pandas as pd

    p = _SLICES / "ruido_por_estacion_periodo_fecha.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p)[["station_id", "district", "lat", "lon"]].drop_duplicates("station_id")
    out = {}
    for _, r in df.iterrows():
        dist = r["district"]
        if dist is None or (isinstance(dist, float)):
            dist = _distrito_por_punto(r["lat"], r["lon"], features)
        out[str(r["station_id"])] = {
            "lat": round(float(r["lat"]), 6),
            "lon": round(float(r["lon"]), 6),
            "distrito": str(dist) if dist is not None else None,
        }
    return out


def construir() -> dict:
    meta = json.loads((_MODELOS / "stgnn_trafico.meta.json").read_text(encoding="utf-8"))
    meta_aire = json.loads((_MODELOS / "stgnn_calidad_aire.meta.json").read_text(encoding="utf-8"))
    features = json.loads((_ASSETS / "distritos_madrid.geojson").read_text(encoding="utf-8"))["features"]

    node_coords = {k: tuple(v) for k, v in meta["node_coords"].items()}
    idx_a_id = {i: nid for nid, i in meta["node_index"].items()}

    nodos = _nodos(node_coords, features)
    aristas = _aristas(meta["edge_index"], meta["edge_weight"], node_coords, idx_a_id)

    distrito_a_nodos: "dict[str, list[str]]" = {}
    for n in nodos:
        distrito_a_nodos.setdefault(n["distrito"] or "sin_distrito", []).append(n["id"])

    return {
        "origen_grafo": meta["origen_grafo"],
        "n_nodos": len(nodos),
        "n_aristas": len(aristas),
        "nodos": nodos,
        "aristas": aristas,
        "importancia_aristas": meta["importancia_aristas"],
        "estaciones_aire": _estaciones_aire(meta_aire, node_coords),
        "estaciones_ruido": _estaciones_ruido(features),
        "distrito_a_nodos": distrito_a_nodos,
        "distritos_geojson": "viz/assets/distritos_madrid.geojson",
        "_fuente": "stgnn_trafico.meta.json + stgnn_calidad_aire.meta.json + Bronce barrios_distritos + gold_slices/ruido (G1)",
    }


def main() -> int:
    grafo = construir()
    _OUT.write_text(json.dumps(grafo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    sin_distrito = sum(1 for n in grafo["nodos"] if n["distrito"] is None)
    print(f"{_OUT}")
    print(f"  nodos={grafo['n_nodos']}  aristas={grafo['n_aristas']}  "
          f"sin_distrito={sin_distrito}  estaciones_aire={len(grafo['estaciones_aire'])}  "
          f"estaciones_ruido={len(grafo['estaciones_ruido'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
