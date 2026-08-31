"""FIL_34 (M3) — el mapa animado del grafo de Madrid.

Lee `viz/grafo_madrid.json` + `viz/data/prevision_animada.parquet` +
`viz/data/gold_slices/` y escribe:

- `viz/mapa/index.html`  — deck.gl (CDN) sobre los polígonos de distrito
  (sin tiles), bucle de 24 h, selector de día/métrica/horizonte, ticker
  meteo, arcos de importancia de aristas (E1). Carga `data.json` /
  `weather.json` por `fetch` (servir con `python -m http.server` o Pages).
- `viz/mapa/data.json`     — frames cuantizados (int) por día/hora/nodo.
- `viz/mapa/weather.json`   — media ciudad por día/hora (E5).
- `viz/mapa_frames.png`     — tira de 6 fotogramas, sin tiles, para la memoria.

    python -m viz.build_mapa_animado

Cero red, cero credenciales.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_VIZ = Path(__file__).resolve().parent
_GRAFO = json.loads((_VIZ / "grafo_madrid.json").read_text(encoding="utf-8"))
_PARQUET = _VIZ / "data" / "prevision_animada.parquet"
_METEO = _VIZ / "data" / "gold_slices" / "meteorologia_por_estacion_magnitud_hora.parquet"
_GEOJSON = json.loads((_VIZ / "assets" / "distritos_madrid.geojson").read_text(encoding="utf-8"))
_OUT = _VIZ / "mapa"
_DECKGL_CDN = "https://unpkg.com/deck.gl@9.0.38/dist.min.js"

# métricas del selector -> (columna del parquet, [min, max] para la escala,
# etiqueta, sentido: +1 = más alto peor)
_METRICAS = {
    "salud": ("health_index", [55, 96], "Índice de salud (100 = mejor)", -1),
    "trafico": ("y_traf_h1", [0.0, 2.5], "Nivel de servicio previsto (h1)", 1),
    "no2": ("no2", [5, 50], "NO₂ previsto µg/m³", 1),
    "o3": ("o3", [20, 130], "O₃ previsto µg/m³", 1),
}
_HORIZ_COL = {"now": "y_traf_obs", "h1": "y_traf_h1", "h3": "y_traf_h3", "h6": "y_traf_h6"}


def _frames_json(df: pd.DataFrame, node_ids: "list[str]") -> dict:
    """`{dia: {metrica: [[valor_int]*n_nodos]*24}}`. Los nulos -> -1."""
    idx = {nid: i for i, nid in enumerate(node_ids)}
    out: dict = {}
    for dia, g_dia in df.groupby("day"):
        md: dict = {}
        for clave, (col, _, _, _) in _METRICAS.items():
            arr = [[-1] * len(node_ids) for _ in range(24)]
            for h, nid, v in zip(g_dia["hour"], g_dia["node_id"], g_dia[col]):
                if pd.notna(v):
                    arr[int(h)][idx[nid]] = round(float(v) * (100 if clave == "trafico" else 1))
            md[clave] = arr
        # columnas de horizonte para el toggle (solo tráfico) + real h1 para el skill
        for hk, hcol in {**_HORIZ_COL, "h1_act": "y_traf_act_h1"}.items():
            arr = [[-1] * len(node_ids) for _ in range(24)]
            for h, nid, v in zip(g_dia["hour"], g_dia["node_id"], g_dia[hcol]):
                if pd.notna(v):
                    arr[int(h)][idx[nid]] = round(float(v) * 100)
            md[f"traf_{hk}"] = arr
        out[str(dia)] = md
    return out


def _weather_json(dias: "list[str]") -> dict:
    m = pd.read_parquet(_METEO)
    m = m[m["date"].isin(dias)]
    piv = (
        m.groupby(["date", "hour", "magnitude"])["avg_value"].mean().unstack("magnitude").reset_index()
    )
    out: dict = {}
    for _, r in piv.iterrows():
        out.setdefault(str(r["date"]), {})[int(r["hour"])] = {
            "temp_c": round(float(r.get("temperature_c", float("nan"))), 1),
            "wind_ms": round(float(r.get("wind_speed_ms", float("nan"))), 1),
            "precip": round(float(r.get("precipitation_lm2", float("nan"))), 2),
            "humidity": round(float(r.get("humidity_pct", float("nan"))), 0),
        }
    return out


def _meta(node_ids: "list[str]", dias: "list[str]") -> dict:
    nodos = {n["id"]: n for n in _GRAFO["nodos"]}
    coords = [[round(nodos[i]["lon"], 5), round(nodos[i]["lat"], 5)] for i in node_ids]
    distr = [nodos[i]["distrito"] for i in node_ids]
    idx = {nid: k for k, nid in enumerate(node_ids)}
    # aristas top-15 de importancia -> pares de índice + importancia normalizada
    imp = _GRAFO["importancia_aristas"]
    mx = max(e["importancia"] for e in imp) or 1.0
    arcs = [
        {"s": idx[e["a"]], "t": idx[e["b"]], "w": round(e["importancia"] / mx, 3)}
        for e in imp
        if e["a"] in idx and e["b"] in idx
    ]
    # textura del grafo: submuestreo de aristas (1 de cada 6) para no saturar
    tex = [[idx[e["a"]], idx[e["b"]]] for e in _GRAFO["aristas"][::6] if e["a"] in idx and e["b"] in idx]
    return {
        "generado": pd.Timestamp.utcnow().isoformat(timespec="seconds"),
        "n_nodos": len(node_ids),
        "dias": dias,
        "dow": {d: pd.Timestamp(d).day_name() for d in dias},
        "coords": coords,
        "distrito": distr,
        "arcs": arcs,
        "tex": tex,
        "metricas": {k: {"rango": v[1], "label": v[2], "peor": v[3]} for k, v in _METRICAS.items()},
        "distritos_geojson": _GEOJSON,
    }


def _html() -> str:
    return _TEMPLATE.replace("__DECKGL_CDN__", _DECKGL_CDN)


def _frame_strip_png(df: pd.DataFrame, dia: str) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    horas = [3, 7, 10, 14, 18, 21]
    g = df[df["day"] == dia]
    fig, axes = plt.subplots(1, 6, figsize=(19, 3.4), constrained_layout=True)
    polys = [
        [(x, y) for x, y in feat["geometry"]["coordinates"][0]]
        for feat in _GEOJSON["features"]
    ]
    for ax, h in zip(axes, horas):
        gh = g[g["hour"] == h]
        ax.add_collection(PolyCollection(polys, facecolors="none", edgecolors="#ccc", linewidths=0.4))
        sc = ax.scatter(
            gh["lon"], gh["lat"], c=gh["health_index"], cmap="RdYlGn",
            vmin=55, vmax=96, s=3, linewidths=0,
        )
        ax.set_title(f"{h:02d}:00", fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")
        ax.autoscale_view()
    fig.colorbar(sc, ax=axes, shrink=0.7, label="índice de salud")
    fig.suptitle(f"Madrid — índice de salud sobre el grafo, {dia} ({pd.Timestamp(dia).day_name()})", fontsize=12)
    out = _VIZ / "mapa_frames.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def main() -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(_PARQUET)
    node_ids = [n["id"] for n in _GRAFO["nodos"]]
    dias = sorted(df["day"].unique().tolist())

    (_OUT / "data.json").write_text(
        json.dumps(_frames_json(df, node_ids), separators=(",", ":")), encoding="utf-8"
    )
    (_OUT / "weather.json").write_text(
        json.dumps(_weather_json(dias), separators=(",", ":")), encoding="utf-8"
    )
    (_OUT / "meta.json").write_text(
        json.dumps(_meta(node_ids, dias), separators=(",", ":")), encoding="utf-8"
    )
    (_OUT / "index.html").write_text(_html(), encoding="utf-8")
    png = _frame_strip_png(df, "2026-08-26")

    for p in ("index.html", "meta.json", "data.json", "weather.json"):
        kb = (_OUT / p).stat().st_size / 1024
        print(f"  viz/mapa/{p}  {kb:,.0f} KB")
    print(f"  {png.relative_to(_VIZ.parent)}")
    print("\n  Servir: python -m http.server -d viz/mapa   ->  http://localhost:8000")
    return 0


_TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Madrid — mapa animado del grafo</title>
<script src="__DECKGL_CDN__"></script>
<style>
  :root { color-scheme: light dark; }
  html,body { margin:0; height:100%; font-family:system-ui,Segoe UI,Roboto,sans-serif; }
  #map { position:absolute; inset:0; background:#0b0f14; }
  .panel { position:absolute; background:rgba(20,24,30,.82); color:#e8edf2;
    backdrop-filter:blur(4px); border-radius:10px; padding:12px 14px; font-size:13px; }
  #controls { left:12px; top:12px; width:260px; }
  #context  { right:12px; top:12px; width:230px; }
  #ticker   { left:12px; bottom:12px; }
  #controls h1 { font-size:14px; margin:0 0 8px; font-weight:650; }
  .row { display:flex; gap:6px; align-items:center; margin:7px 0; flex-wrap:wrap; }
  button { background:#2a3340; color:#e8edf2; border:1px solid #3a4756; border-radius:6px;
    padding:4px 9px; cursor:pointer; font-size:12px; }
  button.on { background:#3d6ce0; border-color:#3d6ce0; }
  input[type=range] { flex:1; }
  .leg { height:10px; border-radius:3px; margin-top:6px;
    background:linear-gradient(90deg,#d7191c,#fdae61,#ffffbf,#a6d96a,#1a9641); }
  .leg.rev { background:linear-gradient(90deg,#1a9641,#a6d96a,#ffffbf,#fdae61,#d7191c); }
  .muted { color:#9fb0c0; font-size:11px; }
  b.big { font-size:15px; }
</style>
</head>
<body>
<div id="map"></div>

<div class="panel" id="controls">
  <h1>Madrid · grafo animado</h1>
  <div class="row" id="days"></div>
  <div class="row">
    <button data-h="now" class="hz on">ahora</button>
    <button data-h="h1" class="hz">+1h</button>
    <button data-h="h3" class="hz">+3h</button>
    <button data-h="h6" class="hz">+6h</button>
  </div>
  <div class="row" id="metrics"></div>
  <div class="row">
    <button id="play">▶︎</button>
    <input type="range" id="hour" min="0" max="23" value="8">
    <span id="hlabel" style="width:44px;text-align:right">08:00</span>
  </div>
  <div class="row" style="margin-bottom:2px"><span id="metlabel" class="muted"></span></div>
  <div class="leg" id="leg"></div>
  <div class="muted" id="legrange" style="display:flex;justify-content:space-between"></div>
  <div class="muted" style="margin-top:8px">Arcos = 15 conexiones más influyentes del STGNN (importancia estática, grosor animado por el tráfico).</div>
</div>

<div class="panel" id="context">
  <div class="muted">día</div><b class="big" id="ctx-day">—</b>
  <div class="muted" style="margin-top:8px">hora</div><b class="big" id="ctx-hour">—</b>
  <div class="muted" style="margin-top:8px">skill STGNN vs persistencia (h1)</div>
  <b class="big" id="ctx-skill">—</b>
  <div class="muted" id="ctx-hint" style="margin-top:8px"></div>
</div>

<div class="panel" id="ticker"><span id="wx">meteo —</span></div>

<script>
const {DeckGL, ScatterplotLayer, LineLayer, ArcLayer, GeoJsonLayer} = deck;
let META, DATA, WX, state = {day:null, hour:8, metric:"salud", hz:"now", playing:false};

const scale = (v, lo, hi) => Math.max(0, Math.min(1, (v-lo)/(hi-lo)));
// rampa RdYlGn (5 paradas) -> rgb
const RAMP = [[215,25,28],[253,174,97],[255,255,191],[166,217,106],[26,150,65]];
function ramp(t){ const x=t*(RAMP.length-1), i=Math.floor(x), f=x-i;
  const a=RAMP[i], b=RAMP[Math.min(i+1,RAMP.length-1)];
  return [0,1,2].map(k=>Math.round(a[k]+(b[k]-a[k])*f)); }

function currentValues(){
  const md = DATA[state.day];
  if(state.metric==="trafico"){ return md["traf_"+state.hz][state.hour]; }
  return md[state.metric][state.hour];
}
function colorFor(v, m){
  if(v<0) return [90,100,110,120];
  const [lo,hi] = META.metricas[m].rango;
  let t = scale(state.metric==="trafico"? v/100 : v, lo, hi);
  if(META.metricas[m].peor>0) t = 1-t;      // alto = malo -> rojo
  const c = ramp(t); return [c[0],c[1],c[2],210];
}

function layers(){
  const vals = currentValues();
  const trafNow = DATA[state.day]["traf_"+(state.hz==="now"?"now":state.hz)][state.hour];
  return [
    new GeoJsonLayer({id:"distr", data:META.distritos_geojson, stroked:true, filled:true,
      getFillColor:[255,255,255,6], getLineColor:[255,255,255,40], lineWidthMinPixels:1}),
    new LineLayer({id:"tex", data:META.tex, getSourcePosition:d=>META.coords[d[0]],
      getTargetPosition:d=>META.coords[d[1]], getColor:[255,255,255,14], getWidth:1}),
    new ArcLayer({id:"imp", data:META.arcs,
      getSourcePosition:d=>META.coords[d.s], getTargetPosition:d=>META.coords[d.t],
      getSourceColor:d=>{const a=trafNow[d.s]; return a>0?ramp(1-scale(a/100,0,2.5)).concat(230):[120,140,255,120];},
      getTargetColor:d=>{const a=trafNow[d.t]; return a>0?ramp(1-scale(a/100,0,2.5)).concat(230):[120,140,255,120];},
      getWidth:d=>1+6*d.w, getHeight:0.4}),
    new ScatterplotLayer({id:"nodes", data:vals.map((v,i)=>i), radiusMinPixels:1.6, radiusMaxPixels:5,
      getPosition:i=>META.coords[i], getRadius:60,
      getFillColor:i=>colorFor(vals[i], state.metric), updateTriggers:{getFillColor:[state.day,state.hour,state.metric,state.hz]}}),
  ];
}

let dgl;
function render(){
  dgl.setProps({layers: layers()});
  const md = META.metricas[state.metric];
  document.getElementById("metlabel").textContent = md.label;
  document.getElementById("leg").className = "leg" + (md.peor>0 ? "" : " rev");
  document.getElementById("legrange").innerHTML = `<span>${md.rango[0]}</span><span>${md.rango[1]}</span>`;
  const hh = String(state.hour).padStart(2,"0")+":00";
  document.getElementById("hlabel").textContent = hh;
  document.getElementById("ctx-day").textContent = state.day + " · " + (META.dow[state.day]||"");
  document.getElementById("ctx-hour").textContent = hh;
  const w = (WX[state.day]||{})[state.hour];
  document.getElementById("wx").textContent = w
    ? `${state.day} ${hh} · ${w.temp_c}°C · viento ${w.wind_ms} m/s · lluvia ${w.precip} l/m² · HR ${w.humidity}%`
    : "meteo —";
  document.getElementById("ctx-skill").textContent = skill().toFixed(2);
  document.getElementById("ctx-hint").textContent = state.metric==="trafico"
    ? "Tráfico: horizonte del toggle." : "El toggle de horizonte solo afecta al tráfico.";
}

function skill(){  // 1 - MAE(stgnn h1) / MAE(persistencia) sobre el frame
  const md = DATA[state.day];
  const p = md["traf_now"][state.hour], f = md["traf_h1"][state.hour];
  const act = md["traf_h1_act"] ? md["traf_h1_act"][state.hour] : null;
  if(!act) return NaN;
  let es=0, ep=0, n=0;
  for(let i=0;i<f.length;i++){ if(f[i]<0||p[i]<0||act[i]<0) continue;
    es+=Math.abs(f[i]-act[i]); ep+=Math.abs(p[i]-act[i]); n++; }
  return n && ep ? 1 - es/ep : NaN;
}

function mkButtons(){
  const dd = document.getElementById("days");
  META.dias.forEach((d,k)=>{ const b=document.createElement("button");
    b.textContent = d.slice(5); b.className = k===0?"day on":"day";
    b.onclick=()=>{ state.day=d; document.querySelectorAll(".day").forEach(x=>x.classList.remove("on"));
      b.classList.add("on"); render(); }; dd.appendChild(b); });
  const mm = document.getElementById("metrics");
  Object.keys(META.metricas).forEach((m,k)=>{ const b=document.createElement("button");
    b.textContent = m; b.className = k===0?"met on":"met";
    b.onclick=()=>{ state.metric=m; document.querySelectorAll(".met").forEach(x=>x.classList.remove("on"));
      b.classList.add("on"); render(); }; mm.appendChild(b); });
  document.querySelectorAll(".hz").forEach(b=>b.onclick=()=>{ state.hz=b.dataset.h;
    document.querySelectorAll(".hz").forEach(x=>x.classList.remove("on")); b.classList.add("on"); render(); });
  const hr=document.getElementById("hour");
  hr.oninput=()=>{ state.hour=+hr.value; render(); };
  const pl=document.getElementById("play");
  pl.onclick=()=>{ state.playing=!state.playing; pl.textContent=state.playing?"❚❚":"▶︎";
    if(state.playing) tick(); };
}
function tick(){ if(!state.playing) return;
  state.hour=(state.hour+1)%24; document.getElementById("hour").value=state.hour; render();
  setTimeout(tick, 650); }

Promise.all([
  fetch("./meta.json").then(r=>r.json()),
  fetch("./data.json").then(r=>r.json()),
  fetch("./weather.json").then(r=>r.json()),
]).then(([m,d,w])=>{
  META=m; DATA=d; WX=w; state.day=m.dias[0];
  dgl = new DeckGL({container:"map",
    initialViewState:{longitude:-3.69, latitude:40.43, zoom:10.4, pitch:35, bearing:-8},
    controller:true, layers:[]});
  mkButtons(); render();
}).catch(e=>{ document.getElementById("map").innerHTML =
  "<p style='color:#ccc;font:14px system-ui;padding:24px'>No se pudieron cargar los datos. "
  +"Sirve la carpeta con <code>python -m http.server -d viz/mapa</code>.<br>"+e+"</p>"; });
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
