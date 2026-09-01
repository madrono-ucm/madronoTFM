"""Genera el mapa animado del grafo de tráfico de Madrid.

Es el entregable de visualización del TFM: un HTML autónomo que se publica
en GitHub Pages y muestra los ~1.798 nodos del grafo latiendo hora a hora
con la previsión de los dos STGNN (tráfico y calidad del aire), sobre los
polígonos de distrito y sin tiles de mapa base (opcionalmente, un basemap
vectorial Carto).

Lee de local (nunca de red ni con credenciales): el grafo canónico
(`viz/grafo_madrid.json`), la previsión ya inferida
(`viz/data/prevision_animada.parquet`), los cortes congelados de Gold
(`viz/data/gold_slices/`) y las capas geográficas (`viz/assets/*.geojson`).

Escribe en `viz/mapa/`:

- `index.html`   — la interfaz completa (deck.gl vía CDN). Bucle de 24 h;
  cuatro grupos de control colapsables (Tiempo / Capa de color / Salud /
  Vista / Ruta); cámara 2D/3D con "encajar a Madrid" y "vista limpia";
  nodos como puntos o como barras extruidas cuya altura crece donde las
  condiciones son peores; etiquetas de distrito, hitos, ejes y parques
  como capas conmutables; tooltip y detalle al hacer clic en un nodo;
  panel de resumen inferior (media de ciudad de 24 h, desglose por
  distrito, meteo y skill del modelo). Carga los tres JSON de abajo más
  `rutas.json` (opcional) con `fetch`.
- `data.json`    — los valores por día, hora y nodo, cuantizados a entero
  (los nulos van como -1 para no inflar el JSON).
- `meta.json`    — todo lo estático: grafo, distritos, centroides, hitos,
  ejes, parques, perfiles de sensibilidad y umbrales OMS/UE.
- `weather.json` — la media de ciudad de meteo por día y hora.

Y en `viz/`: `mapa_frames.png`, una tira de fotogramas para la memoria.

Uso:

    python -m viz.build_mapa_animado
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
_EJES = json.loads((_VIZ / "assets" / "ejes_madrid.geojson").read_text(encoding="utf-8"))
_PARQUES = json.loads((_VIZ / "assets" / "parques_madrid.geojson").read_text(encoding="utf-8"))
_OUT = _VIZ / "mapa"
_DECKGL_CDN = "https://unpkg.com/deck.gl@9.0.38/dist.min.js"
# El basemap vectorial (maplibre-gl) es opcional y opt-in: solo se descargan
# tiles si quien mira el mapa elige un estilo Carto en el selector. Si el CDN
# no carga, el selector queda deshabilitado y el mapa sigue siendo el DeckGL
# plano de siempre. Se cargó como mejora en FIL_50.
_MAPLIBRE_JS_CDN = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"
_MAPLIBRE_CSS_CDN = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"


def _centroide(anillo: "list[list[float]]") -> "list[float]":
    """Centroide (media aritmética de vértices) de un anillo de polígono,
    redondeado a 5 decimales. Aproximación suficiente para colocar la
    etiqueta de texto de un distrito, no un centroide geométrico exacto."""
    xs = [p[0] for p in anillo]
    ys = [p[1] for p in anillo]
    return [round(sum(xs) / len(xs), 5), round(sum(ys) / len(ys), 5)]

# Métricas que ofrece el selector de color, cada una como:
#   clave -> (columna del parquet, [mínimo, máximo] de la escala,
#             etiqueta para la leyenda, sentido: +1 si "más alto es peor")
_METRICAS = {
    "salud": ("health_index", [55, 96], "Índice de salud (100 = mejor)", -1),
    "trafico": ("y_traf_h1", [0.0, 2.5], "Nivel de servicio previsto (h1)", 1),
    "no2": ("no2", [5, 50], "NO₂ previsto µg/m³", 1),
    "o3": ("o3", [20, 130], "O₃ previsto µg/m³", 1),
}
_HORIZ_COL = {"now": "y_traf_obs", "h1": "y_traf_h1", "h3": "y_traf_h3", "h6": "y_traf_h6"}


def _frames_json(df: pd.DataFrame, node_ids: "list[str]") -> dict:
    """Construye el contenido de `data.json`.

    Estructura: `{dia: {metrica: matriz[24 horas][n_nodos]}}` con los
    valores redondeados a entero (el navegador solo necesita la precisión
    del color) y los nulos como -1, para que el JSON quepa en unos pocos MB.
    El tráfico se multiplica por 100 antes de redondear porque llega en
    "nivel de servicio" (0-3), demasiado pequeño para cuantizar a entero.
    """
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
        # Series de tráfico por horizonte de previsión (para el selector
        # ahora/+1h/+3h/+6h) más la observación real a +1h, que el cliente
        # usa para calcular el "skill" del modelo frente a la persistencia.
        for hk, hcol in {**_HORIZ_COL, "h1_act": "y_traf_act_h1"}.items():
            arr = [[-1] * len(node_ids) for _ in range(24)]
            for h, nid, v in zip(g_dia["hour"], g_dia["node_id"], g_dia[hcol]):
                if pd.notna(v):
                    arr[int(h)][idx[nid]] = round(float(v) * 100)
            md[f"traf_{hk}"] = arr
        out[str(dia)] = md
    return out


def _weather_json(dias: "list[str]") -> dict:
    """Construye `weather.json`: la media de ciudad de temperatura, viento,
    precipitación y humedad por día y hora, para el ticker de meteo. Media
    sobre todas las estaciones porque el mapa solo muestra un valor global,
    no una superficie meteorológica."""
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
    """Construye `meta.json`: todo lo que no cambia con el reloj y que el
    cliente necesita una sola vez — coordenadas y distrito de cada nodo,
    polígonos y centroides de distrito, arcos de importancia, textura del
    grafo, hitos, ejes, parques, y la capa social (perfiles de sensibilidad
    y umbrales OMS/UE)."""
    nodos = {n["id"]: n for n in _GRAFO["nodos"]}
    coords = [[round(nodos[i]["lon"], 5), round(nodos[i]["lat"], 5)] for i in node_ids]
    distr = [nodos[i]["distrito"] for i in node_ids]
    distr_nom = {n["distrito"]: n.get("distrito_nombre") for n in _GRAFO["nodos"]}
    idx = {nid: k for k, nid in enumerate(node_ids)}
    # Las 15 aristas más influyentes del STGNN, como pares de índice de nodo
    # con la importancia normalizada a [0, 1] (el cliente la usa de grosor).
    imp = _GRAFO["importancia_aristas"]
    mx = max(e["importancia"] for e in imp) or 1.0
    arcs = [
        {"s": idx[e["a"]], "t": idx[e["b"]], "w": round(e["importancia"] / mx, 3)}
        for e in imp
        if e["a"] in idx and e["b"] in idx
    ]
    # La capa "textura" es el grafo completo (~8.758 aristas), que se dibuja
    # muy tenue como contexto de fondo; va aparte de los arcos de importancia.
    tex = [[idx[e["a"]], idx[e["b"]]] for e in _GRAFO["aristas"] if e["a"] in idx and e["b"] in idx]
    # Un punto por distrito donde anclar su etiqueta de texto en el mapa.
    centroides = [
        {"nombre": f["properties"]["name"], "pos": _centroide(f["geometry"]["coordinates"][0])}
        for f in _GEOJSON["features"]
    ]
    # Los 14 lugares de referencia que también usa `ruta_saludable` como
    # origen/destino; aquí solo sirven de marcador con etiqueta.
    from viz.rutas import LUGARES

    hitos = [{"nombre": k, "pos": [round(v[1], 5), round(v[0], 5)]} for k, v in LUGARES.items()]
    # Envolvente de todos los nodos, para que la cámara encaje Madrid al abrir.
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    bbox = [[min(lons), min(lats)], [max(lons), max(lats)]]

    # Capa social y de accesibilidad: perfiles de sensibilidad (mismos pesos
    # que `ruta_saludable`), ruido medio por distrito, distancia de cada nodo
    # a la estación de aire más cercana (fiabilidad de la interpolación) y las
    # bandas de calidad del aire OMS/UE.
    from grafo.geo import haversine_m
    from viz.rutas import PERFILES

    df_pa = pd.read_parquet(_PARQUET)
    ruido_distrito = (
        df_pa.dropna(subset=["noise_db"]).groupby("district")["noise_db"].mean().round(1).to_dict()
    )
    est_aire = [(v["lat"], v["lon"]) for v in _GRAFO["estaciones_aire"].values()]
    idw_dist = [
        round(min(haversine_m(nodos[i]["lat"], nodos[i]["lon"], la, lo) for la, lo in est_aire))
        for i in node_ids
    ] if est_aire else [0] * len(node_ids)
    perfiles = {k: {s: v[s] for s in ("traf", "no2", "o3", "noise")} for k, v in PERFILES.items()}
    # Umbrales de NO₂/O₃ (µg/m³) e índice de salud: cada banda es "valor por
    # encima del corte i". Los nombres se muestran tal cual en la leyenda.
    umbrales = {
        "no2": {"cortes": [25, 40, 100, 200],
                "bandas": ["≤ guía OMS 24 h", "≤ límite anual UE", "elevado", "≥ límite horario UE", "muy alto"]},
        "o3":  {"cortes": [100, 120, 180, 240],
                "bandas": ["≤ guía OMS 8 h", "≤ objetivo 8 h UE", "≥ umbral información UE", "≥ umbral alerta UE", "extremo"]},
        "salud": {"cortes": [60, 70, 80, 90], "bandas": ["muy baja", "baja", "media", "buena", "muy buena"]},
    }

    return {
        "generado": pd.Timestamp.utcnow().isoformat(timespec="seconds"),
        "n_nodos": len(node_ids),
        "dias": dias,
        "dow": {d: pd.Timestamp(d).day_name() for d in dias},
        "coords": coords,
        "node_id": node_ids,
        "distrito": distr,
        "distrito_nombre": distr_nom,
        "arcs": arcs,
        "tex": tex,
        "metricas": {k: {"rango": v[1], "label": v[2], "peor": v[3]} for k, v in _METRICAS.items()},
        "distritos_geojson": _GEOJSON,
        "distrito_centroide": centroides,
        "hitos": hitos,
        "bbox": bbox,
        "ejes_geojson": _EJES,
        "parques_geojson": _PARQUES,
        "ruido_distrito": ruido_distrito,
        "idw_dist": idw_dist,
        "perfiles": perfiles,
        "umbrales": umbrales,
    }


def _html() -> str:
    """El HTML final: la plantilla con las URL de los CDN sustituidas.
    Sin E/S ni red — se puede llamar en un test para comprobar el HTML
    generado sin regenerar los JSON."""
    return (
        _TEMPLATE.replace("__DECKGL_CDN__", _DECKGL_CDN)
        .replace("__MAPLIBRE_JS_CDN__", _MAPLIBRE_JS_CDN)
        .replace("__MAPLIBRE_CSS_CDN__", _MAPLIBRE_CSS_CDN)
    )


def _frame_strip_png(df: pd.DataFrame, dia: str) -> Path:
    """Tira de fotogramas (04/08/13/18/22 h) del índice de salud sobre los
    distritos, con la misma estética oscura que la app, para incluir como
    figura estática en la memoria. `matplotlib` se importa aquí porque solo
    hace falta para esto."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    horas = [4, 8, 13, 18, 22]
    g = df[df["day"] == dia]
    _BG = "#0a0e14"
    fig, axes = plt.subplots(1, len(horas), figsize=(3.3 * len(horas), 3.5), constrained_layout=True)
    fig.patch.set_facecolor(_BG)
    polys = [
        [(x, y) for x, y in feat["geometry"]["coordinates"][0]]
        for feat in _GEOJSON["features"]
    ]
    lon0, lon1 = g["lon"].min(), g["lon"].max()
    lat0, lat1 = g["lat"].min(), g["lat"].max()
    for ax, h in zip(axes, horas):
        gh = g[g["hour"] == h].sort_values("health_index", ascending=False)
        ax.set_facecolor(_BG)
        ax.add_collection(PolyCollection(polys, facecolors="none", edgecolors="#2a3442", linewidths=0.6))
        sc = ax.scatter(
            gh["lon"], gh["lat"], c=gh["health_index"], cmap="RdYlGn",
            vmin=58, vmax=94, s=11, linewidths=0, alpha=0.92,
        )
        ax.set_title(f"{h:02d}:00", fontsize=11, color="#c8d2dc", pad=6)
        ax.set_xlim(lon0 - 0.01, lon1 + 0.01)
        ax.set_ylim(lat0 - 0.01, lat1 + 0.01)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_aspect("equal")
        for s in ax.spines.values():
            s.set_visible(False)
    cb = fig.colorbar(sc, ax=axes, shrink=0.62, aspect=28, pad=0.012)
    cb.set_label("índice de salud  (100 = mejor)", color="#c8d2dc", fontsize=10)
    cb.ax.tick_params(colors="#8a97a5", labelsize=9)
    cb.outline.set_visible(False)
    fig.suptitle(
        f"Madrid · índice de salud sobre el grafo · {dia} ({pd.Timestamp(dia).day_name()})",
        fontsize=12.5, color="#e8edf2",
    )
    out = _VIZ / "mapa_frames.png"
    fig.savefig(out, dpi=130, facecolor=_BG)
    plt.close(fig)
    return out


