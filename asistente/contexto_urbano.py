"""`contexto_urbano(lugar)`: qué hay alrededor de un sitio de Madrid.

Es la única tool que hace una consulta **multi-salto** del grafo urbano
(las demás resuelven con un `MATCH` de 1 salto). Añadida en `FIL_53`.

Autocontenido: lee `asistente/modelos/grafo_urbano.json.gz` (reconstrucción
offline del grafo de Neo4j, `FIL_51`) y hace BFS ≤2 saltos en Python puro —
sin `networkx` ni Neo4j (mismo criterio que `asistente/athena.py`).

Para un `:Lugar` resuelto por texto devuelve:
- barrio y distrito por la **jerarquía real** (`UBICADO_EN`→`Barrio`
  `PERTENECE_A`→`Distrito`).
- estaciones de medida **a 1 salto** de `PROXIMO_A`, por tipo.
- paradas de transporte **alcanzables a ≤2 saltos de `CONECTADO_CON`**
  desde la parada más cercana.
- otros `:Lugar` **a ≤2 saltos de `PROXIMO_A`**, por tipo.
"""

from __future__ import annotations

import gzip
import json
import math
from collections import defaultdict, deque
from pathlib import Path

_ARTEFACTO = Path(__file__).resolve().parent / "modelos" / "grafo_urbano.json.gz"
_estado: "dict[str, object]" = {}


def disponible(*, artefacto: Path = _ARTEFACTO) -> bool:
    return artefacto.exists()


def _haversine_m(a_lat, a_lon, b_lat, b_lon) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(h))


def _cargar(artefacto: Path = _ARTEFACTO):
    clave = str(artefacto)
    if clave in _estado:
        return _estado[clave]
    with gzip.open(artefacto, "rt", encoding="utf-8") as fh:
        g = json.load(fh)

    tipo, nombre, pos, attrs = {}, {}, {}, {}
    # atributos estáticos que FIL_66 subió a los nodos y que esta tool
    # expone tal cual (cobertura de contaminantes, magnitudes meteo,
    # capacidades, subárea): se guardan en un dict aparte para no ensuciar
    # el resto del estado.
    _ATTR_KEYS = ("contaminantes", "magnitudes", "altitud_m", "anclajes_totales",
                  "plazas_totales", "subarea")
    for lab, ns in g["nodos"].items():
        for n in ns:
            nid = n.get("id")
            if not nid:
                continue
            tipo[nid] = n.get("tipo") or lab
            nombre[nid] = n.get("nombre")
            u = n.get("ubicacion")
            if u and u.get("lat") is not None:
                pos[nid] = (u["lat"], u["lon"])
            extra = {k: n[k] for k in _ATTR_KEYS if n.get(k) not in (None, [])}
            if extra:
                attrs[nid] = extra

    adj_prox: "dict[str, list]" = defaultdict(list)
    for r in g["relaciones"]["PROXIMO_A"]:
        a, b, d = r["origen_id"], r["destino_id"], r["distancia_m"]
        adj_prox[a].append((b, d))
        adj_prox[b].append((a, d))

    adj_conn: "dict[str, list]" = defaultdict(list)
    par_pos = {}
    lineas_de_parada: "dict[str, set]" = defaultdict(set)  # pid -> {(modo, linea)}
    for r in g["relaciones"]["CONECTADO_CON"]:
        o, dd = r["origen"], r["destino"]
        oid = o["id"] if isinstance(o, dict) else o
        did = dd["id"] if isinstance(dd, dict) else dd
        adj_conn[oid].append(did)
        adj_conn[did].append(oid)
        modo, linea = r.get("modo"), r.get("linea")
        if linea:
            lineas_de_parada[oid].add((modo, linea))
            lineas_de_parada[did].add((modo, linea))
        for e, eid in ((o, oid), (dd, did)):
            if isinstance(e, dict):
                nombre.setdefault(eid, e.get("nombre"))
                tipo.setdefault(eid, e.get("tipo") or "parada")
                u = (e.get("ubicacion") or {})
                if u.get("lat") is not None:
                    par_pos[eid] = (u["lat"], u["lon"])

    barrio_de = {r["nodo_id"]: r["barrio_codigo"] for r in g["relaciones"]["UBICADO_EN"]}
    barrio_nombre = {b["codigo"]: b["nombre"] for b in g["nodos"]["Barrio"]}
    barrio_distrito = {b["codigo"]: b["distrito_codigo"] for b in g["nodos"]["Barrio"]}
    distrito_nombre = {d["codigo"]: d["nombre"] for d in g["nodos"]["Distrito"]}
    lugares = [n for n in g["nodos"]["Lugar"] if n.get("nombre")]

    st = {
        "tipo": tipo, "nombre": nombre, "pos": pos, "par_pos": par_pos, "attrs": attrs,
        "adj_prox": adj_prox, "adj_conn": adj_conn, "lineas_de_parada": lineas_de_parada,
        "barrio_de": barrio_de, "barrio_nombre": barrio_nombre,
        "barrio_distrito": barrio_distrito, "distrito_nombre": distrito_nombre,
        "lugares": lugares,
        "_meta": g.get("_meta", {}),
    }
    _estado[clave] = st
    return st


