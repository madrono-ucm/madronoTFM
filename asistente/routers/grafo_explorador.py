"""Explorador del grafo urbano **en vivo** (FIL_67 Parte 3).

Sirve `viz/grafo_explorador.html` en su variante *live*: en vez de traer el
grafo embebido de un snapshot estático (`grafo_urbano.json.gz`), la página
lo pide a estos endpoints, que leen Neo4j en directo (solo lectura).

- `GET /grafo/explorador`            -> el HTML.
- `GET /grafo/explorador/data`       -> nodos + aristas CONECTADO_CON + líneas.
- `GET /grafo/explorador/vecindario` -> vecinos PROXIMO_A de un nodo (`?id=`).

`/data` se cachea en memoria (`_TTL_S`) porque el grafo cambia rara vez y el
payload es de varios MB. Cualquier fallo de Neo4j se traduce en 503 con un
cuerpo legible, nunca en una traza.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from asistente.neo4j_client import (
    cobertura_aire_query,
    grafo_explorador_conectado_con_query,
    grafo_explorador_nodos_query,
    ruta_proximo_query,
    ruta_transporte_query,
    run_neo4j_query,
    sensores_por_distrito_query,
    vecindario_grafo_query,
)

_RAIZ = Path(__file__).resolve().parents[2]
_STGNN_META = _RAIZ / "asistente" / "modelos" / "stgnn_trafico.meta.json"
_RESILIENCIA = _RAIZ / "modelado" / "evaluation" / "artifacts" / "grafo_resiliencia.json"
_CENTRALIDAD = _RAIZ / "modelado" / "evaluation" / "artifacts" / "grafo_centralidad.json"


def _leer(query: str, params: dict, *, intentos: int = 3) -> list:
    """`run_neo4j_query` con reintento ante caídas transitorias de conexión a
    AuraDB (`ConnectionResetError`, `defunct connection`... — vistas de forma
    intermitente desde esta máquina). Backoff corto; a la última, propaga."""
    for i in range(intentos):
        try:
            return run_neo4j_query(query, params)
        except Exception:  # noqa: BLE001
            if i == intentos - 1:
                raise
            time.sleep(0.4 * (2 ** i))
    return []


router = APIRouter(tags=["grafo-explorador"])

_HTML = Path(__file__).resolve().parents[2] / "viz" / "grafo_explorador_live.html"
_TTL_S = 600.0
_cache: "dict[str, object]" = {"t": 0.0, "data": None}

_ATTR_KEYS = ("contaminantes", "magnitudes", "altitud_m", "subarea",
              "anclajes_totales", "plazas_totales")


def _fila_a_nodo(fila: dict) -> dict:
    n = {
        "id": fila["id"], "label": fila["label"], "tipo": fila.get("tipo") or fila["label"],
        "nombre": fila.get("nombre"),
        "lat": round(fila["lat"], 6), "lon": round(fila["lon"], 6),
        "barrio": fila.get("barrio"), "distrito": fila.get("distrito"),
        "attrs": {k: fila[k] for k in _ATTR_KEYS if fila.get(k) not in (None, [])},
    }
    return n


def _construir_data() -> dict:
    q_n, p_n = grafo_explorador_nodos_query()
    q_c, p_c = grafo_explorador_conectado_con_query()
    filas_n = _leer(q_n, p_n)
    filas_c = _leer(q_c, p_c)

    nodos = {}
    for fila in filas_n:
        if fila.get("lat") is None:
            continue
        nodos[fila["id"]] = _fila_a_nodo(fila)

    conn, lineas_de, vistos = [], {}, set()
    for r in filas_c:
        a, b, modo, linea = r["a"], r["b"], r.get("modo"), r.get("linea")
        if linea:
            lineas_de.setdefault(a, set()).add((modo, linea))
            lineas_de.setdefault(b, set()).add((modo, linea))
        key = tuple(sorted((a, b)))
        if key in vistos or a not in nodos or b not in nodos:
            continue
        vistos.add(key)
        conn.append({"a": a, "b": b, "modo": modo})
    lineas_de = {k: sorted(f"{m or '?'} {ln}" for (m, ln) in v) for k, v in lineas_de.items()}

    return {
        "nodos": nodos, "conn": conn, "lineas_de": lineas_de,
        "meta": {"fuente": "Neo4j en vivo (FIL_67)", "n_nodos": len(nodos), "n_conn": len(conn),
                 "generado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
    }


@router.get("/grafo/explorador")
def ui() -> FileResponse:
    """El HTML del explorador (variante *live*)."""
    if not _HTML.exists():
        raise HTTPException(500, "falta viz/grafo_explorador_live.html (python -m viz.build_grafo_explorador --live)")
    return FileResponse(_HTML, media_type="text/html")


@router.get("/grafo/explorador/data")
def data() -> dict:
    """Nodos + aristas CONECTADO_CON + líneas, leído de Neo4j (cacheado)."""
    ahora = time.time()
    if _cache["data"] is None or ahora - float(_cache["t"]) > _TTL_S:
        try:
            _cache["data"] = _construir_data()
            _cache["t"] = ahora
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, f"Neo4j no disponible: {type(exc).__name__}: {exc}")
    return _cache["data"]


_analisis_cache: "dict[str, object]" = {"t": 0.0, "data": None}


def _stgnn_aristas_influyentes(top: int = 15) -> list:
    """Las aristas más influyentes del STGNN de tráfico (`ML_05`), con las
    coordenadas de sus extremos y la importancia normalizada a [0,1]."""
    if not _STGNN_META.exists():
        return []
    m = json.loads(_STGNN_META.read_text(encoding="utf-8"))
    nc = m.get("node_coords", {})
    imp = sorted(m.get("importancia_aristas", []), key=lambda e: -e["importancia"])[:top]
    mx = max((e["importancia"] for e in imp), default=1.0) or 1.0
    out = []
    for e in imp:
        ca, cb = nc.get(e["a"]), nc.get(e["b"])
        if not ca or not cb:
            continue
        out.append({"a": [round(ca[1], 5), round(ca[0], 5)], "b": [round(cb[1], 5), round(cb[0], 5)],
                    "w": round(e["importancia"] / mx, 3),
                    "ids": [f"trafico:{e['a']}", f"trafico:{e['b']}"]})
    return out


def _resiliencia() -> dict:
    if not _RESILIENCIA.exists():
        return {}
    r = json.loads(_RESILIENCIA.read_text(encoding="utf-8"))
    return {
        "nota": r.get("_nota"),
        "n_puntos_articulacion": r.get("n_puntos_articulacion"),
        "puntos_articulacion": [
            {"parada": p["parada"], "modo": p.get("modo"), "grado": p.get("grado"),
             "nodos_desgajados": p.get("nodos_desgajados")}
            for p in r.get("puntos_articulacion_top", [])
        ],
        "puentes": {k: r.get("puentes", {}).get(k) for k in ("n_puentes", "n_aristas", "frac_aristas_puente")},
        "kcore": {k: r.get("kcore", {}).get(k) for k in ("k_max", "n_en_nucleo", "frac_en_nucleo")},
        "robustez_5pct": r.get("robustez", {}).get("frag_mayor_al_5pct"),
    }


def _centralidad() -> dict:
    """PageRank + comunidades Louvain de `CONECTADO_CON` (`FIL_81`), del
    artefacto offline `grafo_centralidad.json` (sin GDS, sin Neo4j en
    caliente)."""
    if not _CENTRALIDAD.exists():
        return {}
    c = json.loads(_CENTRALIDAD.read_text(encoding="utf-8"))
    return {
        "nota": c.get("_nota"),
        "n_nodos": c.get("n_nodos"),
        "top_pagerank": c.get("top_pagerank", [])[:10],
        "top_intermediacion": c.get("top_intermediacion", [])[:10],
        "comunidades": c.get("comunidades", {}),
    }


@router.get("/grafo/explorador/analisis")
def analisis() -> dict:
    """Análisis del TFM proyectados sobre el grafo: cobertura de aire,
    sesgo de sensores por distrito, resiliencia del transporte (`FIL_64`) y
    las aristas más influyentes del STGNN (`ML_05`). Cacheado 10 min."""
    ahora = time.time()
    if _analisis_cache["data"] is None or ahora - float(_analisis_cache["t"]) > _TTL_S:
        try:
            qa, pa = cobertura_aire_query()
            qd, pd = sensores_por_distrito_query()
            filas_a = _leer(qa, pa)
            filas_d = _leer(qd, pd)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, f"Neo4j no disponible: {type(exc).__name__}: {exc}")
        con = sum(1 for f in filas_a if f["con_aire"])
        _analisis_cache["data"] = {
            "cobertura_aire": {
                "trafico_total": len(filas_a),
                "con_aire_cerca": con,
                "sin_aire_cerca": len(filas_a) - con,
                "ids_con_aire": [f["id"] for f in filas_a if f["con_aire"]],
            },
            "sensores_por_distrito": [
                {"distrito": f["distrito"], "n": f["n"], "trafico": f["trafico"], "aire": f["aire"]}
                for f in filas_d
            ],
            "stgnn_aristas_influyentes": _stgnn_aristas_influyentes(),
            "resiliencia": _resiliencia(),
            "centralidad": _centralidad(),
            "generado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _analisis_cache["t"] = ahora
    return _analisis_cache["data"]


@router.get("/grafo/explorador/ruta")
def ruta(
    a: str = Query(description="id del nodo origen."),
    b: str = Query(description="id del nodo destino."),
    modo: str = Query(default="proximo", description="'proximo' (PROXIMO_A ponderado, apoc.algo.dijkstra) o 'transporte' (CONECTADO_CON, shortestPath)."),
) -> dict:
    """Camino entre dos nodos del grafo — la capacidad de enrutado servida
    directa desde Neo4j. `404` si no hay ruta; `503` si Neo4j no responde."""
    if modo == "transporte":
        q, p = ruta_transporte_query(a, b)
    else:
        modo = "proximo"
        q, p = ruta_proximo_query(a, b)
    try:
        filas = _leer(q, p)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Neo4j no disponible: {type(exc).__name__}: {exc}")
    if not filas or not filas[0].get("nodos"):
        raise HTTPException(404, f"sin ruta {modo} entre «{a}» y «{b}»")
    f = filas[0]
    nodos = [
        {**{k: n.get(k) for k in ("id", "tipo", "nombre")},
         "lat": round(n["lat"], 6) if n.get("lat") is not None else None,
         "lon": round(n["lon"], 6) if n.get("lon") is not None else None}
        for n in f["nodos"]
    ]
    out = {"modo": modo, "a": a, "b": b, "saltos": f["saltos"], "nodos": nodos}
    if modo == "proximo":
        out["metros"] = round(f["metros"])
    else:
        tramos = f.get("tramos") or []
        out["tramos"] = tramos
        out["lineas"] = sorted({f"{t.get('modo') or '?'} {t.get('linea')}" for t in tramos if t.get("linea")})
    return out


@router.get("/grafo/explorador/vecindario")
def vecindario(
    id: str = Query(description="id completo del nodo (p. ej. 'calidad_aire:28079008')."),
    radio_m: float = Query(default=300.0, description="Radio PROXIMO_A en metros (útil máx. ~300)."),
) -> dict:
    """Vecinos `PROXIMO_A` de un nodo, en vivo."""
    q, p = vecindario_grafo_query(id, radio_m)
    try:
        filas = _leer(q, p)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Neo4j no disponible: {type(exc).__name__}: {exc}")
    vecinos = [
        {**_fila_a_nodo(f), "distancia_m": round(f["distancia_m"])}
        for f in filas
        if f.get("lat") is not None
    ]
    return {"id": id, "radio_m": radio_m, "n": len(vecinos), "vecinos": vecinos}
