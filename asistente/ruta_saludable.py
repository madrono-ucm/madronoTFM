"""FIL_37 — `ruta_saludable`: enrutado multi-objetivo sobre el grafo de
Madrid (`coords-knn8`, 1.798 nodos), con coste de arista = distancia +
exposición **prevista** (tráfico h1, NO₂, O₃, ruido), ponderada por perfil.

Autocontenido: lee `asistente/modelos/grafo_ruta.json` (vendorizado por
`viz/build_grafo_ruta.py`) y hace Dijkstra en Python puro — sin `networkx`
ni dependencia de `viz/` (mismo criterio que `asistente/athena.py`).

Sirve los **3 días curados** de agosto 2026 como demostración de
metodología (§7.4), igual que los STGNN de grafo. `perfil ∈ {general,
ciclista, sensible_aire, sensible_ruido}`.
"""

from __future__ import annotations

import heapq
import json
import math
from pathlib import Path

_ARTEFACTO = Path(__file__).resolve().parent / "modelos" / "grafo_ruta.json"
_estado: "dict[str, object]" = {}
_SENALES = ("traf", "no2", "o3", "noise")
_HORAS = tuple(range(24))


def disponible(*, artefacto: Path = _ARTEFACTO) -> bool:
    return artefacto.exists()


def _cargar(artefacto: Path):
    clave = str(artefacto)
    if clave not in _estado:
        g = json.loads(artefacto.read_text(encoding="utf-8"))
        g["_idx"] = {n["id"]: i for i, n in enumerate(g["nodos"])}
        g["_distrito"] = {n["id"]: n["distrito"] for n in g["nodos"]}
        _estado[clave] = g
    return _estado[clave]


def _haversine_m(a_lat, a_lon, b_lat, b_lon) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(h))


def _nodo_cercano(g, lat: float, lon: float) -> str:
    return min(g["nodos"], key=lambda n: _haversine_m(lat, lon, n["lat"], n["lon"]))["id"]


def _norm(g, sig: str, v: float) -> float:
    if v is None or v < 0:
        return 0.0
    if sig == "noise":
        lo, hi = g["norm"]["noise"]
        return max(0.0, min(1.0, (v - lo) / (hi - lo)))
    return max(0.0, min(1.0, v / g["norm"][sig]))


def _expo_nodo(g, dia: str, hora: int, node_id: str) -> "dict[str, float]":
    i = g["_idx"][node_id]
    traf100, no2, o3 = g["exposicion"][dia][str(hora)][i]
    db = g["ruido_distrito"].get(g["_distrito"][node_id])
    return {
        "traf": None if traf100 < 0 else traf100 / 100.0,
        "no2": None if no2 < 0 else float(no2),
        "o3": None if o3 < 0 else float(o3),
        "noise": db,
    }


def _dijkstra(g, dia: str, hora: int, pesos: dict, origen: str, destino: str) -> "list[str]":
    # cache de exposición por nodo para esta consulta
    ex_cache: "dict[str, dict]" = {}

    def ex(nid):
        if nid not in ex_cache:
            ex_cache[nid] = _expo_nodo(g, dia, hora, nid)
        return ex_cache[nid]

    def coste(u, v, length_m):
        eu, ev = ex(u), ex(v)
        expo = 0.0
        for s in _SENALES:
            m = 0.5 * (_norm(g, s, eu[s]) + _norm(g, s, ev[s]))
            expo += pesos[s] * m
        return pesos["dist"] * (length_m / 1000.0) + expo

    dist = {origen: 0.0}
    prev: "dict[str, str]" = {}
    pq = [(0.0, origen)]
    visto = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in visto:
            continue
        visto.add(u)
        if u == destino:
            break
        for v, length_m in g["adyacencia"].get(u, []):
            nd = d + coste(u, v, length_m)
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if destino not in prev and destino != origen:
        raise ValueError("no hay camino entre los dos puntos en el grafo")
    camino = [destino]
    while camino[-1] != origen:
        camino.append(prev[camino[-1]])
    return camino[::-1]


