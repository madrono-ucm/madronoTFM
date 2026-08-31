"""FIL_37 — genera `asistente/modelos/grafo_ruta.json`, el artefacto
vendorizado que la 12.ª tool MCP `ruta_saludable` consume **sin depender de
`viz/` ni de `networkx`** (mismo criterio que `asistente/athena.py` respecto
a `grafo/`).

Contiene: el grafo (nodos + adyacencia con `length_m`), la exposición
prevista por nodo/día/hora (tráfico h1, NO₂, O₃) de
`viz/data/prevision_animada.parquet`, el ruido diario por distrito, los
lugares de referencia y los pesos de perfil.

    python -m viz.build_grafo_ruta

Cero red. La tool sirve los **3 días curados** como demostración de
metodología (§7.4), igual que los STGNN de grafo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from viz.rutas import LUGARES, PERFILES  # noqa: E402

_VIZ = Path(__file__).resolve().parent
_GRAFO = json.loads((_VIZ / "grafo_madrid.json").read_text(encoding="utf-8"))
_PARQUET = _VIZ / "data" / "prevision_animada.parquet"
_OUT = Path(__file__).resolve().parents[1] / "asistente" / "modelos" / "grafo_ruta.json"


def construir() -> dict:
    df = pd.read_parquet(_PARQUET)
    nodos = [
        {"id": n["id"], "lat": round(n["lat"], 6), "lon": round(n["lon"], 6),
         "distrito": n["distrito"], "distrito_nombre": n.get("distrito_nombre")}
        for n in _GRAFO["nodos"]
    ]
    ids = {n["id"] for n in nodos}
    adj: "dict[str, list]" = {n["id"]: [] for n in nodos}
    for e in _GRAFO["aristas"]:
        if e["a"] in ids and e["b"] in ids:
            adj[e["a"]].append([e["b"], e["length_m"]])
            adj[e["b"]].append([e["a"], e["length_m"]])

    # exposición cuantizada a int para no inflar el artefacto: traf = nivel de
    # servicio ×100, NO₂/O₃ = µg/m³ redondeado. -1 = sin dato.
    idx = {n["id"]: i for i, n in enumerate(nodos)}
    expo: "dict" = {}
    for (dia, h), g in df.groupby(["day", "hour"]):
        fila = [[-1, -1, -1] for _ in nodos]
        for r in g.itertuples():
            fila[idx[r.node_id]] = [
                -1 if pd.isna(r.y_traf_h1) else round(float(r.y_traf_h1) * 100),
                -1 if pd.isna(r.no2) else round(float(r.no2)),
                -1 if pd.isna(r.o3) else round(float(r.o3)),
            ]
        expo.setdefault(str(dia), {})[int(h)] = fila
    ruido = (
        df.dropna(subset=["noise_db"])
        .groupby("district")["noise_db"].mean().round(1).to_dict()
    )

    return {
        "_fuente": "viz/grafo_madrid.json + viz/data/prevision_animada.parquet (FIL_37)",
        "dias": sorted(df["day"].unique().tolist()),
        "nodos": nodos,
        "adyacencia": adj,
        "exposicion": expo,           # {dia: {hora: {node_id: [traf_h1, no2, o3]}}}
        "ruido_distrito": ruido,      # {distrito_id: LAeq_dB}
        "lugares": {k: [round(v[0], 5), round(v[1], 5)] for k, v in LUGARES.items()},
        "perfiles": PERFILES,
        "norm": {"traf": 3.0, "no2": 200.0, "o3": 180.0, "noise": [45.0, 75.0]},
    }


def main() -> int:
    g = construir()
    _OUT.write_text(json.dumps(g, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kb = _OUT.stat().st_size / 1024
    print(f"{_OUT}  ({kb:,.0f} KB)  nodos={len(g['nodos'])} dias={g['dias']} lugares={len(g['lugares'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
