"""FIL_52 — analítica del grafo urbano real de Madrid (`FIL_51`).

    python -m modelado.grafo_analitica.analisis

Produce, en `modelado/evaluation/artifacts/`:
- `grafo_centralidad_transporte.csv` — grado / intermediación / cercanía de
  las paradas en `CONECTADO_CON` (la red de transporte real).
- `grafo_comunidades.json` — comunidades Louvain sobre `PROXIMO_A` vs los
  131 barrios administrativos (ARI / NMI + ejemplos).
- `grafo_stats.json` — componentes, grado, cobertura de sensores por distrito.
- `grafo_stgnn_vs_conectividad.json` — ¿las aristas influyentes del STGNN
  caen sobre sensores de alta conectividad en el grafo?
- `grafo_analitica.png` — figura resumen.

Cero AWS, cero Neo4j. `networkx` sobre el artefacto reconstruido.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
import pandas as pd

from grafo.exportar_grafo import cargar

logger = logging.getLogger(__name__)
_ART = Path("modelado/evaluation/artifacts")
_META_STGNN = Path("asistente/modelos/stgnn_trafico.meta.json")


# ---------------------------------------------------------------------------

def construir_grafos(g: dict):
    """`(G_prox, G_conn)` — networkx no dirigidos.

    `G_prox`: `PROXIMO_A` (proximidad multi-dominio, peso = `distancia_m`).
    `G_conn`: `CONECTADO_CON` (adyacencia real de la red de transporte)."""
    tipo = {}
    for lab, ns in g["nodos"].items():
        for n in ns:
            nid = n.get("id") or n.get("codigo")
            tipo[nid] = n.get("tipo") or lab

    G_prox = nx.Graph()
    for r in g["relaciones"]["PROXIMO_A"]:
        G_prox.add_edge(r["origen_id"], r["destino_id"], distancia_m=r["distancia_m"])
    G_conn = nx.Graph()
    pos = {}
    for r in g["relaciones"]["CONECTADO_CON"]:
        for extremo, clave in ((r["origen"], "origen"), (r["destino"], "destino")):
            eid = extremo["id"] if isinstance(extremo, dict) else extremo
            if isinstance(extremo, dict):
                tipo.setdefault(eid, extremo.get("tipo") or "parada")
                u = extremo.get("ubicacion")
                if u and u.get("lat") is not None:
                    pos[eid] = (u["lat"], u["lon"])
        oid = r["origen"]["id"] if isinstance(r["origen"], dict) else r["origen"]
        did = r["destino"]["id"] if isinstance(r["destino"], dict) else r["destino"]
        G_conn.add_edge(oid, did, modo=r.get("modo"), linea=r.get("linea"))
    for G in (G_prox, G_conn):
        nx.set_node_attributes(G, {n: tipo.get(n, "?") for n in G}, "tipo")
    nx.set_node_attributes(G_conn, pos, "pos")
    return G_prox, G_conn


def nombres_transporte(g: dict, G_conn: nx.Graph) -> "dict[str, str]":
    """`id de nodo en CONECTADO_CON -> nombre legible`, casando por
    coordenadas con los nodos `:ParadaTransporte` (los ids de la relación y
    los de los nodos usan esquemas distintos)."""
    from grafo.geo import haversine_m

    ref = [(p["nombre"], p["ubicacion"]["lat"], p["ubicacion"]["lon"])
           for p in g["nodos"]["ParadaTransporte"]
           if p.get("nombre") and p.get("ubicacion") and p["ubicacion"].get("lat") is not None]
    out = {}
    for n, (la, lo) in nx.get_node_attributes(G_conn, "pos").items():
        best, bd = None, 60.0
        for nm, rla, rlo in ref:
            d = haversine_m(la, lo, rla, rlo)
            if d < bd:
                best, bd = nm, d
        out[n] = (best.title() if best else n.replace("crtm_red_transporte_madrid:", "#"))
    return out


# ---------------------------------------------------------------------------

def centralidad_transporte(G_conn: nx.Graph, nombres: "dict[str, str] | None" = None) -> pd.DataFrame:
    nombres = nombres or {}
    comp = max(nx.connected_components(G_conn), key=len)
    H = G_conn.subgraph(comp).copy()
    logger.info("CONECTADO_CON: %d nodos, %d aristas; componente mayor %d",
                G_conn.number_of_nodes(), G_conn.number_of_edges(), H.number_of_nodes())
    bet = nx.betweenness_centrality(H, normalized=True, seed=42)
    clo = nx.closeness_centrality(H)
    deg = dict(H.degree())
    filas = [
        {"parada": nombres.get(n, n), "modo": G_conn.nodes[n].get("tipo"), "grado": deg[n],
         "intermediacion": round(bet[n], 5), "cercania": round(clo[n], 4)}
        for n in H
    ]
    return pd.DataFrame(filas).sort_values("intermediacion", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------

def _barrio_por_nodo(g: dict) -> "dict[str, str]":
    return {r["nodo_id"]: r["barrio_codigo"] for r in g["relaciones"]["UBICADO_EN"]}


def comunidades_vs_barrios(g: dict, G_prox: nx.Graph) -> dict:
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    comp = max(nx.connected_components(G_prox), key=len)
    H = G_prox.subgraph(comp).copy()
    coms = nx.community.louvain_communities(H, weight=None, seed=42)
    com_de = {n: i for i, c in enumerate(coms) for n in c}
    b_de = _barrio_por_nodo(g)

    comunes = [n for n in H if n in b_de]
    y_com = [com_de[n] for n in comunes]
    y_bar = [b_de[n] for n in comunes]
    ari = adjusted_rand_score(y_bar, y_com)
    nmi = normalized_mutual_info_score(y_bar, y_com)

    # barrios que una misma comunidad del grafo "junta"
    barrios_por_com: "dict[int, Counter]" = defaultdict(Counter)
    for n in comunes:
        barrios_por_com[com_de[n]][b_de[n]] += 1
    juntados = sorted(
        ({"comunidad": ci, "barrios": [b for b, _ in bc.most_common(6)], "n_barrios": len(bc), "n_nodos": sum(bc.values())}
         for ci, bc in barrios_por_com.items() if len(bc) >= 4),
        key=lambda d: -d["n_barrios"],
    )[:8]
    # barrios que el grafo "parte" en >1 comunidad
    coms_por_barrio: "dict[str, Counter]" = defaultdict(Counter)
    for n in comunes:
        coms_por_barrio[b_de[n]][com_de[n]] += 1
    partidos = sorted(
        ({"barrio": b, "n_comunidades": len(cc), "n_nodos": sum(cc.values())}
         for b, cc in coms_por_barrio.items() if len(cc) >= 3),
        key=lambda d: -d["n_comunidades"],
    )[:8]

    return {
        "n_comunidades": len(coms),
        "n_barrios": len({b for b in b_de.values()}),
        "n_nodos_comparados": len(comunes),
        "ARI": round(ari, 3),
        "NMI": round(nmi, 3),
        "modularidad": round(nx.community.modularity(H, coms), 3),
        "comunidades_que_juntan_barrios": juntados,
        "barrios_partidos_por_el_grafo": partidos,
    }


# ---------------------------------------------------------------------------

def stgnn_vs_conectividad(g: dict, G_prox: nx.Graph) -> dict:
    from scipy.stats import spearmanr

    if not _META_STGNN.exists():
        return {"nota": "sin stgnn_trafico.meta.json"}
    imp = json.loads(_META_STGNN.read_text(encoding="utf-8")).get("importancia_aristas", [])
    grado = dict(G_prox.degree())
    tipo = nx.get_node_attributes(G_prox, "tipo")

    def gr(pid):  # grado del sensor de tráfico en PROXIMO_A (conectividad multi-dominio)
        return grado.get(f"trafico:{pid}", 0)

    filas = [{"a": e["a"], "b": e["b"], "importancia": e["importancia"],
              "grado_medio": (gr(e["a"]) + gr(e["b"])) / 2} for e in imp]
    if len(filas) >= 4:
        rho, p = spearmanr([f["importancia"] for f in filas], [f["grado_medio"] for f in filas])
    else:
        rho = p = float("nan")

    # qué hay alrededor del sensor de la arista más influyente
    top = max(imp, key=lambda e: e["importancia"]) if imp else None
    alrededor = {}
    if top:
        for pid in (top["a"], top["b"]):
            nid = f"trafico:{pid}"
            if nid in G_prox:
                alrededor[pid] = dict(Counter(tipo.get(v, "?") for v in G_prox.neighbors(nid)))
    return {
        "n_aristas_importancia": len(imp),
        "spearman_importancia_vs_grado_proximo_a": {"rho": round(float(rho), 3), "p": round(float(p), 4)},
        "sensores_grafo_trafico_en_proximo_a": sum(1 for n in G_prox if str(n).startswith("trafico:")),
        "arista_top": {"a": top["a"], "b": top["b"], "importancia": round(top["importancia"], 3)} if top else None,
        "alrededor_de_la_arista_top": alrededor,
    }


# ---------------------------------------------------------------------------

def estadisticos(g: dict, G_prox: nx.Graph, G_conn: nx.Graph) -> dict:
    b_de = _barrio_por_nodo(g)
    barrio_distrito = {b["codigo"]: b["distrito_codigo"] for b in g["nodos"]["Barrio"]}
    dist_nombre = {d["codigo"]: d["nombre"] for d in g["nodos"]["Distrito"]}

    sensores_por_distrito: Counter = Counter()
    for n in g["nodos"]["EstacionMedida"]:
        dc = barrio_distrito.get(b_de.get(n["id"]))
        if dc:
            sensores_por_distrito[dist_nombre.get(dc, dc)] += 1
    cobertura = dict(sorted(sensores_por_distrito.items(), key=lambda kv: kv[1]))

    grados = [d for _, d in G_prox.degree()]
    return {
        "PROXIMO_A": {
            "nodos": G_prox.number_of_nodes(), "aristas": G_prox.number_of_edges(),
            "componentes": nx.number_connected_components(G_prox),
            "grado_medio": round(sum(grados) / len(grados), 1),
            "grado_max": max(grados),
        },
        "CONECTADO_CON": {
            "nodos": G_conn.number_of_nodes(), "aristas": G_conn.number_of_edges(),
            "componentes": nx.number_connected_components(G_conn),
            "modos": dict(Counter(nx.get_edge_attributes(G_conn, "modo").values())),
        },
        "sensores_por_distrito": cobertura,
        "distritos_con_menos_sensores": list(cobertura.items())[:5],
    }


# ---------------------------------------------------------------------------

def _figura(cent: pd.DataFrame, com: dict, stats: dict, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2), constrained_layout=True)
    top = cent.head(12).iloc[::-1]
    ax[0].barh(range(len(top)), top["intermediacion"], color="#3d6ce0")
    ax[0].set_yticks(range(len(top)))
    ax[0].set_yticklabels([f"{p[:22]} ({m})" for p, m in zip(top["parada"], top["modo"])], fontsize=7)
    ax[0].set_title("Intermediación en CONECTADO_CON (top-12)")

    d = pd.Series(dict(sorted(stats["sensores_por_distrito"].items(), key=lambda kv: kv[1])))
    ax[1].barh(d.index, d.values, color="#4bbf73")
    ax[1].set_title("Sensores (EstacionMedida) por distrito")
    ax[1].tick_params(axis="y", labelsize=7)

    ax[2].axis("off")
    txt = (f"PROXIMO_A: {stats['PROXIMO_A']['nodos']} nodos / {stats['PROXIMO_A']['aristas']} aristas\n"
           f"  grado medio {stats['PROXIMO_A']['grado_medio']}, máx {stats['PROXIMO_A']['grado_max']}\n"
           f"  {stats['PROXIMO_A']['componentes']} componentes\n\n"
           f"CONECTADO_CON: {stats['CONECTADO_CON']['nodos']} paradas / {stats['CONECTADO_CON']['aristas']} aristas\n"
           f"  modos: {stats['CONECTADO_CON']['modos']}\n\n"
           f"Comunidades PROXIMO_A (Louvain): {com['n_comunidades']}\n"
           f"  vs {com['n_barrios']} barrios · ARI {com['ARI']} · NMI {com['NMI']}\n"
           f"  modularidad {com['modularidad']}")
    ax[2].text(0, 1, txt, va="top", family="monospace", fontsize=10)
    fig.suptitle("Madroño — analítica del grafo urbano real (FIL_52)", fontsize=13)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    g = cargar()
    G_prox, G_conn = construir_grafos(g)
    nombres = nombres_transporte(g, G_conn)

    cent = centralidad_transporte(G_conn, nombres)
    com = comunidades_vs_barrios(g, G_prox)
    svc = stgnn_vs_conectividad(g, G_prox)
    stats = estadisticos(g, G_prox, G_conn)

    _ART.mkdir(parents=True, exist_ok=True)
    cent.to_csv(_ART / "grafo_centralidad_transporte.csv", index=False)
    (_ART / "grafo_comunidades.json").write_text(json.dumps(com, indent=1, ensure_ascii=False), encoding="utf-8")
    (_ART / "grafo_stgnn_vs_conectividad.json").write_text(json.dumps(svc, indent=1, ensure_ascii=False), encoding="utf-8")
    (_ART / "grafo_stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    _figura(cent, com, stats, _ART / "grafo_analitica.png")

    print("\n== centralidad transporte (top-8) ==")
    print(cent.head(8).to_string(index=False))
    print("\n== comunidades vs barrios ==")
    print(f"  {com['n_comunidades']} comunidades vs {com['n_barrios']} barrios · "
          f"ARI {com['ARI']} · NMI {com['NMI']} · modularidad {com['modularidad']}")
    print("\n== STGNN vs conectividad ==")
    print(f"  Spearman(importancia, grado PROXIMO_A) = {svc.get('spearman_importancia_vs_grado_proximo_a')}")
    print("\nartefactos en", _ART)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
