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

import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from asistente.neo4j_client import (
    grafo_explorador_conectado_con_query,
    grafo_explorador_nodos_query,
    run_neo4j_query,
    vecindario_grafo_query,
)

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
    filas_n = run_neo4j_query(q_n, p_n)
    filas_c = run_neo4j_query(q_c, p_c)

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


@router.get("/grafo/explorador/vecindario")
def vecindario(
    id: str = Query(description="id completo del nodo (p. ej. 'calidad_aire:28079008')."),
    radio_m: float = Query(default=300.0, description="Radio PROXIMO_A en metros (útil máx. ~300)."),
) -> dict:
    """Vecinos `PROXIMO_A` de un nodo, en vivo."""
    q, p = vecindario_grafo_query(id, radio_m)
    try:
        filas = run_neo4j_query(q, p)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Neo4j no disponible: {type(exc).__name__}: {exc}")
    vecinos = [
        {**_fila_a_nodo(f), "distancia_m": round(f["distancia_m"])}
        for f in filas
        if f.get("lat") is not None
    ]
    return {"id": id, "radio_m": radio_m, "n": len(vecinos), "vecinos": vecinos}