def _metricas(g, dia: str, hora: int, camino: "list[str]") -> dict:
    dist_m = 0.0
    for i in range(len(camino) - 1):
        a = camino[i]
        for v, length_m in g["adyacencia"][a]:
            if v == camino[i + 1]:
                dist_m += length_m
                break
    acc = {s: 0.0 for s in _SENALES}
    n = 0
    for nid in camino:
        e = _expo_nodo(g, dia, hora, nid)
        for s in _SENALES:
            if e[s] is not None:
                acc[s] += e[s]
        n += 1
    return {"n_nodos": len(camino), "dist_m": round(dist_m, 1),
            **{f"{s}_medio": round(acc[s] / max(n, 1), 2) for s in _SENALES}}


def ruta(origen: str, destino: str, perfil: str = "general", *, dia: str, hora: int) -> dict:
    """Ruta saludable vs ruta rápida entre dos lugares de referencia."""
    g = _cargar(_ARTEFACTO)
    if perfil not in g["perfiles"]:
        raise ValueError(f"perfil {perfil!r} no válido; usa {list(g['perfiles'])}")
    if origen not in g["lugares"] or destino not in g["lugares"]:
        raise ValueError(
            f"lugar no reconocido; opciones: {', '.join(sorted(g['lugares']))}"
        )
    if dia not in g["exposicion"] or not (0 <= hora <= 23):
        raise ValueError(f"día/hora fuera de rango; días: {g['dias']}, hora 0..23")

    o = _nodo_cercano(g, *g["lugares"][origen])
    d = _nodo_cercano(g, *g["lugares"][destino])
    w = g["perfiles"][perfil]
    w_rapida = {"dist": 1.0, "traf": 0.0, "no2": 0.0, "o3": 0.0, "noise": 0.0}

    p_sana = _dijkstra(g, dia, hora, w, o, d)
    p_rapida = _dijkstra(g, dia, hora, w_rapida, o, d)
    m_sana, m_rapida = _metricas(g, dia, hora, p_sana), _metricas(g, dia, hora, p_rapida)

    delta = (m_sana["dist_m"] - m_rapida["dist_m"]) / max(m_rapida["dist_m"], 1.0) * 100
    red = {
        s: round((m_rapida[f"{s}_medio"] - m_sana[f"{s}_medio"]) / max(m_rapida[f"{s}_medio"], 1e-6) * 100, 1)
        for s in _SENALES
    }
    return {
        "origen": origen, "destino": destino, "perfil": perfil, "dia": dia, "hora": hora,
        "nodo_origen": o, "nodo_destino": d,
        "ruta_sana": {"nodos": p_sana, **m_sana},
        "ruta_rapida": {"nodos": p_rapida, **m_rapida},
        "delta_distancia_pct": round(delta, 1),
        "reduccion_exposicion_pct": red,
    }


def mejor_hora(origen: str, destino: str, perfil: str, *, dia: str) -> dict:
    """Hora del día que minimiza la exposición combinada de la ruta sana."""
    g = _cargar(_ARTEFACTO)
    mejor, best_h = math.inf, None
    for h in _HORAS:
        r = ruta(origen, destino, perfil, dia=dia, hora=h)
        m = r["ruta_sana"]
        score = sum(_norm(g, s, m[f"{s}_medio"]) for s in _SENALES)
        if score < mejor:
            mejor, best_h = score, h
    return {"origen": origen, "destino": destino, "perfil": perfil, "dia": dia,
            "mejor_hora": best_h, "score": round(mejor, 3)}


def dias() -> "list[str]":
    return list(_cargar(_ARTEFACTO)["dias"])


def lugares() -> "list[str]":
    return sorted(_cargar(_ARTEFACTO)["lugares"])
