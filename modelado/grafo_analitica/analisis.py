"""Analítica del grafo urbano real de Madrid para el capítulo de resultados.

Corre sobre el artefacto reconstruido por `FIL_51`; añadida en `FIL_52`.

    python -m modelado.grafo_analitica.analisis

Produce, en `modelado/evaluation/artifacts/`:
- `grafo_centralidad_transporte.csv` — grado / intermediación / cercanía de
  las paradas en `CONECTADO_CON` (la red de transporte real).
- `grafo_comunidades.json` — comunidades Louvain sobre `PROXIMO_A` vs los
  131 barrios administrativos (ARI / NMI + ejemplos).
- `grafo_stats.json` — componentes, grado, cobertura de sensores por distrito.
- `grafo_stgnn_vs_conectividad.json` — ¿las aristas influyentes del STGNN
  caen sobre sensores de alta conectividad en el grafo?
- `grafo_resiliencia.json` — (`FIL_64`) puntos de articulación, puentes por
  línea, descomposición k-core y curva de robustez frente a ataque dirigido
  vs. fallo aleatorio sobre `CONECTADO_CON`.
- `grafo_analitica.png` — figura resumen.
- `grafo_resiliencia.png` — (`FIL_64`) curva de robustez + articulación + k-core.

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
# FIL_64 — resiliencia estructural de la red de transporte (CONECTADO_CON).
# ---------------------------------------------------------------------------

def _componente_mayor(G: nx.Graph) -> nx.Graph:
    return G.subgraph(max(nx.connected_components(G), key=len)).copy()


def _frac_componente_mayor(G: nx.Graph, n_ref: int) -> float:
    """Tamaño de la componente conexa mayor de `G` como fracción de `n_ref`
    (el nº de nodos de la red intacta). 0.0 si `G` se queda sin nodos."""
    if G.number_of_nodes() == 0:
        return 0.0
    return len(max(nx.connected_components(G), key=len)) / n_ref


def puntos_de_articulacion(G_conn: nx.Graph, nombres: "dict[str, str] | None" = None,
                           top: int = 20) -> "list[dict]":
    """Paradas cuya eliminación desconecta la red: para cada punto de
    articulación de la componente mayor de `CONECTADO_CON`, cuántas
    componentes quedan al quitarlo y qué fracción de la red sobrevive en el
    fragmento mayor. Ordenado por daño (fragmento mayor más pequeño primero).
    """
    nombres = nombres or {}
    H = _componente_mayor(G_conn)
    n = H.number_of_nodes()
    filas = []
    for nodo in nx.articulation_points(H):
        sub = H.copy()
        sub.remove_node(nodo)
        comps = sorted((len(c) for c in nx.connected_components(sub)), reverse=True)
        filas.append({
            "parada": nombres.get(nodo, nodo),
            "modo": H.nodes[nodo].get("tipo"),
            "grado": H.degree(nodo),
            "componentes_tras_quitar": len(comps),
            "frac_red_en_fragmento_mayor": round(comps[0] / n, 4) if comps else 0.0,
            "nodos_desgajados": n - 1 - (comps[0] if comps else 0),
        })
    filas.sort(key=lambda d: d["frac_red_en_fragmento_mayor"])
    return filas[:top]


def puentes_por_linea(G_conn: nx.Graph) -> dict:
    """Puentes (aristas sin ruta alternativa) de la componente mayor,
    agregados por `(modo, linea)`: un tramo puente significa que ese par de
    paradas consecutivas no tiene redundancia — si se corta, la línea se
    parte. `frac_puentes` alto ⇒ línea "en cadena", sin mallado."""
    H = _componente_mayor(G_conn)
    puentes = list(nx.bridges(H))
    total_por_linea: Counter = Counter()
    puentes_por_linea: Counter = Counter()
    for u, v, data in H.edges(data=True):
        clave = (data.get("modo"), data.get("linea"))
        total_por_linea[clave] += 1
    for u, v in puentes:
        data = H.get_edge_data(u, v)
        puentes_por_linea[(data.get("modo"), data.get("linea"))] += 1
    filas = [
        {"modo": modo, "linea": linea, "tramos": total_por_linea[(modo, linea)],
         "tramos_puente": puentes_por_linea[(modo, linea)],
         "frac_puentes": round(puentes_por_linea[(modo, linea)] / total_por_linea[(modo, linea)], 3)}
        for (modo, linea) in total_por_linea
    ]
    filas.sort(key=lambda d: (-d["frac_puentes"], -d["tramos"]))
    return {
        "n_puentes": len(puentes),
        "n_aristas": H.number_of_edges(),
        "frac_aristas_puente": round(len(puentes) / H.number_of_edges(), 3),
        "lineas_sin_redundancia": [f for f in filas if f["frac_puentes"] == 1.0][:15],
        "por_linea_top": filas[:15],
    }


def kcore_resumen(G_conn: nx.Graph) -> dict:
    """Descomposición k-core de la componente mayor: el "núcleo" (k-core
    máximo) frente a la periferia colgante. `nx.core_number` requiere el
    grafo sin bucles."""
    H = _componente_mayor(G_conn)
    H.remove_edges_from(nx.selfloop_edges(H))
    core = nx.core_number(H)
    kmax = max(core.values())
    nucleo = [n for n, k in core.items() if k == kmax]
    return {
        "k_max": kmax,
        "n_en_nucleo": len(nucleo),
        "frac_en_nucleo": round(len(nucleo) / H.number_of_nodes(), 4),
        "distribucion_coreness": dict(sorted(Counter(core.values()).items())),
        "modos_en_nucleo": dict(Counter(H.nodes[n].get("tipo") for n in nucleo)),
    }


def curva_robustez(G_conn: nx.Graph, frac_max: float = 0.10, recalc_cada: int = 25,
                   reps_aleatorio: int = 5, seed: int = 42) -> dict:
    """Curva de fragmentación de `CONECTADO_CON` bajo dos regímenes de fallo:

    - **dirigido**: quita iterativamente la parada de mayor intermediación,
      recalculando betweenness cada `recalc_cada` bajas sobre el grafo que
      va quedando (recalcular en cada baja es O(V·E) por paso — inviable a
      esta escala; recalcular por lotes es la aproximación estándar).
    - **aleatorio**: quita nodos al azar; media de `reps_aleatorio` corridas.

    Devuelve, para cada régimen, la lista de `(frac_eliminada,
    frac_componente_mayor)`.
    """
    import random

    H0 = _componente_mayor(G_conn)
    n0 = H0.number_of_nodes()
    n_quitar = max(1, int(n0 * frac_max))

    # --- ataque dirigido ---
    H = H0.copy()
    dirig = [(0.0, 1.0)]
    ranking: list = []
    for i in range(n_quitar):
        if H.number_of_nodes() <= 1:
            break
        if not ranking or i % recalc_cada == 0:
            bet = nx.betweenness_centrality(H, normalized=True, seed=seed)
            ranking = [x for x, _ in sorted(bet.items(), key=lambda kv: -kv[1])]
        objetivo = next((x for x in ranking if x in H), None)
        if objetivo is None:
            break
        H.remove_node(objetivo)
        ranking.remove(objetivo)
        dirig.append(((i + 1) / n0, round(_frac_componente_mayor(H, n0), 4)))

    # --- fallo aleatorio (media de varias corridas) ---
    acumulado = [0.0] * (n_quitar + 1)
    rng = random.Random(seed)
    for _ in range(reps_aleatorio):
        H = H0.copy()
        orden = list(H0.nodes())
        rng.shuffle(orden)
        acumulado[0] += 1.0
        for i, nodo in enumerate(orden[:n_quitar], start=1):
            H.remove_node(nodo)
            acumulado[i] += _frac_componente_mayor(H, n0)
    aleat = [(i / n0, round(acumulado[i] / reps_aleatorio, 4)) for i in range(n_quitar + 1)]

    # resumen: cuánto cae el fragmento mayor al 5 % de bajas
    def _en(curva, frac):
        for f, v in curva:
            if f >= frac:
                return v
        return curva[-1][1]

    return {
        "n_nodos_componente_mayor": n0,
        "frac_eliminada_max": round(n_quitar / n0, 4),
        "dirigido": dirig,
        "aleatorio": aleat,
        "frag_mayor_al_5pct": {"dirigido": _en(dirig, 0.05), "aleatorio": _en(aleat, 0.05)},
    }


def resiliencia_transporte(G_conn: nx.Graph, nombres: "dict[str, str] | None" = None) -> dict:
    """Agrega los cuatro análisis de resiliencia de `FIL_64` en un dict."""
    art = puntos_de_articulacion(G_conn, nombres)
    return {
        "_nota": (
            "CONECTADO_CON modela UN viaje representativo por línea (el primero en "
            "direction_id='0', ver grafo/relaciones.py::conectado_con), no la red "
            "operada completa: sin ramales ni servicios paralelos, la red resultante "
            "es intrínsecamente poco mallada (k_max bajo, muchos puentes). Los "
            "hallazgos valen para el grafo tal como se ha modelado — sirven para "
            "razonar sobre estructura y sobre el propio modelo, no como diagnóstico "
            "operativo de la EMT/Metro reales."
        ),
        "n_puntos_articulacion": len(list(nx.articulation_points(_componente_mayor(G_conn)))),
        "puntos_articulacion_top": art,
        "puentes": puentes_por_linea(G_conn),
        "kcore": kcore_resumen(G_conn),
        "robustez": curva_robustez(G_conn),
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


def _figura_resiliencia(res: dict, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 3, figsize=(15, 4.2), constrained_layout=True)

    rob = res["robustez"]
    dx = [f * 100 for f, _ in rob["dirigido"]]
    dy = [v for _, v in rob["dirigido"]]
    ax_ = [f * 100 for f, _ in rob["aleatorio"]]
    ay = [v for _, v in rob["aleatorio"]]
    ax[0].plot(dx, dy, color="#d1495b", lw=2, label="ataque dirigido (betweenness)")
    ax[0].plot(ax_, ay, color="#3d6ce0", lw=2, ls="--", label="fallo aleatorio (media)")
    ax[0].set_xlabel("% de paradas eliminadas")
    ax[0].set_ylabel("fragmento mayor / red intacta")
    ax[0].set_title("Curva de robustez de CONECTADO_CON")
    ax[0].legend(fontsize=8)
    ax[0].grid(alpha=0.25)

    art = res["puntos_articulacion_top"][:12][::-1]
    ax[1].barh(range(len(art)), [a["nodos_desgajados"] for a in art], color="#edae49")
    ax[1].set_yticks(range(len(art)))
    ax[1].set_yticklabels([f"{a['parada'][:22]} ({a['modo']})" for a in art], fontsize=7)
    ax[1].set_title("Puntos de articulación — nodos desgajados")

    kc = res["kcore"]["distribucion_coreness"]
    ax[2].bar([str(k) for k in kc], list(kc.values()), color="#66a182")
    ax[2].set_xlabel("coreness (k)")
    ax[2].set_ylabel("nº de paradas")
    ax[2].set_title(f"Descomposición k-core (k_max={res['kcore']['k_max']})")

    fig.suptitle("Madroño — resiliencia de la red de transporte real (FIL_64)", fontsize=13)
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
    res = resiliencia_transporte(G_conn, nombres)

    _ART.mkdir(parents=True, exist_ok=True)
    cent.to_csv(_ART / "grafo_centralidad_transporte.csv", index=False)
    (_ART / "grafo_comunidades.json").write_text(json.dumps(com, indent=1, ensure_ascii=False), encoding="utf-8")
    (_ART / "grafo_stgnn_vs_conectividad.json").write_text(json.dumps(svc, indent=1, ensure_ascii=False), encoding="utf-8")
    (_ART / "grafo_stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
    (_ART / "grafo_resiliencia.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    _figura(cent, com, stats, _ART / "grafo_analitica.png")
    _figura_resiliencia(res, _ART / "grafo_resiliencia.png")

    print("\n== centralidad transporte (top-8) ==")
    print(cent.head(8).to_string(index=False))
    print("\n== comunidades vs barrios ==")
    print(f"  {com['n_comunidades']} comunidades vs {com['n_barrios']} barrios · "
          f"ARI {com['ARI']} · NMI {com['NMI']} · modularidad {com['modularidad']}")
    print("\n== STGNN vs conectividad ==")
    print(f"  Spearman(importancia, grado PROXIMO_A) = {svc.get('spearman_importancia_vs_grado_proximo_a')}")
    print("\n== resiliencia (FIL_64) ==")
    print(f"  {res['n_puntos_articulacion']} puntos de articulación · "
          f"{res['puentes']['n_puentes']} puentes ({res['puentes']['frac_aristas_puente']*100:.0f}% de las aristas) · "
          f"k_max={res['kcore']['k_max']} ({res['kcore']['n_en_nucleo']} paradas en el núcleo)")
    print(f"  fragmento mayor al 5% de bajas — dirigido {res['robustez']['frag_mayor_al_5pct']['dirigido']} "
          f"vs aleatorio {res['robustez']['frag_mayor_al_5pct']['aleatorio']}")
    print("\nartefactos en", _ART)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