def main() -> int:
    """Regenera todo `viz/mapa/` (los tres JSON + `index.html`), luego
    `rutas.json` vía `viz.rutas` y la figura `mapa_frames.png`. Idempotente
    y sin red."""
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

    # La capa de rutas saludables necesita `networkx`. Si no está instalado
    # (entorno mínimo), se omite `rutas.json` y el mapa carga sin esa capa.
    try:
        from viz import rutas as _rutas

        _rutas.main()
    except Exception as exc:  # noqa: BLE001
        print(f"  (rutas.json omitido: {exc})")

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
<link href="__MAPLIBRE_CSS_CDN__" rel="stylesheet">
<script src="__MAPLIBRE_JS_CDN__"></script>
<style>
  :root { color-scheme: light dark; }
  html,body { margin:0; height:100%; font-family:system-ui,Segoe UI,Roboto,sans-serif; }
  #map { position:absolute; inset:0;
    background:radial-gradient(ellipse 120% 90% at 50% 38%, #0e141c 0%, #070a0e 70%); }
  .panel { position:absolute; background:rgba(20,24,30,.86); color:#e8edf2;
    backdrop-filter:blur(4px); border-radius:10px; padding:10px 12px; font-size:13px; }
  #titulo { left:50%; top:10px; transform:translateX(-50%); padding:6px 16px; font-weight:650;
    letter-spacing:.2px; text-align:center; }
  #titulo small { display:block; font-weight:400; color:#9fb0c0; font-size:11px; margin-top:2px; }
  #controls { left:12px; top:56px; width:272px; max-height:calc(100% - 200px); overflow:auto; }
  #context  { right:12px; top:56px; width:250px; max-height:calc(100% - 200px); overflow:auto; }
  #resumen  { left:12px; right:12px; bottom:12px; padding:8px 12px; display:flex; gap:16px;
    align-items:stretch; font-variant-numeric:tabular-nums; }
  #resumen .blk { display:flex; flex-direction:column; gap:2px; }
  #resumen .blk.grow { flex:1; min-width:0; }
  #resumen svg { display:block; width:100%; }
  #resumen .hd { color:#9fb0c0; font-size:10.5px; text-transform:uppercase; letter-spacing:.4px; }
  details { border:1px solid #2c3644; border-radius:8px; margin:6px 0; padding:2px 8px 8px; }
  details[open] { background:rgba(255,255,255,.02); }
  summary { cursor:pointer; font-weight:600; padding:6px 0; list-style:none; }
  summary::-webkit-details-marker { display:none; }
  summary::before { content:"▸ "; color:#9fb0c0; }
  details[open] > summary::before { content:"▾ "; }
  .row { display:flex; gap:6px; align-items:center; margin:6px 0; flex-wrap:wrap; }
  button, select { background:#2a3340; color:#e8edf2; border:1px solid #3a4756; border-radius:6px;
    padding:4px 9px; cursor:pointer; font-size:12px; }
  button:focus-visible, select:focus-visible, summary:focus-visible, input:focus-visible {
    outline:2px solid #8ab4ff; outline-offset:1px; }
  button.on { background:#3d6ce0; border-color:#3d6ce0; }
  select { flex:1; min-width:0; }
  input[type=range] { flex:1; }
  label.chk { display:flex; gap:6px; align-items:center; font-size:12px; margin:4px 0; cursor:pointer; }
  .leg { height:10px; border-radius:3px; margin-top:6px;
    background:linear-gradient(90deg,#d7191c,#fdae61,#ffffbf,#a6d96a,#1a9641); }
  .leg.rev { background:linear-gradient(90deg,#1a9641,#a6d96a,#ffffbf,#fdae61,#d7191c); }
  .leg.div { background:linear-gradient(90deg,#2c7bb6,#abd9e9,#ffffbf,#fdae61,#d7191c); }
  .muted { color:#9fb0c0; font-size:11px; }
  b.big { font-size:15px; }
  .tabs { display:flex; gap:4px; margin-bottom:8px; }
  .brow { display:flex; align-items:center; gap:6px; margin:3px 0; font-size:11px; }
  .brow span:first-child { width:96px; color:#c8d4df; }
  .brow span:last-child { width:26px; text-align:right; color:#9fb0c0; }
  .deck-tooltip { font-size:12px !important; background:rgba(20,24,30,.92) !important; border-radius:6px !important; }
</style>
</head>
<body>
<div id="map" role="application" aria-label="Mapa animado del grafo de Madrid"></div>

<div class="panel" id="titulo">Madrid · previsión sobre el grafo<small id="titulo-sub">—</small></div>

<div class="panel" id="controls">
  <details open>
    <summary>⏱ Tiempo</summary>
    <div class="row" id="days"></div>
    <div class="row">
      <button id="play" aria-label="Reproducir / pausar">▶︎</button>
      <input type="range" id="hour" min="0" max="23" value="8" aria-label="Hora del día">
      <span id="hlabel" style="width:44px;text-align:right">08:00</span>
    </div>
    <div class="row" aria-label="Horizonte de previsión">
      <button data-h="now" class="hz on">ahora</button>
      <button data-h="h1" class="hz">+1h</button>
      <button data-h="h3" class="hz">+3h</button>
      <button data-h="h6" class="hz">+6h</button>
    </div>
  </details>

  <details open>
    <summary>🎨 Capa de color</summary>
    <div class="row" id="metrics"></div>
    <div class="row" aria-label="Escala de color">
      <span class="muted">escala:</span>
      <button data-e="lineal" class="es on">lineal</button>
      <button data-e="bandas" class="es">bandas OMS·UE</button>
    </div>
    <div class="muted" id="metlabel"></div>
    <div class="leg" id="leg"></div>
    <div class="muted" id="legrange" style="display:flex;justify-content:space-between"></div>
    <div id="leg-bandas" class="muted" style="display:none;margin-top:4px"></div>
    <div class="row"><button id="ghost">modelo vs persistencia (E2)</button></div>
    <div class="muted" style="margin-top:4px">Arcos = 15 conexiones más influyentes del STGNN
      (importancia estática, grosor ∝ importancia, color animado por el tráfico). Clic en un nodo → detalle.</div>
  </details>

  <details>
    <summary>♿ Salud · perfil de sensibilidad</summary>
    <div class="row" id="perfiles"></div>
    <div class="muted" id="mejor-hora" style="margin-top:2px"></div>
    <label class="chk"><input type="checkbox" id="l-idw"> confianza de la interpolación de aire
      (nodos lejos de estación = menos fiables)</label>
    <div class="muted" style="margin-top:6px">Métricas de dosis: media de la exposición prevista de las
      próximas 8 h como % de la guía OMS.</div>
    <div class="muted" style="margin-top:8px;border-top:1px solid #2c3644;padding-top:6px">
      Agregados por zona · datos abiertos, sin información personal · describe el aire y la hora,
      no señala barrios · <b>apoyo a la decisión, no consejo médico</b>.</div>
  </details>

  <details>
    <summary>🧭 Vista</summary>
    <div class="row">
      <button id="v2d" class="on">2D</button><button id="v3d">3D</button>
      <button id="fit">encajar a Madrid</button>
      <button id="clean">vista limpia</button>
    </div>
    <div class="row" aria-label="Representación de los nodos">
      <span class="muted">nodos:</span>
      <button data-r="puntos" class="rp on">puntos</button>
      <button data-r="auto" class="rp">auto</button>
      <button data-r="barras" class="rp">barras (3D)</button>
    </div>
    <div class="row" aria-label="Basemap vectorial (opcional)">
      <span class="muted">basemap:</span>
      <select id="basemap" aria-label="Basemap vectorial">
        <option value="ninguno">ninguno</option>
        <option value="positron">Carto Positron (claro)</option>
        <option value="dark-matter">Carto Dark Matter (oscuro)</option>
        <option value="voyager">Carto Voyager (calles)</option>
      </select>
    </div>
    <label class="chk"><input type="checkbox" id="l-distr" checked> nombres de distrito</label>
    <label class="chk"><input type="checkbox" id="l-hitos" checked> hitos (Sol, Atocha…)</label>
    <label class="chk"><input type="checkbox" id="l-ejes"> ejes (M-30, Castellana… · contexto)</label>
    <label class="chk"><input type="checkbox" id="l-parques"> parques grandes</label>
    <label class="chk"><input type="checkbox" id="l-tex"> textura del grafo (aristas)</label>
  </details>

  <details>
    <summary>🚶 Ruta saludable (E3)</summary>
    <div class="row">
      <select id="r-od" aria-label="Origen y destino"><option value="-1">— sin ruta —</option></select>
    </div>
    <div class="row"><select id="r-perfil" aria-label="Perfil"></select></div>
    <div class="muted" id="routeinfo" style="margin-top:2px"></div>
  </details>
</div>

<div class="panel" id="context">
  <div class="tabs">
    <button id="tab-d" class="tab on">distritos</button>
    <button id="tab-a" class="tab">arista/nodo</button>
  </div>
  <div id="pane-d">
    <div class="muted">índice de salud medio por distrito · <span id="pd-hour">—</span></div>
    <div id="pulse" style="margin-top:6px"></div>
  </div>
  <div id="pane-a" style="display:none">
    <div class="muted">nodo</div><b class="big" id="ea-id">—</b>
    <div class="muted" id="ea-dist"></div>
    <div class="muted" style="margin-top:8px">tráfico obs vs previsto (h1) · 24 h</div>
    <svg id="ea-spark-t" width="222" height="46"></svg>
    <div class="muted" style="margin-top:4px">NO₂ / O₃ · 24 h</div>
    <svg id="ea-spark-a" width="222" height="46"></svg>
    <div class="muted" style="margin-top:8px" id="ea-imp"></div>
  </div>
  <div class="muted" style="margin-top:10px">skill STGNN vs persistencia (h1): <b id="ctx-skill">—</b></div>
</div>

<div class="panel" id="resumen">
  <div class="blk grow">
    <span class="hd" id="rs-ct-hd">media ciudad · 24 h</span>
    <svg id="rs-city" viewBox="0 0 320 60" preserveAspectRatio="none" height="56"></svg>
    <span class="muted" id="rs-city-txt">—</span>
  </div>
  <div class="blk grow">
    <span class="hd">salud por distrito · ahora</span>
    <svg id="rs-distr" viewBox="0 0 320 60" preserveAspectRatio="none" height="56"></svg>
    <span class="muted" id="rs-distr-txt">—</span>
  </div>
  <div class="blk" style="min-width:190px">
    <span class="hd">meteo · skill</span>
    <div id="wx" style="margin-top:4px">meteo —</div>
    <div class="muted" style="margin-top:6px">skill STGNN vs persistencia (h1): <b id="rs-skill">—</b></div>
  </div>
</div>

<script>
// Interfaz del mapa. `META` (estático), `DATA` (valores por día/hora/nodo) y
// `WX` (meteo) se cargan de tres JSON al final del fichero; `state` guarda lo
// que el usuario elige con los controles; `render()` reconstruye las capas de
// deck.gl y los paneles a partir de `state` cada vez que algo cambia.
const {DeckGL, ScatterplotLayer, ColumnLayer, LineLayer, ArcLayer, GeoJsonLayer, PathLayer, TextLayer, WebMercatorViewport} = deck;
let META, DATA, WX, RUTAS, dgl, selNode = null;
let state = {
  day:null, hour:8, metric:"salud", hz:"now", playing:false, ghost:false, tab:"d", route:-1,
  view:{longitude:-3.70, latitude:40.43, zoom:10.6, pitch:0, bearing:0},
  layers:{distr:true, hitos:true, ejes:false, parques:false, tex:false, idw:false},
  clean:false, repr:"puntos", escala:"lineal", perfil:"general", basemap:"ninguno",
};

// Basemap vectorial opcional. "ninguno" es un estilo vacío (transparente, el
// aspecto plano por defecto); el resto son estilos Carto que no necesitan
// token. Solo se descargan tiles si se elige uno distinto de "ninguno".
const HAS_MAPLIBRE = typeof maplibregl !== "undefined";
const BASEMAP_VACIO = {version:8, sources:{}, layers:[]};
const BASEMAPS = {
  ninguno: BASEMAP_VACIO,
  positron: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  "dark-matter": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  voyager: "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
};

const clamp01 = x => Math.max(0, Math.min(1, x));
const scale = (v, lo, hi) => clamp01((v-lo)/(hi-lo));
const RAMP = [[215,25,28],[253,174,97],[255,255,191],[166,217,106],[26,150,65]];
const DIV  = [[44,123,182],[171,217,233],[255,255,191],[253,174,97],[215,25,28]];
function lerp(stops,t){ const x=t*(stops.length-1), i=Math.floor(x), f=x-i;
  const a=stops[i], b=stops[Math.min(i+1,stops.length-1)];
  return [0,1,2].map(k=>Math.round(a[k]+(b[k]-a[k])*f)); }
const ramp = t => lerp(RAMP, clamp01(t));
const divg = t => lerp(DIV, clamp01(t));

// Paleta de las bandas OMS/UE, en 5 pasos y distinguible en deuteranopía.
const BANDAS_PAL = [[44,123,182],[145,191,219],[255,255,191],[252,141,89],[215,25,28]];
// Métricas que no vienen en los datos: se calculan en el navegador a partir
// del perfil de sensibilidad elegido. Misma forma que `META.metricas`.
const MET_EXTRA = {
  salud_perfil: {rango:[40,95], label:"Índice de salud según el perfil elegido", peor:-1, banda:"salud"},
  dosis_no2:    {rango:[0,120], label:"Dosis NO₂ próximas 8 h (% de la guía OMS 24 h)", peor:1},
  dosis_o3:     {rango:[0,150], label:"Dosis O₃ próximas 8 h (% de la guía OMS 8 h)", peor:1},
};
const metDef = m => META.metricas[m] || MET_EXTRA[m];
const _n = (s,v) => s==="traf" ? clamp01(v/300) : s==="no2" ? clamp01(v/200)
                  : s==="o3" ? clamp01(v/180) : clamp01((v-45)/30);

function trafArr(hz){ return DATA[state.day]["traf_"+hz][state.hour]; }
function _dosis(campo, guia, hora){
  const h0 = hora==null ? state.hour : hora;
  const md = DATA[state.day][campo];
  return META.coords.map((_,i)=>{
    let s=0, n=0;
    for(let h=h0; h<Math.min(24,h0+8); h++){ const v=md[h][i]; if(v>=0){ s+=v; n++; } }
    return n ? s/n/guia*100 : -1;
  });
}
function _saludPerfilHora(h){
  const w = META.perfiles[state.perfil] || META.perfiles.general;
  const sw = w.traf+w.no2+w.o3+w.noise;
  const md = DATA[state.day];
  return META.coords.map((_,i)=>{
    const traf=md.trafico[h][i], no2=md.no2[h][i], o3=md.o3[h][i];
    const db = META.ruido_distrito[META.distrito[i]];
    if(no2<0||o3<0) return -1;
    const carga = (w.traf*_n("traf", traf<0?0:traf) + w.no2*_n("no2",no2) + w.o3*_n("o3",o3)
                 + w.noise*_n("noise", db==null?55:db)) / sw;
    return Math.round(100*(1-carga));
  });
}
const _saludPerfil = () => _saludPerfilHora(state.hour);
// barrido 24 h de salud media por perfil; memoizado por (día, perfil) porque se
// llama en cada render (playback, pan/zoom) y recorre 24 x 1798 nodos
const _mhpCache = {};
function mejorHoraPerfil(){
  const key = state.day + "|" + state.perfil;
  if(_mhpCache[key]) return _mhpCache[key];
  let best=-1, bh=0, worst=101, wh=0;
  for(let h=0;h<24;h++){ const a=_saludPerfilHora(h); let s=0,n=0;
    for(const v of a){ if(v>=0){ s+=v; n++; } }
    const m = n?s/n:0;
    if(m>best){ best=m; bh=h; }
    if(m<worst){ worst=m; wh=h; } }
  return (_mhpCache[key] = {hora:bh, salud:best, peor_hora:wh});
}
function metricArr(){
  if(state.metric==="trafico") return trafArr(state.hz);
  if(state.metric==="salud_perfil") return _saludPerfil();
  if(state.metric==="dosis_no2") return _dosis("no2", 25);
  if(state.metric==="dosis_o3")  return _dosis("o3", 100);
  return DATA[state.day][state.metric][state.hour];
}
function _banda(m, v){
  const key = (metDef(m).banda) || m;
  const u = META.umbrales[key];
  if(!u) return null;
  let b = 0; for(const c of u.cortes){ if(v > c) b++; }
  return {i:b, nombre:u.bandas[b]};
}
function nodeColor(i){
  if(state.ghost){
    const f = DATA[state.day]["traf_h1"][state.hour][i];
    const p = DATA[state.day]["traf_now"][state.hour][i];
    if(f<0||p<0) return [70,80,95,28];
    return divg(0.5 + (f-p)/200).concat(235);
  }
  const v = metricArr()[i];
  if(v<0) return [70,80,95,28];
  if(state.escala==="bandas" && _banda(state.metric, v)){
    const {i:bi} = _banda(state.metric, v);
    const peor = metDef(state.metric).peor>0;
    return BANDAS_PAL[peor ? bi : BANDAS_PAL.length-1-bi].concat(240);
  }
  const [lo,hi] = metDef(state.metric).rango;
  let t = scale(state.metric==="trafico" ? v/100 : v, lo, hi);
  if(metDef(state.metric).peor>0) t = 1-t;
  return ramp(t).concat(240);
}
const arcCol = a => a>0 ? ramp(1-scale(a/100,0,2.5)).concat(220) : [110,130,235,90];
// radio de nodo dependiente del zoom: puntos nítidos de lejos, no una mancha
function nodeRmin(){ const z = state.view.zoom;
  return z < 10.6 ? 1.6 : z < 11.6 ? 2.4 : z < 12.6 ? 3.2 : 4.2; }
// "gravedad" 0..100 -> altura de barra: sube donde las condiciones son PEORES
function nodeElev(i){
  if(state.ghost){
    const f = DATA[state.day]["traf_h1"][state.hour][i], p = DATA[state.day]["traf_now"][state.hour][i];
    return (f<0||p<0) ? 0 : Math.min(100, Math.abs(f-p)*0.7);
  }
  const v = metricArr()[i];
  if(v<0) return 0;
  const md = metDef(state.metric), [lo,hi] = md.rango;
  const t = scale(state.metric==="trafico" ? v/100 : v, lo, hi);
  return (md.peor>0 ? t : 1-t) * 100;   // salud: alto = salud baja (problema)
}
const usaBarras = () => state.repr==="barras" || (state.repr==="auto" && state.view.pitch > 5);

function layers(){
  const idxs = META.coords.map((_,i)=>i);
  const trafNow = trafArr(state.hz);
  const L = [
    new GeoJsonLayer({id:"distr", data:META.distritos_geojson, stroked:true, filled:true,
      getFillColor:[255,255,255,3], getLineColor:[150,170,195,34], lineWidthMinPixels:0.7}),
  ];
  if(state.layers.ejes)
    L.push(new GeoJsonLayer({id:"ejes", data:META.ejes_geojson, stroked:true, filled:false,
      getLineColor:[255,214,140,55], lineWidthMinPixels:1.5, getLineWidth:2}));
  if(state.layers.tex && !state.clean)
    L.push(new LineLayer({id:"tex", data:META.tex, getSourcePosition:d=>META.coords[d[0]],
      getTargetPosition:d=>META.coords[d[1]], getColor:[150,170,200,10], getWidth:1}));
  if(!state.clean)
    L.push(new ArcLayer({id:"imp", data:META.arcs,
      getSourcePosition:d=>META.coords[d.s], getTargetPosition:d=>META.coords[d.t],
      getSourceColor:d=>arcCol(trafNow[d.s]), getTargetColor:d=>arcCol(trafNow[d.t]),
      getWidth:d=>0.8+3*d.w, getHeight:0.16,
      updateTriggers:{getSourceColor:[state.day,state.hour,state.hz], getTargetColor:[state.day,state.hour,state.hz]}}));
  const onNode = info => { if(info.index!=null){ selNode=info.index; state.tab="a"; syncTabs(); render(); } };
  // incluye perfil y escala: con la métrica "salud (perfil)" fija, cambiar de
  // perfil o de escala (lineal<->bandas) recolorea los nodos aunque metric no cambie
  const trig = [state.day,state.hour,state.metric,state.hz,state.ghost,state.perfil,state.escala];
  if(usaBarras())
    L.push(new ColumnLayer({id:"nodes", data:idxs, pickable:true, diskResolution:6,
      radius:40, radiusUnits:"meters", extruded:true, elevationScale:24,
      getPosition:i=>META.coords[i], getElevation:nodeElev, getFillColor:nodeColor,
      material:{ambient:0.6, diffuse:0.5, shininess:20},
      updateTriggers:{getFillColor:trig, getElevation:trig}, onClick:onNode}));
  else
    L.push(new ScatterplotLayer({id:"nodes", data:idxs, pickable:true,
      radiusMinPixels:nodeRmin(), radiusMaxPixels:8, getPosition:i=>META.coords[i], getRadius:70,
      stroked:true, getLineColor:[8,11,16,110], lineWidthMinPixels:0.4, getFillColor:nodeColor,
      updateTriggers:{getFillColor:trig, radiusMinPixels:[state.view.zoom]}, onClick:onNode}));
  if(state.layers.idw && META.idw_dist)
    L.push(new ScatterplotLayer({id:"idw", data:META.coords.map((_,i)=>i).filter(i=>META.idw_dist[i]>1800),
      getPosition:i=>META.coords[i], getRadius:i=>Math.min(3, META.idw_dist[i]/2500),
      radiusUnits:"pixels", radiusMinPixels:2, radiusMaxPixels:5,
      stroked:true, filled:false, getLineColor:[255,190,90,150], lineWidthMinPixels:1}));
  if(selNode!=null)
    L.push(new ScatterplotLayer({id:"sel", data:[selNode], getPosition:i=>META.coords[i],
      getRadius:nodeRmin()*3, radiusUnits:"pixels", stroked:true, filled:false,
      getLineColor:[255,255,255,235], lineWidthMinPixels:2}));
  if(state.layers.parques){
    L.push(new ScatterplotLayer({id:"pq-dot", data:META.parques_geojson.features,
      getPosition:f=>f.geometry.coordinates, getRadius:5, radiusMinPixels:4, radiusMaxPixels:9,
      getFillColor:[80,190,120,220], stroked:true, getLineColor:[10,20,15,180], lineWidthMinPixels:1}));
    L.push(new TextLayer({id:"pq-tx", data:META.parques_geojson.features,
      getPosition:f=>f.geometry.coordinates, getText:f=>f.properties.nombre,
      getSize:11, getColor:[190,240,205,235], getPixelOffset:[0,-12],
      fontFamily:"system-ui", characterSet:"auto", fontSettings:{sdf:true}, outlineWidth:3, outlineColor:[0,0,0,220],
      getTextAnchor:"middle", getAlignmentBaseline:"bottom"}));
  }
  if(state.layers.distr && !state.clean)
    L.push(new TextLayer({id:"d-tx", data:META.distrito_centroide,
      getPosition:d=>d.pos, getText:d=>d.nombre.toUpperCase(), getSize:10,
      getColor:[200,212,226, state.view.zoom < 10.8 ? 55 : 100],
      fontFamily:"system-ui", fontWeight:600, characterSet:"auto", fontSettings:{sdf:true},
      outlineWidth:2.5, outlineColor:[8,11,16,210], getTextAnchor:"middle",
      updateTriggers:{getColor:[state.view.zoom]}}));
  if(state.layers.hitos && !state.clean){
    L.push(new ScatterplotLayer({id:"h-dot", data:META.hitos, getPosition:d=>d.pos,
      getRadius:4, radiusMinPixels:3, radiusMaxPixels:7, getFillColor:[255,255,255,235],
      stroked:true, getLineColor:[40,50,60,220], lineWidthMinPixels:1}));
    L.push(new TextLayer({id:"h-tx", data:META.hitos, getPosition:d=>d.pos, getText:d=>d.nombre,
      getSize:11, getColor:[235,240,246,235], getPixelOffset:[0,10], fontFamily:"system-ui",
      characterSet:"auto", fontSettings:{sdf:true}, outlineWidth:3, outlineColor:[0,0,0,220],
      getTextAnchor:"middle", getAlignmentBaseline:"top"}));
  }
  L.push(...routeLayers());
  return L;
}

function routeLayers(){
  if(state.route<0 || !RUTAS) return [];
  const R = RUTAS.rutas[state.route], r = R.por_hora[state.hour];
  const ends = [{pos:r.sana[0], t:R.origen},{pos:r.sana[r.sana.length-1], t:R.destino}];
  return [
    new PathLayer({id:"r-fast", data:[r.rapida], getPath:d=>d, widthMinPixels:3,
      getColor:[150,160,170,200], getWidth:4, updateTriggers:{data:[state.route,state.hour]}}),
    new PathLayer({id:"r-safe", data:[r.sana], getPath:d=>d, widthMinPixels:4,
      getColor:[40,200,120,235], getWidth:6, updateTriggers:{data:[state.route,state.hour]}}),
    new ScatterplotLayer({id:"r-end", data:ends, getPosition:d=>d.pos, getRadius:6,
      radiusMinPixels:5, getFillColor:[40,200,120,255], stroked:true, getLineColor:[0,0,0,220], lineWidthMinPixels:1}),
    new TextLayer({id:"r-lbl", data:ends, getPosition:d=>d.pos, getText:d=>d.t, getSize:12,
      getColor:[210,255,225,255], getPixelOffset:[0,-14], fontFamily:"system-ui",
      characterSet:"auto", fontSettings:{sdf:true}, outlineWidth:3, outlineColor:[0,0,0,220],
      getTextAnchor:"middle", getAlignmentBaseline:"bottom"}),
  ];
}

function skill(){
  const md = DATA[state.day], f=md.traf_h1[state.hour], p=md.traf_now[state.hour], a=md.traf_h1_act[state.hour];
  let es=0, ep=0, n=0;
  for(let i=0;i<f.length;i++){ if(f[i]<0||p[i]<0||a[i]<0) continue;
    es+=Math.abs(f[i]-a[i]); ep+=Math.abs(p[i]-a[i]); n++; }
  return n && ep ? 1 - es/ep : NaN;
}

function pulse(){
  const vals = DATA[state.day].salud[state.hour];
  const acc = {};
  META.distrito.forEach((d,i)=>{ if(vals[i]<0) return;
    (acc[d]=acc[d]||[0,0]); acc[d][0]+=vals[i]; acc[d][1]++; });
  const rows = Object.entries(acc).map(([d,s])=>[d, s[0]/s[1]]).sort((a,b)=>a[1]-b[1]);
  const name = id => (META.distrito_nombre && META.distrito_nombre[id]) || id;
  document.getElementById("pd-hour").textContent = String(state.hour).padStart(2,"0")+":00";
  document.getElementById("pulse").innerHTML = rows.map(([d,v])=>{
    const w = Math.round(scale(v,55,96)*120);
    return `<div class="brow"><span>${name(d)}</span>`
      +`<span style="height:14px;border-radius:3px;width:${w}px;background:rgb(${ramp(scale(v,55,96)).join(",")})"></span>`
      +`<span>${v.toFixed(0)}</span></div>`;
  }).join("");
}

function spark(svg, series, colors, lo, hi){
  const W=222, H=46, n=24;
  const x = i => 3 + i*(W-6)/(n-1);
  const y = v => (v==null||v<0) ? null : H-3 - clamp01((v-lo)/(hi-lo))*(H-6);
  const path = s => { let d="", pen=false;
    s.forEach((v,i)=>{ const yy=y(v); if(yy==null){pen=false;return;}
      d += (pen?"L":"M")+x(i).toFixed(1)+" "+yy.toFixed(1)+" "; pen=true; });
    return d; };
  svg.innerHTML = series.map((s,k)=>`<path d="${path(s)}" fill="none" stroke="${colors[k]}" stroke-width="1.4"/>`).join("")
    + `<line x1="${x(state.hour)}" y1="0" x2="${x(state.hour)}" y2="${H}" stroke="#89a" stroke-width="1" stroke-dasharray="2 2"/>`;
}

function edgePane(){
  if(selNode==null) return;
  const md = DATA[state.day], id = META.node_id ? META.node_id[selNode] : selNode;
  document.getElementById("ea-id").textContent = "#"+id;
  const dn = META.distrito_nombre ? META.distrito_nombre[META.distrito[selNode]] : META.distrito[selNode];
  document.getElementById("ea-dist").textContent = "distrito "+(dn||META.distrito[selNode]);
  const obs = Array.from({length:24}, (_,h)=>md.traf_now[h][selNode]);
  const h1  = Array.from({length:24}, (_,h)=>md.traf_h1[h][selNode]);
  spark(document.getElementById("ea-spark-t"), [obs,h1], ["#7fd1ff","#ffd27f"], 0, 300);
  const no2 = Array.from({length:24}, (_,h)=>md.no2[h][selNode]);
  const o3  = Array.from({length:24}, (_,h)=>md.o3[h][selNode]);
  spark(document.getElementById("ea-spark-a"), [no2,o3], ["#c58bff","#9adf9a"], 0, 140);
  const tocan = META.arcs.filter(a=>a.s===selNode||a.t===selNode).map(a=> (a.s===selNode?a.t:a.s)+" (w="+a.w+")");
  document.getElementById("ea-imp").textContent = tocan.length
    ? "aristas influyentes del STGNN que tocan este nodo: "+tocan.join(", ")
    : "este nodo no está en el top-15 de importancia_aristas.";
}

function syncTabs(){
  document.getElementById("pane-d").style.display = state.tab==="d" ? "" : "none";
  document.getElementById("pane-a").style.display = state.tab==="a" ? "" : "none";
  document.getElementById("tab-d").classList.toggle("on", state.tab==="d");
  document.getElementById("tab-a").classList.toggle("on", state.tab==="a");
}

function tooltip({object, layer}){
  if(!object) return null;
  if(layer.id==="nodes"){
    const i=object, md=DATA[state.day];
    const dn = META.distrito_nombre[META.distrito[i]] || META.distrito[i];
    return {text:`#${META.node_id[i]} · ${dn}\nsalud ${md.salud[state.hour][i]} · NO₂ ${md.no2[state.hour][i]} · O₃ ${md.o3[state.hour][i]}`};
  }
  if(layer.id==="d-tx") return {text:object.nombre};
  if(layer.id==="h-dot"||layer.id==="h-tx") return {text:object.nombre};
  if(layer.id==="pq-dot"||layer.id==="pq-tx") return {text:object.properties.nombre+" · "+(object.properties.distrito||"")};
  return null;
}

function render(){
  dgl.setProps({layers: layers(), viewState: state.view});
  const md = metDef(state.metric);
  const bandas = state.escala==="bandas" && !state.ghost && (META.umbrales[md.banda||state.metric]);
  document.getElementById("metlabel").textContent = state.ghost
    ? "E2 · divergencia STGNN(h1) − persistencia (azul = STGNN menor, rojo = mayor)"
    : md.label + (state.metric==="salud_perfil" ? ` · perfil: ${state.perfil}` : "");
  const leg = document.getElementById("leg");
  leg.style.display = bandas ? "none" : "block";
  leg.className = "leg" + (state.ghost ? " div" : (md.peor>0 ? "" : " rev"));
  document.getElementById("legrange").style.display = bandas ? "none" : "flex";
  document.getElementById("legrange").innerHTML = state.ghost
    ? "<span>−</span><span>+</span>"
    : `<span>${md.rango[0]}</span><span>${md.rango[1]}</span>`;
  const lb = document.getElementById("leg-bandas");
  if(bandas){ const u = META.umbrales[md.banda||state.metric];
    lb.style.display = "block";
    lb.innerHTML = u.bandas.map((nm,k)=>{
      const c = md.peor>0 ? BANDAS_PAL[k] : BANDAS_PAL[BANDAS_PAL.length-1-k];
      return `<span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:rgb(${c.join(",")});margin-right:4px"></span>${nm}`;
    }).join("<br>");
  } else lb.style.display = "none";
  const hh = String(state.hour).padStart(2,"0")+":00";
  document.getElementById("hlabel").textContent = hh;
  document.getElementById("titulo-sub").textContent =
    `${state.day} (${(META.dow[state.day]||"")}) · ${hh} · ${META.n_nodos} nodos`;
  const w = (WX[state.day]||{})[state.hour];
  document.getElementById("wx").innerHTML = w
    ? `${hh} · ${w.temp_c}°C · viento ${w.wind_ms} m/s<br>lluvia ${w.precip} l/m² · HR ${w.humidity}%`
    : "meteo —";
  const mh = mejorHoraPerfil();
  document.getElementById("mejor-hora").innerHTML =
    `Mejor hora hoy para <b>${state.perfil}</b>: <b>${String(mh.hora).padStart(2,"0")}:00</b> `
    + `(salud media ${mh.salud.toFixed(0)}) · peor: ${String(mh.peor_hora).padStart(2,"0")}:00`;
  const s = skill(), sTxt = isNaN(s) ? "—" : s.toFixed(2);
  const cs = document.getElementById("ctx-skill"); if(cs) cs.textContent = sTxt;
  document.getElementById("rs-skill").textContent = sTxt;
  routeInfo();
  resumen();
  if(state.tab==="d") pulse(); else edgePane();
}

// --- Panel de resumen inferior (media de ciudad + desglose por distrito) ---
function _mediaCiudad(dia, metric, hora){
  // Las métricas virtuales (salud por perfil, dosis) no están en DATA[dia];
  // hay que reproducir aquí el mismo cálculo que hace `metricArr`.
  let arr;
  if(metric==="trafico")           arr = DATA[dia]["traf_"+state.hz][hora];
  else if(metric==="salud_perfil") arr = _saludPerfilHora(hora);
  else if(metric==="dosis_no2")    arr = _dosis("no2", 25, hora);
  else if(metric==="dosis_o3")     arr = _dosis("o3", 100, hora);
  else                             arr = DATA[dia][metric][hora];
  let s=0, n=0; for(const v of arr){ if(v>=0){ s+=(metric==="trafico"?v/100:v); n++; } }
  return n ? s/n : null;
}
function resumen(){
  const dia = state.day, m = state.metric, md = metDef(m);
  // 1) media ciudad 24 h
  const serie = Array.from({length:24}, (_,h)=>_mediaCiudad(dia, m, h));
  const vals = serie.filter(v=>v!=null);
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi-lo)*0.12 || 1;
  const W=320, H=60;
  const x = h => 4 + h*(W-8)/23;
  const y = v => v==null ? null : H-4 - (v-lo+pad)/((hi-lo)+2*pad)*(H-8);
  let area="M"+x(0)+" "+H, line="";
  serie.forEach((v,h)=>{ const yy=y(v); if(yy==null) return;
    area += " L"+x(h).toFixed(1)+" "+yy.toFixed(1); line += (line?"L":"M")+x(h).toFixed(1)+" "+yy.toFixed(1)+" "; });
  area += " L"+x(23)+" "+H+" Z";
  const col = md.peor>0 ? "#e6704b" : "#4bbf73";
  document.getElementById("rs-city").innerHTML =
    `<path d="${area}" fill="${col}22"/><path d="${line}" fill="none" stroke="${col}" stroke-width="1.6"/>`
    + `<line x1="${x(state.hour)}" y1="0" x2="${x(state.hour)}" y2="${H}" stroke="#89a" stroke-dasharray="2 2"/>`;
  const now=serie[state.hour], iMin=serie.indexOf(lo), iMax=serie.indexOf(hi);
  const _ETR = {salud_perfil:"salud (perfil "+state.perfil+")", dosis_no2:"dosis NO₂", dosis_o3:"dosis O₃"};
  document.getElementById("rs-ct-hd").textContent = `media ciudad · ${_ETR[m]||m} · 24 h`;
  document.getElementById("rs-city-txt").textContent =
    `ahora ${now==null?"—":now.toFixed(1)} · mín ${lo.toFixed(1)} @${String(iMin).padStart(2,"0")}h · máx ${hi.toFixed(1)} @${String(iMax).padStart(2,"0")}h`;
  // 2) por distrito ahora (mismo criterio que el pulso, compacto)
  const svals = DATA[dia].salud[state.hour], acc={};
  META.distrito.forEach((d,i)=>{ if(svals[i]<0) return; (acc[d]=acc[d]||[0,0]); acc[d][0]+=svals[i]; acc[d][1]++; });
  const rows = Object.entries(acc).map(([d,s])=>[d,s[0]/s[1]]).sort((a,b)=>a[1]-b[1]);
  const bw = (W-8)/rows.length;
  document.getElementById("rs-distr").innerHTML = rows.map(([d,v],k)=>{
    const hgt = (H-8)*scale(v,55,96), c = ramp(scale(v,55,96));
    return `<rect x="${(4+k*bw).toFixed(1)}" y="${(H-4-hgt).toFixed(1)}" width="${(bw-1).toFixed(1)}" height="${hgt.toFixed(1)}" fill="rgb(${c.join(",")})"><title>${(META.distrito_nombre[d]||d)}: ${v.toFixed(0)}</title></rect>`;
  }).join("");
  document.getElementById("rs-distr-txt").textContent =
    `peor: ${META.distrito_nombre[rows[0][0]]||rows[0][0]} ${rows[0][1].toFixed(0)} · mejor: ${META.distrito_nombre[rows[rows.length-1][0]]||rows[rows.length-1][0]} ${rows[rows.length-1][1].toFixed(0)}`;
}

function routeInfo(){
  const el = document.getElementById("routeinfo");
  if(state.route<0 || !RUTAS){ el.textContent = "elige origen·destino y perfil"; return; }
  const R = RUTAS.rutas[state.route], r = R.por_hora[state.hour];
  const c = r.cambio_por_senal_pct || {};
  const sig = k => (c[k] >= 0 ? "−" : "+") + Math.abs(c[k]) + "%";
  el.innerHTML = `<b>verde</b> = saludable · <b>gris</b> = rápida<br>`
    + `+${r.delta_dist_pct}% distancia · <b>−${r.reduccion_exposicion_pct}%</b> exposición ponderada<br>`
    + `por señal: tráf ${sig("traf")} · NO₂ ${sig("no2")} · O₃ ${sig("o3")} · ruido ${sig("noise")}<br>`
    + `mejor salida: ${R.mejor_hora}:00`;
}

function fitBounds(){
  const {width, height} = dgl.deck || {width:innerWidth, height:innerHeight};
  const vp = new WebMercatorViewport({width:innerWidth, height:innerHeight});
  const {longitude, latitude, zoom} = vp.fitBounds(META.bbox, {padding:60});
  state.view = {...state.view, longitude, latitude, zoom};
  render();
}

function mkControls(){
  const dd = document.getElementById("days");
  META.dias.forEach((d,k)=>{ const b=document.createElement("button");
    b.textContent = d.slice(5)+" ·"+(META.dow[d]||"").slice(0,3); b.className = k===0?"day on":"day";
    b.onclick=()=>{ state.day=d; document.querySelectorAll(".day").forEach(x=>x.classList.remove("on"));
      b.classList.add("on"); render(); }; dd.appendChild(b); });

  const mm = document.getElementById("metrics");
  const METS = [...Object.keys(META.metricas), "salud_perfil", "dosis_no2", "dosis_o3"];
  const ET = {salud_perfil:"salud (perfil)", dosis_no2:"dosis NO₂", dosis_o3:"dosis O₃"};
  METS.forEach((m,k)=>{ const b=document.createElement("button");
    b.textContent = ET[m] || m; b.className = k===0?"met on":"met"; b.dataset.m = m;
    b.onclick=()=>{ state.metric=m; state.ghost=false; document.getElementById("ghost").classList.remove("on");
      document.querySelectorAll(".met").forEach(x=>x.classList.remove("on")); b.classList.add("on"); render(); };
    mm.appendChild(b); });

  document.querySelectorAll(".es").forEach(b=>b.onclick=()=>{ state.escala=b.dataset.e;
    document.querySelectorAll(".es").forEach(x=>x.classList.remove("on")); b.classList.add("on"); render(); });

  const pp = document.getElementById("perfiles");
  Object.keys(META.perfiles).forEach(p=>{ const b=document.createElement("button");
    b.textContent = p; b.className = p==="general" ? "pf on" : "pf"; b.dataset.p = p;
    b.onclick=()=>{ state.perfil=p; state.metric="salud_perfil";
      document.querySelectorAll(".pf").forEach(x=>x.classList.remove("on")); b.classList.add("on");
      document.querySelectorAll(".met").forEach(x=>x.classList.toggle("on", x.dataset.m==="salud_perfil"));
      render(); };
    pp.appendChild(b); });
  document.getElementById("l-idw").onchange=e=>{ state.layers.idw=e.target.checked; render(); };

  document.querySelectorAll(".hz").forEach(b=>b.onclick=()=>{ state.hz=b.dataset.h;
    document.querySelectorAll(".hz").forEach(x=>x.classList.remove("on")); b.classList.add("on"); render(); });
  document.getElementById("ghost").onclick=e=>{ state.ghost=!state.ghost;
    e.target.classList.toggle("on", state.ghost); render(); };

  const hr=document.getElementById("hour");
  hr.oninput=()=>{ state.hour=+hr.value; render(); };
  const pl=document.getElementById("play");
  pl.onclick=()=>{ state.playing=!state.playing; pl.textContent=state.playing?"❚❚":"▶︎"; if(state.playing) tick(); };

  document.getElementById("tab-d").onclick=()=>{ state.tab="d"; syncTabs(); render(); };
  document.getElementById("tab-a").onclick=()=>{ state.tab="a"; syncTabs(); render(); };

  document.querySelectorAll(".rp").forEach(b=>b.onclick=()=>{ state.repr=b.dataset.r;
    document.querySelectorAll(".rp").forEach(x=>x.classList.remove("on")); b.classList.add("on"); render(); });
  document.getElementById("v2d").onclick=()=>setPitch(0);
  document.getElementById("v3d").onclick=()=>setPitch(40);
  document.getElementById("fit").onclick=fitBounds;
  document.getElementById("clean").onclick=e=>{
    state.clean=!state.clean;
    e.target.classList.toggle("on", state.clean);
    document.getElementById("controls").style.opacity = state.clean ? ".22" : "1";
    document.getElementById("context").style.display = state.clean ? "none" : "";
    document.getElementById("resumen").style.display = state.clean ? "none" : "flex";
    render();
  };
  const setChk = (id,key)=>{ const el=document.getElementById(id);
    el.onchange=()=>{ state.layers[key]=el.checked; render(); }; };
  setChk("l-distr","distr"); setChk("l-hitos","hitos"); setChk("l-ejes","ejes");
  setChk("l-parques","parques"); setChk("l-tex","tex");

  const bmSel = document.getElementById("basemap");
  if(!HAS_MAPLIBRE){
    bmSel.disabled = true;
    bmSel.title = "maplibre-gl no se pudo cargar; el mapa sigue funcionando sin basemap";
  } else {
    bmSel.value = state.basemap;
    bmSel.onchange = ()=>{ state.basemap = bmSel.value;
      dgl.setProps({mapStyle: BASEMAPS[state.basemap] || BASEMAP_VACIO}); };
  }

  // ruta: 2 desplegables (origen·destino  ×  perfil)
  if(RUTAS && RUTAS.rutas.length){
    const ods = [...new Set(RUTAS.rutas.map(r=>r.origen+" → "+r.destino))];
    const perfiles = [...new Set(RUTAS.rutas.map(r=>r.perfil))];
    const odSel = document.getElementById("r-od"), pSel = document.getElementById("r-perfil");
    ods.forEach((od,i)=>odSel.add(new Option(od, i)));
    perfiles.forEach(p=>pSel.add(new Option(p, p)));
    const apply=()=>{
      const odi = +odSel.value;
      if(odi<0){ state.route=-1; render(); return; }
      const [o,d] = ods[odi].split(" → ");
      const k = RUTAS.rutas.findIndex(r=>r.origen===o && r.destino===d && r.perfil===pSel.value);
      state.route = k; render();
    };
    odSel.onchange = apply; pSel.onchange = apply;
  } else {
    document.getElementById("r-od").disabled = true;
    document.getElementById("r-perfil").disabled = true;
  }
}
function setPitch(p){ state.view = {...state.view, pitch:p, bearing:p?state.view.bearing:0};
  document.getElementById("v2d").classList.toggle("on", p===0);
  document.getElementById("v3d").classList.toggle("on", p!==0); render(); }
function tick(){ if(!state.playing) return;
  state.hour=(state.hour+1)%24; document.getElementById("hour").value=state.hour; render();
  setTimeout(tick, 650); }

Promise.all([
  fetch("./meta.json").then(r=>r.json()),
  fetch("./data.json").then(r=>r.json()),
  fetch("./weather.json").then(r=>r.json()),
  fetch("./rutas.json").then(r=>r.ok?r.json():null).catch(()=>null),
]).then(([m,d,w,ru])=>{
  META=m; DATA=d; WX=w; RUTAS=ru; state.day=m.dias[0];
  dgl = new DeckGL({container:"map", controller:true, viewState:state.view,
    ...(HAS_MAPLIBRE ? {map: maplibregl, mapStyle: BASEMAPS[state.basemap] || BASEMAP_VACIO} : {}),
    onViewStateChange:e=>{ state.view=e.viewState; dgl.setProps({viewState:state.view});
      // re-render props que dependen del zoom/pitch (radio de nodo, opacidad de
      // etiquetas, puntos<->barras en "auto") sin recalcular en cada frame
      if(!render._raf) render._raf = requestAnimationFrame(()=>{ render._raf = 0; render(); }); },
    getTooltip:tooltip, layers:[]});
  mkControls(); syncTabs();
  if(META.bbox) fitBounds(); else render();
}).catch(e=>{ document.getElementById("map").innerHTML =
  "<p style='color:#ccc;font:14px system-ui;padding:24px'>No se pudieron cargar los datos. "
  +"Sirve la carpeta con <code>python -m http.server -d viz/mapa</code>.<br>"+e+"</p>"; });
</script>
</body>
</html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
