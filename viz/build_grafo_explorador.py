"""Construye `viz/grafo_explorador.html` — página autónoma para explorar el
grafo urbano **real** de Neo4j (FIL_67 Parte 3).

A diferencia del mapa animado (`viz/mapa/`, que usa el grafo `coords-knn8`
del STGNN), esta página pinta el grafo tal cual está cargado en la instancia
AuraDB: los 5 labels (incluidas las estaciones meteo y los recintos de
eventos de FIL_65), sus atributos estáticos de FIL_66 (contaminantes que
mide cada estación de aire, capacidades, subárea, altitud) y las dos
relaciones espaciales/topológicas (`PROXIMO_A`, `CONECTADO_CON`).

Se genera **offline** desde `grafo/_data/grafo_urbano.json.gz`
(reconstrucción del grafo de Neo4j, FIL_51/65/66/67) — sin credenciales, sin
red. No toca `viz/mapa/` ni la app web.

    python -m viz.build_grafo_explorador     # -> viz/grafo_explorador.html

Interacción: capas conmutables por tipo de nodo, `CONECTADO_CON` siempre
visible (esqueleto de transporte), y al hacer clic en un nodo se dibuja su
vecindario `PROXIMO_A` y un panel lateral con sus atributos, su barrio/
distrito real y las líneas que pasan por él.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
_GRAFO = _RAIZ / "grafo" / "_data" / "grafo_urbano.json.gz"
_OUT = Path(__file__).resolve().parent / "grafo_explorador.html"

# color por (label, tipo) — paleta deuteranopia-friendly, coherente con el mapa
_COLORES = {
    "trafico": "#e15759", "calidad_aire": "#4e79a7", "ruido": "#f28e2b",
    "meteo": "#76b7b2", "aforos_peatones_bicicletas": "#b07aa1",
    "bicimad": "#59a14f", "emt": "#9c755f", "metro": "#edc948",
    "metro_ligero": "#bab0ac", "cercanias": "#ff9da7",
    "poi_turistico": "#8cd17d", "parque": "#59a14f", "aparcamiento": "#a0cbe8",
    "cine": "#d37295", "recinto": "#b6992d",
}
_DEFECTO = "#888888"


def _compactar(g: dict) -> dict:
    """De `grafo_urbano.json.gz` a la forma mínima que necesita la página:
    nodos con posición + atributos, adyacencia `PROXIMO_A`, aristas
    `CONECTADO_CON`, y el barrio/distrito real por nodo."""
    barrio_nombre = {b["codigo"]: b["nombre"] for b in g["nodos"]["Barrio"]}
    barrio_distrito = {b["codigo"]: b["distrito_codigo"] for b in g["nodos"]["Barrio"]}
    distrito_nombre = {d["codigo"]: d["nombre"] for d in g["nodos"]["Distrito"]}
    barrio_de = {r["nodo_id"]: r["barrio_codigo"] for r in g["relaciones"]["UBICADO_EN"]}

    _ATTR = ("contaminantes", "magnitudes", "altitud_m", "subarea",
             "anclajes_totales", "plazas_totales")
    nodos = {}
    for lab, ns in g["nodos"].items():
        if lab in ("Distrito", "Barrio"):
            continue
        for n in ns:
            u = n.get("ubicacion") or {}
            if u.get("lat") is None:
                continue
            nid = n["id"]
            bcod = barrio_de.get(nid)
            attrs = {k: n[k] for k in _ATTR if n.get(k) not in (None, [])}
            nodos[nid] = {
                "id": nid, "label": lab, "tipo": n.get("tipo") or lab,
                "nombre": n.get("nombre"), "lat": round(u["lat"], 6), "lon": round(u["lon"], 6),
                "barrio": barrio_nombre.get(bcod),
                "distrito": distrito_nombre.get(barrio_distrito.get(bcod)),
                "attrs": attrs,
            }

    prox: "dict[str, list]" = {}
    for r in g["relaciones"]["PROXIMO_A"]:
        a, b, d = r["origen_id"], r["destino_id"], round(r["distancia_m"])
        if a in nodos and b in nodos:
            prox.setdefault(a, []).append([b, d])
            prox.setdefault(b, []).append([a, d])

    conn, lineas_de = [], {}
    vistos = set()
    for r in g["relaciones"]["CONECTADO_CON"]:
        o = r["origen"] if isinstance(r["origen"], dict) else {"id": r["origen"]}
        de = r["destino"] if isinstance(r["destino"], dict) else {"id": r["destino"]}
        oid, did = o["id"], de["id"]
        modo, linea = r.get("modo"), r.get("linea")
        for e in (o, de):
            u = e.get("ubicacion") or {}
            if e["id"] not in nodos and u.get("lat") is not None:
                nodos[e["id"]] = {
                    "id": e["id"], "label": "ParadaTransporte", "tipo": e.get("tipo") or "parada",
                    "nombre": e.get("nombre"), "lat": round(u["lat"], 6), "lon": round(u["lon"], 6),
                    "barrio": None, "distrito": None, "attrs": {},
                }
        if linea:
            lineas_de.setdefault(oid, set()).add((modo, linea))
            lineas_de.setdefault(did, set()).add((modo, linea))
        key = tuple(sorted((oid, did)))
        if key in vistos or oid not in nodos or did not in nodos:
            continue
        vistos.add(key)
        conn.append({"a": oid, "b": did, "modo": modo})

    lineas_de = {k: sorted(f"{m or '?'} {ln}" for (m, ln) in v) for k, v in lineas_de.items()}
    return {
        "nodos": nodos, "prox": prox, "conn": conn, "lineas_de": lineas_de,
        "meta": g.get("_meta", {}),
    }


_TEMPLATE = """<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grafo urbano de Madrid — explorador</title>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<style>
  :root{color-scheme:light dark}
  *{box-sizing:border-box}
  body{margin:0;font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
  #map{position:absolute;inset:0}
  #panel{position:absolute;top:12px;right:12px;width:320px;max-height:calc(100% - 24px);
    overflow:auto;background:#fffe;backdrop-filter:blur(4px);border-radius:10px;
    box-shadow:0 2px 16px #0003;padding:14px 16px}
  @media (prefers-color-scheme:dark){#panel{background:#1b1b1beedd;color:#eee}}
  #panel h1{font-size:15px;margin:0 0 4px}
  #panel .sub{color:#888;font-size:12px;margin-bottom:10px}
  #capas{position:absolute;top:12px;left:12px;background:#fffe;border-radius:10px;
    box-shadow:0 2px 16px #0003;padding:10px 12px;font-size:12px;max-width:200px}
  @media (prefers-color-scheme:dark){#capas{background:#1b1b1beedd;color:#eee}}
  #capas label{display:flex;align-items:center;gap:6px;padding:2px 0;cursor:pointer}
  #capas .sw{width:12px;height:12px;border-radius:50%;flex:0 0 auto}
  .kv{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;margin:6px 0}
  .kv b{color:#888;font-weight:500}
  .tag{display:inline-block;background:#8883;border-radius:6px;padding:1px 6px;margin:1px 2px 1px 0;font-size:12px}
  .muted{color:#999}
  .neigh{margin-top:8px;border-top:1px solid #8883;padding-top:8px}
  .neigh b{color:#888}
</style></head><body>
<div id="map"></div>
<div id="capas"></div>
<div id="panel">
  <h1>Grafo urbano de Madrid</h1>
  <div class="sub" id="meta"></div>
  <div id="detalle" class="muted">Haz clic en un nodo para ver sus atributos,
  su barrio/distrito y su vecindario <code>PROXIMO_A</code>.</div>
</div>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script>
const G = __DATA__;
const COLORES = __COLORES__, DEFECTO = "__DEFECTO__";
const N = G.nodos, PROX = G.prox, CONN = G.conn, LINEAS = G.lineas_de;
const tipos = [...new Set(Object.values(N).map(n=>n.tipo))].sort();
const activos = new Set(tipos);

const map = new maplibregl.Map({
  container:"map", style:"https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  center:[-3.703, 40.42], zoom:11, hash:true
});
map.addControl(new maplibregl.NavigationControl(), "bottom-right");

function nodosFC(){
  return {type:"FeatureCollection", features:Object.values(N)
    .filter(n=>activos.has(n.tipo))
    .map(n=>({type:"Feature", geometry:{type:"Point", coordinates:[n.lon,n.lat]},
      properties:{id:n.id, tipo:n.tipo, color:COLORES[n.tipo]||DEFECTO}}))};
}
function connFC(){
  return {type:"FeatureCollection", features:CONN.map(e=>{
    const a=N[e.a], b=N[e.b];
    return {type:"Feature", geometry:{type:"LineString",
      coordinates:[[a.lon,a.lat],[b.lon,b.lat]]}, properties:{modo:e.modo||"?"}};
  })};
}

map.on("load", ()=>{
  map.addSource("conn", {type:"geojson", data:connFC()});
  map.addLayer({id:"conn", type:"line", source:"conn",
    paint:{"line-color":"#7773","line-width":1.1}});
  map.addSource("prox-sel", {type:"geojson", data:{type:"FeatureCollection",features:[]}});
  map.addLayer({id:"prox-sel", type:"line", source:"prox-sel",
    paint:{"line-color":"#d1495b","line-width":1.6,"line-opacity":0.8}});
  map.addSource("nodos", {type:"geojson", data:nodosFC()});
  map.addLayer({id:"nodos", type:"circle", source:"nodos",
    paint:{"circle-radius":["interpolate",["linear"],["zoom"],10,2.2,15,5.5],
      "circle-color":["get","color"],"circle-stroke-width":0.6,"circle-stroke-color":"#fff8"}});
  map.addLayer({id:"nodo-sel", type:"circle", source:"nodos",
    filter:["==","id",""], paint:{"circle-radius":9,"circle-color":"#0000","circle-stroke-width":2.5,"circle-stroke-color":"#d1495b"}});

  map.on("click","nodos", e=>seleccionar(e.features[0].properties.id));
  map.on("mouseenter","nodos", ()=>map.getCanvas().style.cursor="pointer");
  map.on("mouseleave","nodos", ()=>map.getCanvas().style.cursor="");

  document.getElementById("meta").textContent =
    `${Object.keys(N).length.toLocaleString("es")} nodos · ${CONN.length.toLocaleString("es")} tramos CONECTADO_CON · fuente: Neo4j (FIL_51/65/66/67)`;
  construirCapas();
});

function construirCapas(){
  const box = document.getElementById("capas");
  box.innerHTML = "<b>Capas</b>";
  for(const t of tipos){
    const lab = document.createElement("label");
    lab.innerHTML = `<span class="sw" style="background:${COLORES[t]||DEFECTO}"></span>
      <input type="checkbox" checked data-t="${t}"> ${t}`;
    lab.querySelector("input").addEventListener("change", ev=>{
      ev.target.checked ? activos.add(t) : activos.delete(t);
      map.getSource("nodos").setData(nodosFC());
    });
    box.appendChild(lab);
  }
}

function esc(s){return (s==null?"":String(s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

function seleccionar(id){
  const n = N[id]; if(!n) return;
  map.setFilter("nodo-sel", ["==","id",id]);
  const vecinos = (PROX[id]||[]).slice().sort((a,b)=>a[1]-b[1]);
  map.getSource("prox-sel").setData({type:"FeatureCollection", features:vecinos.map(([vid])=>{
    const v = N[vid]; if(!v) return null;
    return {type:"Feature", geometry:{type:"LineString",
      coordinates:[[n.lon,n.lat],[v.lon,v.lat]]}, properties:{}};
  }).filter(Boolean)});

  const porTipo = {};
  for(const [vid,d] of vecinos){ const v=N[vid]; if(!v) continue;
    (porTipo[v.tipo] ||= []).push(`${esc(v.nombre||vid.split(":").pop())} · ${d} m`); }

  let h = `<h1>${esc(n.nombre || n.id.split(":").pop())}</h1>`;
  h += `<div class="sub">${esc(n.label)} · <span class="tag">${esc(n.tipo)}</span>`;
  if(n.barrio) h += ` ${esc(n.barrio)} / ${esc(n.distrito)}`;
  h += `</div>`;
  h += `<div class="kv"><b>id</b><span>${esc(n.id)}</span></div>`;
  const A = n.attrs || {};
  if(A.contaminantes) h += `<div class="kv"><b>mide</b><span>${A.contaminantes.map(c=>`<span class="tag">${esc(c)}</span>`).join("")}</span></div>`;
  if(A.magnitudes)    h += `<div class="kv"><b>magnitudes</b><span>${A.magnitudes.map(c=>`<span class="tag">${esc(c)}</span>`).join("")}</span></div>`;
  if(A.altitud_m!=null)        h += `<div class="kv"><b>altitud</b><span>${A.altitud_m} m</span></div>`;
  if(A.subarea!=null)          h += `<div class="kv"><b>subárea</b><span>${esc(A.subarea)}</span></div>`;
  if(A.plazas_totales!=null)   h += `<div class="kv"><b>plazas</b><span>${A.plazas_totales}</span></div>`;
  if(A.anclajes_totales!=null) h += `<div class="kv"><b>anclajes</b><span>${A.anclajes_totales}</span></div>`;
  const ls = LINEAS[id];
  if(ls && ls.length) h += `<div class="kv"><b>líneas</b><span>${ls.map(x=>`<span class="tag">${esc(x)}</span>`).join("")}</span></div>`;

  h += `<div class="neigh"><b>Vecindario PROXIMO_A</b> (${vecinos.length})`;
  for(const t of Object.keys(porTipo).sort()){
    h += `<div class="kv"><b>${esc(t)}</b><span>${porTipo[t].slice(0,6).map(esc).join("<br>")}${porTipo[t].length>6?`<br>… +${porTipo[t].length-6}`:""}</span></div>`;
  }
  h += `</div>`;
  document.getElementById("detalle").innerHTML = h;
  document.getElementById("detalle").classList.remove("muted");
}
</script></body></html>
"""


def construir() -> str:
    with gzip.open(_GRAFO, "rt", encoding="utf-8") as fh:
        g = json.load(fh)
    datos = _compactar(g)
    return (
        _TEMPLATE
        .replace("__DATA__", json.dumps(datos, ensure_ascii=False, separators=(",", ":")))
        .replace("__COLORES__", json.dumps(_COLORES, ensure_ascii=False))
        .replace("__DEFECTO__", _DEFECTO)
    )


def main() -> int:
    html = construir()
    _OUT.write_text(html, encoding="utf-8")
    kb = _OUT.stat().st_size / 1024
    print(f"{_OUT}  ({kb:,.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