def _resolver_lugar(st, texto: str) -> "str | None":
    t = texto.strip().lower()
    cands = [n for n in st["lugares"] if t in (n["nombre"] or "").lower()]
    if not cands:
        return None
    cands.sort(key=lambda n: len(n["nombre"]))  # el match más ajustado
    return cands[0]["id"]


def _bfs(adj, inicio: str, saltos: int) -> "dict[str, int]":
    dist = {inicio: 0}
    q = deque([inicio])
    while q:
        u = q.popleft()
        if dist[u] >= saltos:
            continue
        for v in adj.get(u, []):
            v = v[0] if isinstance(v, tuple) else v
            if v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    return dist


def _parada_mas_cercana(st, lat, lon) -> "str | None":
    best, bd = None, 800.0
    for pid, (pla, plo) in st["par_pos"].items():
        d = _haversine_m(lat, lon, pla, plo)
        if d < bd:
            best, bd = pid, d
    return best


def contexto(lugar: str, *, artefacto: Path = _ARTEFACTO) -> dict:
    st = _cargar(artefacto)
    lid = _resolver_lugar(st, lugar)
    if lid is None:
        muestra = sorted({n["nombre"] for n in st["lugares"]})[:12]
        raise ValueError(f"ningún :Lugar contiene «{lugar}». Ej.: {', '.join(muestra)}")

    nombre = st["nombre"].get(lid)
    bcod = st["barrio_de"].get(lid)
    barrio = st["barrio_nombre"].get(bcod)
    distrito = st["distrito_nombre"].get(st["barrio_distrito"].get(bcod))

    # estaciones de medida a 1 salto (incluye meteo desde FIL_65; cada
    # estación arrastra sus atributos estáticos de FIL_66: `contaminantes`
    # para aire, `magnitudes`/`altitud_m` para meteo, `subarea` para tráfico).
    est = defaultdict(list)
    for v, d in st["adj_prox"].get(lid, []):
        tp = st["tipo"].get(v, "")
        if tp in ("trafico", "calidad_aire", "ruido", "aforos_peatones_bicicletas", "meteo"):
            fila = {"id": v, "distancia_m": d, "nombre": st["nombre"].get(v)}
            fila.update(st["attrs"].get(v, {}))
            est[tp].append(fila)
    for tp in est:
        est[tp].sort(key=lambda x: x["distancia_m"])

    # otros :Lugar a <=2 saltos de PROXIMO_A (incluye recinto de eventos, FIL_65)
    d2 = _bfs(st["adj_prox"], lid, 2)
    lug_cerca = defaultdict(list)
    for v, saltos in d2.items():
        if v == lid:
            continue
        tp = st["tipo"].get(v, "")
        if tp in ("parque", "aparcamiento", "cine", "poi_turistico", "recinto"):
            fila = {"nombre": st["nombre"].get(v), "saltos": saltos}
            fila.update(st["attrs"].get(v, {}))  # p. ej. plazas_totales en aparcamiento
            lug_cerca[tp].append(fila)
    for tp in lug_cerca:
        lug_cerca[tp].sort(key=lambda x: x["saltos"])

    # transporte alcanzable a <=2 saltos de CONECTADO_CON desde la parada más cercana
    transporte = {"parada_ancla": None, "alcanzables_2_saltos": 0, "ejemplos": []}
    lineas_cercanas: "list[dict]" = []
    if lid in st["pos"]:
        ancla = _parada_mas_cercana(st, *st["pos"][lid])
        if ancla:
            dc = _bfs(st["adj_conn"], ancla, 2)
            nombres = sorted({st["nombre"].get(k) for k in dc if k != ancla and st["nombre"].get(k)})
            transporte = {
                "parada_ancla": st["nombre"].get(ancla) or ancla,
                "alcanzables_2_saltos": len(dc) - 1,
                "ejemplos": nombres[:8],
            }
            # líneas que pasan por la parada ancla y sus vecinas directas
            pares = set()
            for k in dc:
                pares |= st["lineas_de_parada"].get(k, set())
            lineas_cercanas = sorted(
                ({"modo": m, "linea": ln} for (m, ln) in pares),
                key=lambda x: (x["modo"] or "", x["linea"]),
            )[:20]

    return {
        "lugar": nombre,
        "lugar_id": lid,
        "tipo": st["tipo"].get(lid),
        "barrio": barrio,
        "distrito": distrito,
        "estaciones_1_salto": {k: v for k, v in est.items()},
        "lugares_cercanos_2_saltos": {k: v[:6] for k, v in lug_cerca.items()},
        "transporte": transporte,
        "lineas_cercanas": lineas_cercanas,
        "fuente_grafo": "grafo_urbano.json.gz (FIL_51 — reconstrucción del grafo de Neo4j)",
    }


def meta() -> dict:
    return dict(_cargar()["_meta"])
