"""Construye el explorador del grafo urbano **real** de Neo4j (FIL_67 Parte 3).

Dos variantes de la misma página:

    python -m viz.build_grafo_explorador          # -> viz/grafo_explorador.html
                                                  #    (autónoma: grafo embebido de grafo_urbano.json.gz)
    python -m viz.build_grafo_explorador --live   # -> viz/grafo_explorador_live.html
                                                  #    (pide el grafo a /grafo/explorador/{data,vecindario}
                                                  #    del asistente, que lee Neo4j en vivo)

A diferencia del mapa animado (`viz/mapa/`, grafo `coords-knn8` del STGNN),
pinta el grafo tal cual está en Neo4j: 5 labels — meteo y recintos de
`FIL_65` incluidos —, atributos por entidad de `FIL_66` (contaminantes que
mide cada estación de aire, capacidades, subárea, altitud) y las relaciones
`PROXIMO_A` / `CONECTADO_CON`. Clic en un nodo → panel con sus atributos, su
barrio/distrito reales y su vecindario `PROXIMO_A`.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
_GRAFO = _RAIZ / "grafo" / "_data" / "grafo_urbano.json.gz"
_DIR = Path(__file__).resolve().parent

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
    """De `grafo_urbano.json.gz` a la forma mínima que necesita la página."""
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

    conn, lineas_de, vistos = [], {}, set()
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
    return {"nodos": nodos, "prox": prox, "conn": conn, "lineas_de": lineas_de,
            "meta": g.get("_meta", {})}


_TEMPLATE = """<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grafo urbano de Madrid — explorador</title>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<style>
  *{box-sizing:border-box}
  body{margin:0;font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#e9e9ec}
  #map{position:absolute;inset:0;background:#0d1117}
  #izq{position:absolute;top:12px;left:12px;bottom:12px;width:280px;display:flex;
    flex-direction:column;gap:10px;pointer-events:none;overflow:hidden}
  #izq > .box{pointer-events:auto}
  .box,#panel{background:rgba(22,24,29,.94);color:#e9e9ec;
    border:1px solid rgba(255,255,255,.09);border-radius:10px;
    box-shadow:0 4px 20px #0007;backdrop-filter:blur(3px)}
  #panel{position:absolute;top:12px;right:12px;width:330px;max-height:calc(100% - 24px);overflow:auto;padding:14px 16px}
  .box{padding:10px 12px;font-size:12px}
  #panel h1{font-size:15px;margin:0 0 4px}
  #panel .sub{color:#9aa0a6;font-size:12px;margin-bottom:10px}
  #capas{overflow:auto;max-height:170px}
  #analisis{overflow:auto;flex:1 1 auto;min-height:0}
  #menu select, #menu button, #panel button{width:100%;margin:6px 0 4px;padding:5px 8px;border-radius:7px;
    background:#2a2d36;color:#e9e9ec;border:1px solid rgba(255,255,255,.14);font:inherit;cursor:pointer}
  #menu button.on{background:#3d6ce0;border-color:#3d6ce0}
  #menu .desc{color:#9aa0a6;font-size:11px}
  #capas label{display:flex;align-items:center;gap:6px;padding:2px 0;cursor:pointer}
  #capas .sw{width:12px;height:12px;border-radius:50%;flex:0 0 auto}
  #analisis h2{font-size:13px;margin:0 0 4px}
  #analisis .big{font-size:22px;font-weight:600;line-height:1.1}
  #analisis table{border-collapse:collapse;width:100%;font-size:11px;margin-top:4px}
  #analisis td{padding:1px 5px 1px 0;border-bottom:1px solid rgba(255,255,255,.08)}
  #analisis td:not(:first-child){text-align:right;font-variant-numeric:tabular-nums}
  #analisis .nota{color:#8b8f96;font-size:10.5px;margin-top:6px;font-style:italic}
  .kv{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;margin:6px 0}
  .kv b{color:#9aa0a6;font-weight:500}
  .tag{display:inline-block;background:rgba(255,255,255,.13);border-radius:6px;padding:1px 6px;margin:1px 2px 1px 0;font-size:12px}
  .muted{color:#8b8f96}
  .neigh{margin-top:8px;border-top:1px solid rgba(255,255,255,.1);padding-top:8px}
  .neigh b{color:#9aa0a6}
  #err{position:absolute;left:50%;top:8px;transform:translateX(-50%);z-index:9;max-width:70%;
    background:#5b1a1a;color:#ffdede;border:1px solid #a33;border-radius:8px;padding:6px 12px;font-size:12px;display:none}
</style></head><body>
<div id="map"></div>
<div id="err"></div>
<div id="izq">
<div id="menu" class="box">
  <b>Vista / análisis</b>
  <select id="vista">
    <option value="explorar">Explorar (color por tipo)</option>
    <option value="aire_cobertura">Aire · cobertura de las estaciones de tráfico</option>
    <option value="aire_o3">Aire · qué estaciones miden O₃ (FIL_66)</option>
    <option value="sensores_distrito">Sensores por distrito (sesgo §7)</option>
    <option value="resiliencia">Transporte · resiliencia (FIL_64)</option>
    <option value="stgnn">Modelo STGNN · aristas influyentes (ML_05)</option>
  </select>
  <div class="desc" id="vista-desc"></div>
  <div style="margin-top:8px;border-top:1px solid rgba(255,255,255,.1);padding-top:8px">
    <b>Ruta entre 2 puntos</b>
    <select id="ruta-modo">
      <option value="proximo">a pie · PROXIMO_A ponderado (Dijkstra)</option>
      <option value="transporte">transporte · CONECTADO_CON (menos saltos)</option>
    </select>
    <button id="ruta-toggle">Elegir origen y destino</button>
    <div class="desc" id="ruta-estado"></div>
  </div>
</div>
<div id="capas" class="box"></div>
<div id="analisis" class="box" hidden></div>
</div>
<div id="panel">
  <h1>Grafo urbano de Madrid</h1>
  <div class="sub" id="meta">cargando…</div>
  <div id="detalle" class="muted">Haz clic en un nodo para ver sus atributos,
  su barrio/distrito y su vecindario <code>PROXIMO_A</code>.</div>
</div>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script>
const LIVE = __LIVE__;
const ENDPOINT = "__ENDPOINT__";
const COLORES = __COLORES__, DEFECTO = "__DEFECTO__";
let G = __DATA__;
let N = G.nodos || {}, PROX = G.prox || {}, CONN = G.conn || [], LINEAS = G.lineas_de || {};
let tipos = [], activos = new Set();
let ANALISIS = null, vista = "explorar";
let ruta = {activa:false, a:null, b:null};
const DIM = "#5f6672";

function mostrarError(m){
  const e = document.getElementById("err");
  e.textContent = "⚠ " + m; e.style.display = "block";
  console.error(m);
}
window.addEventListener("error", ev=>mostrarError((ev.error&&ev.error.stack)||ev.message));
window.addEventListener("unhandledrejection", ev=>mostrarError("promesa: "+((ev.reason&&ev.reason.stack)||ev.reason)));

const map = new maplibregl.Map({
  container:"map", style:"https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  center:[-3.703, 40.42], zoom:11, hash:true
});
map.addControl(new maplibregl.NavigationControl(), "bottom-right");

function colorNodo(n){
  if(vista==="aire_cobertura"){
    if(n.tipo==="trafico") return (ANALISIS&&ANALISIS._conAire&&ANALISIS._conAire.has(n.id)) ? "#4bbf73" : "#d1495b";
    if(n.tipo==="calidad_aire") return "#1b4965";
    return DIM;
  }
  if(vista==="aire_o3"){
    if(n.tipo!=="calidad_aire") return DIM;
    return (n.attrs&&n.attrs.contaminantes&&n.attrs.contaminantes.includes("O3")) ? "#4e79a7" : "#d1495b";
  }
  if(vista==="sensores_distrito")
    return (n.label==="EstacionMedida") ? (COLORES[n.tipo]||DEFECTO) : DIM;
  if(vista==="resiliencia")
    return (ANALISIS&&ANALISIS._artIds&&ANALISIS._artIds.has(n.id)) ? "#edae49" : DIM;
  if(vista==="stgnn")
    return (ANALISIS&&ANALISIS._stgnnIds&&ANALISIS._stgnnIds.has(n.id)) ? "#e15759" : DIM;
  return COLORES[n.tipo]||DEFECTO;
}
function nodosFC(){
  const soloAnalisis = vista!=="explorar";
  const destacado = n=> (vista==="resiliencia" && ANALISIS && ANALISIS._artIds && ANALISIS._artIds.has(n.id))
    || (vista==="stgnn" && ANALISIS && ANALISIS._stgnnIds && ANALISIS._stgnnIds.has(n.id));
  return {type:"FeatureCollection", features:Object.values(N)
    .filter(n=>n.lat!=null && (soloAnalisis || activos.has(n.tipo)))
    .map(n=>({type:"Feature", geometry:{type:"Point", coordinates:[n.lon,n.lat]},
      properties:{id:n.id, tipo:n.tipo, color:colorNodo(n), r:destacado(n)?2.2:1}}))};
}
function connFC(){
  return {type:"FeatureCollection", features:CONN.map(e=>{
    const a=N[e.a], b=N[e.b]; if(!a||!b) return null;
    return {type:"Feature", geometry:{type:"LineString",
      coordinates:[[a.lon,a.lat],[b.lon,b.lat]]}, properties:{modo:e.modo||"?"}};
  }).filter(Boolean)};
}

async function traerDatos(reintentos=4){
  let ultimo;
  for(let i=0;i<reintentos;i++){
    try{
      const r = await fetch(ENDPOINT + "/data");
      if(!r.ok) throw new Error("HTTP " + r.status);
      return await r.json();
    }catch(err){ ultimo = err; await new Promise(s=>setTimeout(s, 1200*(i+1))); }
  }
  throw ultimo;
}

let arrancado = false;
map.on("load", ()=>arrancar());

async function arrancar(){
  const meta = document.getElementById("meta");
  if(LIVE){
    meta.textContent = "cargando el grafo de Neo4j…";
    try{
      G = await traerDatos();
      N = G.nodos; CONN = G.conn; LINEAS = G.lineas_de || {};
    }catch(err){
      meta.innerHTML = "no se pudo cargar el grafo de Neo4j (" + esc(String(err)) +
        "). <button id='reintentar'>Reintentar</button>";
      document.getElementById("reintentar").onclick = ()=>arrancar();
      return;
    }
  }
  tipos = [...new Set(Object.values(N).map(n=>n.tipo))].sort();
  activos = new Set(tipos);

  if(arrancado){  // reintento exitoso: repuebla las fuentes ya creadas
    map.getSource("conn").setData(connFC());
    refrescarNodos();
    cargarAnalisis(); construirCapas();
    meta.textContent = `${Object.keys(N).length.toLocaleString("es")} nodos · ${CONN.length.toLocaleString("es")} tramos CONECTADO_CON · Neo4j en vivo`;
    return;
  }
  arrancado = true;

  map.addSource("conn", {type:"geojson", data:connFC()});
  map.addLayer({id:"conn", type:"line", source:"conn", paint:{"line-color":"#7773","line-width":1.1}});
  map.addSource("prox-sel", {type:"geojson", data:{type:"FeatureCollection",features:[]}});
  map.addLayer({id:"prox-sel", type:"line", source:"prox-sel",
    paint:{"line-color":"#d1495b","line-width":1.6,"line-opacity":0.8}});
  map.addSource("ruta", {type:"geojson", data:{type:"FeatureCollection",features:[]}});
  map.addLayer({id:"ruta", type:"line", source:"ruta",
    paint:{"line-color":"#20c997","line-width":4,"line-opacity":0.95}});
  map.addSource("ruta-ab", {type:"geojson", data:{type:"FeatureCollection",features:[]}});
  map.addLayer({id:"ruta-ab", type:"circle", source:"ruta-ab",
    paint:{"circle-radius":7,"circle-color":"#20c997","circle-stroke-width":2,"circle-stroke-color":"#fff"}});
  map.addSource("stgnn", {type:"geojson", data:{type:"FeatureCollection",features:[]}});
  map.addLayer({id:"stgnn", type:"line", source:"stgnn",
    paint:{"line-color":"#e15759","line-width":["+",1,["*",6,["get","w"]]],"line-opacity":0.85}});
  map.addSource("nodos", {type:"geojson", data:nodosFC()});
  map.addLayer({id:"nodos", type:"circle", source:"nodos",
    paint:{"circle-radius":["interpolate",["linear"],["zoom"],10,2.4,15,5.5],
      "circle-color":["get","color"],"circle-stroke-width":0.5,"circle-stroke-color":"rgba(255,255,255,.35)"}});
  map.addLayer({id:"nodos-hi", type:"circle", source:"nodos",
    filter:[">",["get","r"],1],
    paint:{"circle-radius":["interpolate",["linear"],["zoom"],10,5,15,11],
      "circle-color":["get","color"],"circle-stroke-width":1.4,"circle-stroke-color":"#fff"}});
  map.addLayer({id:"nodo-sel", type:"circle", source:"nodos",
    filter:["==","id",""], paint:{"circle-radius":9,"circle-color":"#0000","circle-stroke-width":2.5,"circle-stroke-color":"#d1495b"}});

  map.on("click","nodos", e=>seleccionar(e.features[0].properties.id));
  map.on("mouseenter","nodos", ()=>map.getCanvas().style.cursor="pointer");
  map.on("mouseleave","nodos", ()=>map.getCanvas().style.cursor="");

  cargarAnalisis();  // en paralelo; no bloquea el render
  document.getElementById("vista").addEventListener("change", e=>aplicarVista(e.target.value));
  document.getElementById("ruta-toggle").addEventListener("click", toggleRuta);
  document.getElementById("ruta-modo").addEventListener("change", ()=>{ if(ruta.a&&ruta.b) calcularRuta(); });

  const src = LIVE ? "Neo4j en vivo" : "snapshot grafo_urbano.json.gz";
  document.getElementById("meta").textContent =
    `${Object.keys(N).length.toLocaleString("es")} nodos · ${CONN.length.toLocaleString("es")} tramos CONECTADO_CON · ${src}`;
  construirCapas();
}

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
function fmt(n){return (n==null)?"—":Number(n).toLocaleString("es");}

// ---- Análisis del TFM proyectados sobre el grafo -----------------------------

async function cargarAnalisis(){
  if(LIVE){
    try{
      const r = await fetch(ENDPOINT + "/analisis");
      if(r.ok) ANALISIS = await r.json();
    }catch(e){ ANALISIS = null; }
  }
  if(!ANALISIS){  // modo embebido / sin backend: lo que se puede derivar aquí
    ANALISIS = derivarAnalisisLocal();
  }
  prepararAnalisis();
}

function derivarAnalisisLocal(){
  // cobertura de aire y sensores por distrito se pueden calcular con PROX + N
  const aire = new Set(Object.values(N).filter(n=>n.tipo==="calidad_aire").map(n=>n.id));
  const traf = Object.values(N).filter(n=>n.tipo==="trafico");
  const conAire = traf.filter(t=>(PROX[t.id]||[]).some(([vid])=>aire.has(vid))).map(t=>t.id);
  const porDist = {};
  for(const n of Object.values(N)) if(n.label==="EstacionMedida" && n.distrito){
    (porDist[n.distrito] ||= {distrito:n.distrito,n:0,trafico:0,aire:0});
    porDist[n.distrito].n++; if(n.tipo==="trafico") porDist[n.distrito].trafico++;
    if(n.tipo==="calidad_aire") porDist[n.distrito].aire++;
  }
  return {
    cobertura_aire:{trafico_total:traf.length, con_aire_cerca:conAire.length,
      sin_aire_cerca:traf.length-conAire.length, ids_con_aire:conAire},
    sensores_por_distrito:Object.values(porDist).sort((a,b)=>b.n-a.n),
    stgnn_aristas_influyentes:[], resiliencia:{}, _local:true,
  };
}

function prepararAnalisis(){
  const A = ANALISIS;
  A._conAire = new Set((A.cobertura_aire&&A.cobertura_aire.ids_con_aire)||[]);
  A._stgnnIds = new Set();
  for(const e of A.stgnn_aristas_influyentes||[]) (e.ids||[]).forEach(id=>A._stgnnIds.add(id));
  // resiliencia: casar el nombre de parada -> id de :ParadaTransporte
  const porNombre = {};
  for(const n of Object.values(N)) if(n.label==="ParadaTransporte" && n.nombre)
    porNombre[n.nombre.toLowerCase()] = n.id;
  A._artIds = new Set();
  for(const p of (A.resiliencia&&A.resiliencia.puntos_articulacion)||[]){
    const id = porNombre[(p.parada||"").toLowerCase()];
    if(id){ p._id = id; A._artIds.add(id); }
  }
  aplicarVista(vista);
}

function refrescarNodos(){
  if(map.getSource("nodos")) map.getSource("nodos").setData(nodosFC());
}

function aplicarVista(v){
  vista = v;
  document.getElementById("capas").hidden = (v!=="explorar");
  const stgnnFC = {type:"FeatureCollection", features:(v==="stgnn"&&ANALISIS?ANALISIS.stgnn_aristas_influyentes:[])
    .map(e=>({type:"Feature", geometry:{type:"LineString", coordinates:[e.a,e.b]}, properties:{w:e.w}}))};
  if(map.getSource("stgnn")) map.getSource("stgnn").setData(stgnnFC);
  refrescarNodos();
  panelAnalisis(v);
}

function panelAnalisis(v){
  const box = document.getElementById("analisis"), desc = document.getElementById("vista-desc");
  const A = ANALISIS || {};
  const DESC = {
    explorar:"Nodos por tipo. Clic en uno → sus atributos y su vecindario PROXIMO_A.",
    aire_cobertura:"Estaciones de tráfico coloreadas según tengan (verde) o no (rojo) una estación de calidad del aire a ≤300 m.",
    aire_o3:"Estaciones de calidad del aire: azul si miden O₃, rojo si no. Cada estación mide un subconjunto distinto (FIL_66).",
    sensores_distrito:"Nº de estaciones de medida por distrito — el sesgo de cobertura que la memoria declara en §7.",
    resiliencia:"Puntos de articulación de la red de transporte (CONECTADO_CON): paradas cuya caída la parte en dos (FIL_64).",
    stgnn:"Las 15 conexiones que el STGNN de tráfico marca como más influyentes (importancia de arista, ML_05).",
  };
  desc.textContent = DESC[v] || "";
  if(v==="explorar"){ box.hidden = true; return; }
  box.hidden = false;
  let h = "";
  if(v==="aire_cobertura" && A.cobertura_aire){
    const c = A.cobertura_aire;
    h = `<h2>Cobertura de calidad del aire</h2>
      <div class="big">${fmt(c.sin_aire_cerca)} / ${fmt(c.trafico_total)}</div>
      estaciones de tráfico <b>sin</b> ninguna estación de aire a ≤300 m
      (${(100*c.sin_aire_cerca/c.trafico_total).toFixed(0)} %). Solo hay
      ${fmt(Object.values(N).filter(n=>n.tipo==="calidad_aire").length)} estaciones de aire para toda la ciudad.`;
  } else if(v==="aire_o3"){
    const air = Object.values(N).filter(n=>n.tipo==="calidad_aire");
    const o3 = air.filter(n=>n.attrs&&n.attrs.contaminantes&&n.attrs.contaminantes.includes("O3"));
    h = `<h2>¿Qué mide cada estación de aire?</h2>
      <div class="big">${o3.length} / ${air.length}</div>
      estaciones de calidad del aire miden O₃. El resto solo NOx/PM — pedir "aire cerca de X"
      puede devolver una estación que no mide el contaminante que importa.`;
  } else if(v==="sensores_distrito"){
    const rows = (A.sensores_por_distrito||[]).map(d=>
      `<tr><td>${esc(d.distrito)}</td><td>${fmt(d.n)}</td><td>${fmt(d.trafico)}</td><td>${fmt(d.aire)}</td></tr>`).join("");
    h = `<h2>Sensores por distrito</h2><table>
      <tr><td><b>distrito</b></td><td><b>total</b></td><td><b>tráf.</b></td><td><b>aire</b></td></tr>${rows}</table>`;
  } else if(v==="resiliencia" && A.resiliencia){
    const R = A.resiliencia;
    const rows = (R.puntos_articulacion||[]).slice(0,12).map(p=>
      `<tr><td>${esc(p.parada)}</td><td>${esc(p.modo||"")}</td><td>${fmt(p.nodos_desgajados)}</td></tr>`).join("");
    h = `<h2>Resiliencia del transporte (FIL_64)</h2>
      <div class="big">${fmt(R.n_puntos_articulacion)}</div> puntos de articulación ·
      ${fmt(R.puentes&&R.puentes.n_puentes)} puentes (${((R.puentes&&R.puentes.frac_aristas_puente||0)*100).toFixed(0)} % de las aristas) ·
      k-core máx ${fmt(R.kcore&&R.kcore.k_max)}.
      Al 5 % de bajas dirigidas el fragmento mayor cae a
      ${R.robustez_5pct?Math.round(R.robustez_5pct.dirigido*100):"—"} % (vs
      ${R.robustez_5pct?Math.round(R.robustez_5pct.aleatorio*100):"—"} % aleatorio).
      <table><tr><td><b>parada</b></td><td><b>modo</b></td><td><b>desgaja</b></td></tr>${rows}</table>
      ${R.nota?`<div class="nota">${esc(R.nota)}</div>`:""}`;
  } else if(v==="stgnn"){
    const es = (A.stgnn_aristas_influyentes||[]);
    const rows = es.slice(0,12).map(e=>{
      const na = N[e.ids[0]], nb = N[e.ids[1]];
      return `<tr><td>${esc((na&&na.nombre)||e.ids[0].split(":").pop())} ↔ ${esc((nb&&nb.nombre)||e.ids[1].split(":").pop())}</td><td>${e.w.toFixed(2)}</td></tr>`;
    }).join("");
    h = es.length
      ? `<h2>STGNN · aristas influyentes (ML_05)</h2>
         Grosor ∝ importancia relativa que el modelo asigna a la conexión entre dos
         puntos de tráfico. <table><tr><td><b>conexión</b></td><td><b>peso</b></td></tr>${rows}</table>`
      : `<h2>STGNN · aristas influyentes</h2><span class="muted">disponible solo en modo live (necesita stgnn_trafico.meta.json)</span>`;
  }
  box.innerHTML = h;
}

async function vecinosDe(id){
  if(!LIVE) return (PROX[id]||[]).map(([vid,d])=>({id:vid, distancia_m:d, nodo:N[vid]}));
  try{
    const r = await fetch(ENDPOINT + "/vecindario?id=" + encodeURIComponent(id) + "&radio_m=300");
    if(!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();
    return j.vecinos.map(v=>{ if(!N[v.id]) N[v.id] = v; return {id:v.id, distancia_m:v.distancia_m, nodo:v}; });
  }catch(err){ return []; }
}

// ---- Ruta entre 2 puntos (capacidad de enrutado del grafo DB) ---------------

function toggleRuta(){
  ruta.activa = !ruta.activa;
  document.getElementById("ruta-toggle").classList.toggle("on", ruta.activa);
  const est = document.getElementById("ruta-estado");
  if(ruta.activa){ est.textContent = "clic en el nodo ORIGEN"; }
  else { limpiarRuta(); est.textContent = ""; }
}
function limpiarRuta(){
  ruta.a = ruta.b = null;
  for(const s of ["ruta","ruta-ab"]) if(map.getSource(s)) map.getSource(s).setData({type:"FeatureCollection",features:[]});
}
function marcarAB(){
  const pts = [ruta.a, ruta.b].filter(Boolean).filter(id=>N[id]&&N[id].lat!=null)
    .map(id=>({type:"Feature", geometry:{type:"Point", coordinates:[N[id].lon,N[id].lat]}, properties:{}}));
  map.getSource("ruta-ab").setData({type:"FeatureCollection", features:pts});
}
function rutaPick(id){
  const est = document.getElementById("ruta-estado");
  if(!N[id]){ return; }
  if(!ruta.a || (ruta.a && ruta.b)){ ruta = {activa:true, a:id, b:null}; marcarAB();
    est.textContent = "origen: " + (N[id].nombre||id.split(":").pop()) + " — clic en el DESTINO"; return; }
  ruta.b = id; marcarAB(); est.textContent = "calculando…"; calcularRuta();
}
async function calcularRuta(){
  const modo = document.getElementById("ruta-modo").value;
  const est = document.getElementById("ruta-estado");
  try{
    const r = await fetch(ENDPOINT + "/ruta?a=" + encodeURIComponent(ruta.a) + "&b=" + encodeURIComponent(ruta.b) + "&modo=" + modo);
    if(r.status === 404){ est.textContent = "sin ruta " + modo + " entre esos dos puntos";
      map.getSource("ruta").setData({type:"FeatureCollection",features:[]}); return; }
    if(!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json();
    const coords = (j.nodos||[]).filter(n=>n.lat!=null).map(n=>[n.lon,n.lat]);
    map.getSource("ruta").setData({type:"FeatureCollection", features:coords.length>1
      ? [{type:"Feature", geometry:{type:"LineString", coordinates:coords}, properties:{}}] : []});
    const na = N[j.a]&&N[j.a].nombre || j.a.split(":").pop(), nb = N[j.b]&&N[j.b].nombre || j.b.split(":").pop();
    const detalle = j.modo==="proximo"
      ? (fmt(j.metros) + " m · " + j.saltos + " saltos PROXIMO_A")
      : (j.saltos + " tramos · " + ((j.lineas&&j.lineas.length)?("líneas: "+j.lineas.join(", ")):"sin línea"));
    est.innerHTML = "<b>" + esc(na) + " → " + esc(nb) + "</b><br>" + detalle +
      " · <button id='ruta-clear' style='width:auto;padding:2px 8px;margin:2px 0'>limpiar</button>";
    document.getElementById("ruta-clear").onclick = ()=>{ limpiarRuta(); est.textContent = "clic en el nodo ORIGEN"; };
  }catch(err){ est.textContent = "error al calcular la ruta: " + err; }
}

async function seleccionar(id){
  if(ruta.activa){ return rutaPick(id); }
  const n = N[id]; if(!n) return;
  map.setFilter("nodo-sel", ["==","id",id]);
  document.getElementById("detalle").textContent = "cargando vecindario…";
  const vecinos = (await vecinosDe(id)).sort((a,b)=>a.distancia_m-b.distancia_m);

  map.getSource("prox-sel").setData({type:"FeatureCollection", features:vecinos.map(({nodo})=>{
    if(!nodo || nodo.lat==null) return null;
    return {type:"Feature", geometry:{type:"LineString",
      coordinates:[[n.lon,n.lat],[nodo.lon,nodo.lat]]}, properties:{}};
  }).filter(Boolean)});

  const porTipo = {};
  for(const {distancia_m, nodo} of vecinos){ if(!nodo) continue;
    (porTipo[nodo.tipo] ||= []).push(`${esc(nodo.nombre||nodo.id.split(":").pop())} · ${distancia_m} m`); }

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
  const det = document.getElementById("detalle");
  det.innerHTML = h; det.classList.remove("muted");
}
</script></body></html>
"""


def construir(*, live: bool = False, endpoint: str = "/grafo/explorador") -> str:
    if live:
        datos = "{}"
    else:
        with gzip.open(_GRAFO, "rt", encoding="utf-8") as fh:
            datos = json.dumps(_compactar(json.load(fh)), ensure_ascii=False, separators=(",", ":"))
    return (
        _TEMPLATE
        .replace("__LIVE__", "true" if live else "false")
        .replace("__ENDPOINT__", endpoint)
        .replace("__DATA__", datos)
        .replace("__COLORES__", json.dumps(_COLORES, ensure_ascii=False))
        .replace("__DEFECTO__", _DEFECTO)
    )


def main(argv: "list[str] | None" = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    live = "--live" in argv
    out = _DIR / ("grafo_explorador_live.html" if live else "grafo_explorador.html")
    out.write_text(construir(live=live), encoding="utf-8")
    print(f"{out}  ({out.stat().st_size / 1024:,.0f} KB){'  [live -> /grafo/explorador]' if live else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
