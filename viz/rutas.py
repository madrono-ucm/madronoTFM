"""FIL_37 (M6) — `ruta_saludable`: enrutado multi-objetivo sobre el grafo de
Madrid con coste de arista = distancia + exposición **prevista** (tráfico,
NO₂, O₃, ruido), ponderada por perfil.

- Grafo: `viz/grafo_madrid.json` (`coords-knn8`, 1.798 nodos).
- Exposición por nodo y hora: `viz/data/prevision_animada.parquet`.
- Perfiles: `general`, `ciclista`, `sensible_aire`, `sensible_ruido`.

Escribe `viz/mapa/rutas.json` (rutas precomputadas para la capa E3 del mapa)
y expone `ruta()` / `mejor_hora()` / `pareto()` para el resto (tests, un
posible tool MCP, la memoria §7).

    python -m viz.rutas

Cero red, cero credenciales.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import networkx as nx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from grafo.geo import haversine_m  # noqa: E402

_VIZ = Path(__file__).resolve().parent
_GRAFO = json.loads((_VIZ / "grafo_madrid.json").read_text(encoding="utf-8"))
_PARQUET = _VIZ / "data" / "prevision_animada.parquet"
_OUT = _VIZ / "mapa" / "rutas.json"

# lugar -> (lat, lon). Referencias conocidas; el enrutado usa el nodo más cercano.
LUGARES = {
    "Atocha": (40.4066, -3.6895),
    "Sol": (40.4169, -3.7033),
    "Moncloa": (40.4351, -3.7196),
    "Nuevos Ministerios": (40.4462, -3.6922),
    "Retiro": (40.4152, -3.6844),
    "Bernabéu": (40.4531, -3.6883),
    "Metropolitano": (40.4362, -3.5995),
    "Plaza Elíptica": (40.3852, -3.7182),
    "Cibeles": (40.4193, -3.6934),
    "Chamartín": (40.4726, -3.6828),
    "Príncipe Pío": (40.4207, -3.7199),
    "Plaza Castilla": (40.4669, -3.6884),
    "Legazpi": (40.3911, -3.6952),
    "Ventas": (40.4319, -3.6636),
}

# perfil -> pesos (dist en km; exposición normalizada 0..~1 por señal)
# Un perfil = un vector de pesos por señal. Compartido por `ruta_saludable`
# (FIL_37) y la capa social del mapa (FIL_45). `dist` solo lo usa el
# enrutado; la capa social usa los pesos de señal.
PERFILES = {
    "general":            {"dist": 1.0, "traf": 0.30, "no2": 0.30, "o3": 0.20, "noise": 0.20},
    "ciclista":           {"dist": 0.6, "traf": 0.50, "no2": 0.60, "o3": 0.40, "noise": 0.40},
    "sensible_aire":      {"dist": 0.8, "traf": 0.20, "no2": 0.90, "o3": 0.70, "noise": 0.20},
    "sensible_ruido":     {"dist": 0.8, "traf": 0.30, "no2": 0.30, "o3": 0.20, "noise": 0.90},
    # FIL_45 — perfiles de sensibilidad
    "asma_epoc":          {"dist": 0.7, "traf": 0.20, "no2": 1.00, "o3": 0.85, "noise": 0.20},
    "mayor":              {"dist": 0.9, "traf": 0.25, "no2": 0.55, "o3": 0.70, "noise": 0.45},
    "infancia":           {"dist": 0.8, "traf": 0.55, "no2": 0.75, "o3": 0.55, "noise": 0.35},
    "movilidad_reducida": {"dist": 1.3, "traf": 0.35, "no2": 0.45, "o3": 0.35, "noise": 0.80},
    "trabajo_exterior":   {"dist": 0.5, "traf": 0.40, "no2": 0.75, "o3": 0.75, "noise": 0.50},
}
_NORM = {"traf": 300.0, "no2": 200.0, "o3": 180.0, "noise": (45.0, 75.0)}  # traf en unidades *100


def _grafo_nx() -> "tuple[nx.Graph, dict]":
    g = nx.Graph()
    coord = {n["id"]: (n["lat"], n["lon"]) for n in _GRAFO["nodos"]}
    for n in _GRAFO["nodos"]:
        g.add_node(n["id"], lat=n["lat"], lon=n["lon"], distrito=n["distrito"])
    for e in _GRAFO["aristas"]:
        g.add_edge(e["a"], e["b"], length_m=e["length_m"])
    # trabajar en la componente conexa mayor (coords-knn8 deja ~137 sueltos)
    mayor = max(nx.connected_components(g), key=len)
    return g.subgraph(mayor).copy(), coord


def _nodo_cercano(g: nx.Graph, lat: float, lon: float) -> str:
    return min(g.nodes, key=lambda n: haversine_m(lat, lon, g.nodes[n]["lat"], g.nodes[n]["lon"]))


def _exposicion_horaria(dia: str) -> "dict[int, dict[str, dict]]":
    """`{hora: {node_id: {traf, no2, o3, noise}}}` para `dia`."""
    df = pd.read_parquet(_PARQUET)
    df = df[df["day"] == dia]
    out: dict = {}
    for h, g in df.groupby("hour"):
        out[int(h)] = {
            r.node_id: {
                "traf": 0.0 if pd.isna(r.y_traf_h1) else float(r.y_traf_h1) * 100,
                "no2": 0.0 if pd.isna(r.no2) else float(r.no2),
                "o3": 0.0 if pd.isna(r.o3) else float(r.o3),
                "noise": 55.0 if pd.isna(r.noise_db) else float(r.noise_db),
            }
            for r in g.itertuples()
        }
    return out


def _n(sig: str, v: float) -> float:
    if sig == "noise":
        lo, hi = _NORM["noise"]
        return max(0.0, min(1.0, (v - lo) / (hi - lo)))
    return max(0.0, min(1.0, v / _NORM[sig]))


def _coste_arista(u, v, exp_h, w) -> float:
    eu, ev = exp_h.get(u, {}), exp_h.get(v, {})
    expo = 0.0
    for sig in ("traf", "no2", "o3", "noise"):
        m = 0.5 * (_n(sig, eu.get(sig, 0.0)) + _n(sig, ev.get(sig, 0.0)))
        expo += w[sig] * m
    return expo  # + término de distancia se añade fuera (necesita length_m)


def _ruta_con_pesos(g, exp_h, w, o, d):
    def peso(u, v, data):
        return w["dist"] * (data["length_m"] / 1000.0) + _coste_arista(u, v, exp_h, w)
    path = nx.shortest_path(g, o, d, weight=peso)
    return path


_SIGS = ("traf", "no2", "o3", "noise")


def _metricas(g, exp_h, path, w) -> dict:
    """Exposición **acumulada por arista** — la MISMA agregación que
    `_coste_arista` minimiza (`FIL_43`): `Σ_aristas 0.5·(extremo_u+extremo_v)`,
    normalizada por señal, y su combinación ponderada por perfil
    `E_ponderada` (el término de exposición del coste de Dijkstra). Al ser lo
    optimizado, `E_ponderada` de la ruta sana nunca supera al de la rápida.
    Se guardan también las sumas **brutas** por señal para un "cambio"
    legible."""
    dist = sum(g[path[i]][path[i + 1]]["length_m"] for i in range(len(path) - 1))
    norm = {s: 0.0 for s in _SIGS}
    bruta = {s: 0.0 for s in _SIGS}
    for i in range(len(path) - 1):
        eu, ev = exp_h.get(path[i], {}), exp_h.get(path[i + 1], {})
        for s in _SIGS:
            norm[s] += 0.5 * (_n(s, eu.get(s, 0.0)) + _n(s, ev.get(s, 0.0)))
            bruta[s] += 0.5 * (eu.get(s, 0.0) + ev.get(s, 0.0))
    E = sum(w[s] * norm[s] for s in _SIGS)
    return {
        "n_nodos": len(path),
        "dist_m": round(dist, 1),
        "E_ponderada": round(E, 4),
        "expo_norm": {s: round(norm[s], 3) for s in _SIGS},
        "expo_bruta": {s: round(bruta[s], 1) for s in _SIGS},
    }


def ruta(origen: str, destino: str, perfil: str = "general", *, dia: str, hora: int) -> dict:
    """Ruta saludable vs ruta rápida entre dos lugares, a una hora dada."""
    if perfil not in PERFILES:
        raise ValueError(f"perfil {perfil!r} no válido; usa {list(PERFILES)}")
    g, _ = _grafo_nx()
    exp = _exposicion_horaria(dia)
    exp_h = exp[hora]
    o = _nodo_cercano(g, *LUGARES[origen])
    d = _nodo_cercano(g, *LUGARES[destino])

    w = PERFILES[perfil]
    w_rapida = {"dist": 1.0, "traf": 0.0, "no2": 0.0, "o3": 0.0, "noise": 0.0}
    p_sana = _ruta_con_pesos(g, exp_h, w, o, d)
    p_rapida = _ruta_con_pesos(g, exp_h, w_rapida, o, d)

    m_sana = _metricas(g, exp_h, p_sana, w)
    m_rapida = _metricas(g, exp_h, p_rapida, w)
    delta_dist = (m_sana["dist_m"] - m_rapida["dist_m"]) / max(m_rapida["dist_m"], 1) * 100
    # headline: reducción de la exposición PONDERADA (lo que Dijkstra minimiza)
    # -> nunca negativa para la ruta sana (FIL_43).
    reduccion = (m_rapida["E_ponderada"] - m_sana["E_ponderada"]) / max(m_rapida["E_ponderada"], 1e-9) * 100
    # por señal: CAMBIO (puede ser ±, la ruta sana canjea unas señales por otras)
    cambio = {
        s: round((m_rapida["expo_bruta"][s] - m_sana["expo_bruta"][s]) / max(m_rapida["expo_bruta"][s], 1e-6) * 100, 1)
        for s in _SIGS
    }
    return {
        "origen": origen, "destino": destino, "perfil": perfil, "dia": dia, "hora": hora,
        "nodo_origen": o, "nodo_destino": d,
        "ruta_sana": {"path": p_sana, "coords": [[g.nodes[n]["lon"], g.nodes[n]["lat"]] for n in p_sana], **m_sana},
        "ruta_rapida": {"path": p_rapida, "coords": [[g.nodes[n]["lon"], g.nodes[n]["lat"]] for n in p_rapida], **m_rapida},
        "delta_dist_pct": round(delta_dist, 1),
        "reduccion_exposicion_pct": round(max(reduccion, 0.0), 1),
        "cambio_por_senal_pct": cambio,
    }


def mejor_hora(origen: str, destino: str, perfil: str, *, dia: str, ventana=range(24)) -> dict:
    """Hora de la ventana que minimiza la exposición combinada de la ruta sana."""
    g, _ = _grafo_nx()
    exp = _exposicion_horaria(dia)
    o = _nodo_cercano(g, *LUGARES[origen])
    d = _nodo_cercano(g, *LUGARES[destino])
    w = PERFILES[perfil]
    mejor, best_h = float("inf"), None
    for h in ventana:
        p = _ruta_con_pesos(g, exp[h], w, o, d)
        m = _metricas(g, exp[h], p, w)
        score = m["E_ponderada"]  # misma agregación que Dijkstra minimiza
        if score < mejor:
            mejor, best_h = score, h
    return {"origen": origen, "destino": destino, "perfil": perfil, "dia": dia,
            "mejor_hora": best_h, "score": round(mejor, 3)}


def pareto(dia: str, hora: int) -> "list[dict]":
    """Para cada par de lugares y perfil: (Δdistancia %, reducción de la
    exposición ponderada %). Alimenta la figura §7. La reducción es la de la
    cantidad que Dijkstra minimiza (`FIL_43`) → nunca negativa."""
    lugares = list(LUGARES)
    filas = []
    for i in range(0, len(lugares), 2):
        if i + 1 >= len(lugares):
            break
        o, d = lugares[i], lugares[i + 1]
        for perfil in PERFILES:
            try:
                r = ruta(o, d, perfil, dia=dia, hora=hora)
            except nx.NetworkXNoPath:
                continue
            filas.append({
                "origen": o, "destino": d, "perfil": perfil,
                "delta_dist_pct": r["delta_dist_pct"],
                "reduccion_ponderada_pct": r["reduccion_exposicion_pct"],
            })
    return filas


def main() -> int:
    dias = sorted(pd.read_parquet(_PARQUET)["day"].unique().tolist())
    dia = dias[-1]  # miércoles cargado
    ejemplos = [("Atocha", "Moncloa"), ("Plaza Elíptica", "Cibeles"), ("Legazpi", "Bernabéu")]
    out = {"dia": dia, "generado": pd.Timestamp.utcnow().isoformat(timespec="seconds"), "rutas": []}
    for o, d in ejemplos:
        for perfil in ("general", "ciclista"):
            por_hora = []
            for h in range(24):
                r = ruta(o, d, perfil, dia=dia, hora=h)
                por_hora.append({
                    "hora": h,
                    "sana": r["ruta_sana"]["coords"],
                    "rapida": r["ruta_rapida"]["coords"],
                    "delta_dist_pct": r["delta_dist_pct"],
                    "reduccion_exposicion_pct": r["reduccion_exposicion_pct"],
                    "cambio_por_senal_pct": r["cambio_por_senal_pct"],
                })
            mh = mejor_hora(o, d, perfil, dia=dia)
            out["rutas"].append({"origen": o, "destino": d, "perfil": perfil,
                                 "mejor_hora": mh["mejor_hora"], "por_hora": por_hora})
    out["pareto"] = pareto(dia, hora=14)
    _OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{_OUT}  ({_OUT.stat().st_size/1024:.0f} KB, {len(out['rutas'])} rutas x 24 h, {len(out['pareto'])} puntos pareto)")
    r0 = out["rutas"][0]["por_hora"][8]
    print(f"  ej. {ejemplos[0]} general 08h: d_dist {r0['delta_dist_pct']}% | reduccion {r0['reduccion_exposicion_pct']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
