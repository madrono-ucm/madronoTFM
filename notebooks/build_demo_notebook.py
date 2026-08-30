"""Genera `notebooks/demo_madrono.ipynb` — la demo end-to-end del proyecto,
con foco en el elemento *wow* (la STGNN: modelar la ciudad como un grafo y
aprender qué **conexiones** explican la congestión).

Se guarda el generador (y no solo el `.ipynb`) para que la demo sea
revisable en diff y regenerable:

    python notebooks/build_demo_notebook.py

El notebook resultante se ejecuta de arriba a abajo **sin credenciales**
(usa un mini-grafo sintético «mini-Madrid» y mocks del asistente); si hay
Neo4j / MLflow / paneles reales disponibles, algunas celdas usan datos
reales y lo indican por pantalla.
"""

from __future__ import annotations

import json
from pathlib import Path

NB = Path(__file__).with_name("demo_madrono.ipynb")


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n") + "\n"}


def code(src: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": src.strip("\n") + "\n",
    }


CELLS: list[dict] = []
CELLS.append(md(r"""
# Madroño — demo end-to-end

**Plataforma de datos de movilidad y vida urbana de Madrid → modelos predictivos → asistente MCP.**

Este cuaderno recorre el sistema completo en ~4 minutos y se detiene en el **elemento *wow*** del TFM:
una **red neuronal de grafo espacio-temporal (STGNN)** que modela la ciudad como un grafo y aprende
**qué conexiones entre lugares** explican la congestión — algo que un modelo de árboles no puede dar.

| § | Qué | Necesita |
|---|---|---|
| 1 | Un XML del Ayuntamiento → una fila *Gold* (medallón Bronze→Silver→Gold) | nada |
| 2 | El grafo urbano (`:Lugar`–`PROXIMO_A`–`:EstacionMedida`) | Neo4j *(opcional)* |
| **3** | **⭐ La STGNN: entrenamiento, skill, e *importancia de aristas*** | nada |
| 4 | El bucle observación→predicción→asistente (tool MCP `*_prevista`) | nada *(mocks)* |
| 5 | Honestidad: limitaciones reales (§7.4) | nada |

> El cuaderno corre **sin credenciales**: §2 cae a un mini-grafo sintético «mini-Madrid» y §3–4 usan
> ese mini-grafo + mocks. Con `AWS_PROFILE`/`NEO4J_*` reales, §2 y §5 usan datos de verdad y lo avisan.
""".strip()))

CELLS.append(code(r"""
import os, sys, warnings, json, time
from pathlib import Path

# raíz del repo en el path (el cuaderno vive en notebooks/)
ROOT = Path.cwd()
if not (ROOT / "asistente").is_dir():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import numpy as np
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")
np.set_printoptions(precision=3, suppress=True)
print("repo:", ROOT)
print("pipeline de ingesta CONGELADO desde 2026-08-30 — los datos llegan hasta ~2026-08-29")
""".strip()))

# ---------------------------------------------------------------- §1
CELLS.append(md(r"""
## 1 · De un XML del Ayuntamiento a una fila *Gold*

Sin Spark ni AWS: la lógica de cada job de Glue está en **Python puro** y testeable
(`procesamiento/silver_gold/<ds>/{transform,aggregate}.py`). Aquí un registro real de
`informo.madrid.es` (fixture commiteado) atraviesa las tres capas.
""".strip()))

CELLS.append(code(r"""
from datetime import datetime, timezone
from ingesta.capturas.trafico_madrid import parse_records
from procesamiento.silver_gold.trafico.transform import bronze_to_silver
from procesamiento.silver_gold.trafico.aggregate import aggregate_silver_to_gold

xml = (ROOT / "ingesta/tests/fixtures/pm_sample.xml").read_text(encoding="utf-8")
bronze = list(parse_records(xml, datetime(2026, 8, 12, 10, tzinfo=timezone.utc)))
silver, rechazados = bronze_to_silver(bronze, datetime(2026, 8, 12, 10, 5, tzinfo=timezone.utc))
gold = aggregate_silver_to_gold(silver, datetime(2026, 8, 12, 10, 5, tzinfo=timezone.utc))

print(f"Bronze: {len(bronze)} registros crudos   Silver: {len(silver)} válidos "
      f"({len(rechazados)} rechazados por la puerta de calidad)   Gold: {len(gold)} filas agregadas\n")
print("BRONZE (crudo, coords UTM tal cual las publica la fuente):")
print(json.dumps({k: bronze[0][k] for k in ("point_id", "intensity_vph", "service_level", "location")},
                 indent=1, ensure_ascii=False))
print("\nSILVER (validado + reproyectado a WGS84 + ratios normalizados):")
print(json.dumps({k: silver[0][k] for k in ("point_id", "location", "occupancy_ratio", "intensity_ratio")},
                 indent=1, ensure_ascii=False))
print("\nGOLD (agregado por punto + hora — lo que consulta el asistente vía Athena):")
print(json.dumps({k: gold[0][k] for k in ("point_id", "date", "hour", "avg_service_level",
                                          "avg_intensity_vph", "samples_count")}, indent=1, ensure_ascii=False))
""".strip()))

# ---------------------------------------------------------------- §2
CELLS.append(md(r"""
## 2 · El grafo urbano

Lo que permite *cruzar* datasets: `(:Lugar)-[:PROXIMO_A]-(:EstacionMedida)` en Neo4j.
El asistente resuelve «Retiro» → nodo `:Lugar` → sensores de tráfico a ≤ 300 m.

Si hay `NEO4J_*` en el entorno, se trae un subgrafo real; si no, se construye **mini-Madrid**:
8 zonas del centro × 2 sensores, unidas por un grafo k-NN de proximidad. La misma estructura que
usa la STGNN de verdad (que además puede leer las aristas `PROXIMO_A` reales, ver `train_stgnn.py`).
""".strip()))

CELLS.append(code(r"""
from modelado.datasets.graph_snapshots import edges_desde_coords

rng = np.random.default_rng(7)
LANDMARKS = {
    "Sol": (40.4169, -3.7035), "Retiro": (40.4153, -3.6844), "Atocha": (40.4065, -3.6895),
    "Chamberí": (40.4361, -3.7038), "Cuatro Caminos": (40.4470, -3.7038), "Moncloa": (40.4352, -3.7192),
    "Plaza España": (40.4239, -3.7128), "Bilbao": (40.4292, -3.7010),
}
NOMBRES, COORDS = [], []
for zona, (la, lo) in LANDMARKS.items():
    for j in range(2):
        NOMBRES.append(f"{zona} · s{j}")
        COORDS.append([la + rng.normal(0, 4e-4), lo + rng.normal(0, 4e-4)])
COORDS = np.array(COORDS)
N = len(NOMBRES)
EDGE_INDEX, EDGE_WEIGHT = edges_desde_coords(COORDS, k=3)          # [2, E], [E]
FUENTE_GRAFO = "mini-Madrid sintético (k-NN)"

# --- upgrade a datos reales si hay Neo4j ---
if all(v in os.environ for v in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")):
    try:
        from asistente.neo4j_client import (
            lugares_proximos_a_estaciones_trafico_query, run_neo4j_query)
        q, p = lugares_proximos_a_estaciones_trafico_query("Retiro", 300.0)
        filas = run_neo4j_query(q, p)
        print(f"Neo4j REAL: {len(filas)} estaciones de tráfico a ≤300 m de «Retiro»")
        for f in filas[:5]:
            print(f"  {f['estacion_id']}  ({f['distancia_m']:.0f} m)")
        FUENTE_GRAFO = "Neo4j real (subgrafo «Retiro»)"
    except Exception as e:
        print("Neo4j no disponible:", type(e).__name__, "— sigo con mini-Madrid")

print(f"\nGrafo para la demo: {FUENTE_GRAFO} — {N} nodos, {EDGE_INDEX.shape[1] // 2} aristas no dirigidas")

fig, ax = plt.subplots(figsize=(7, 6))
for k in range(0, EDGE_INDEX.shape[1], 2):
    a, b = EDGE_INDEX[0, k], EDGE_INDEX[1, k]
    ax.plot(COORDS[[a, b], 1], COORDS[[a, b], 0], "-", color="0.75", lw=1, zorder=1)
ax.scatter(COORDS[:, 1], COORDS[:, 0], s=90, c="#c0392b", zorder=2)
for i, nm in enumerate(NOMBRES):
    if nm.endswith("s0"):
        ax.annotate(nm.split(" · ")[0], (COORDS[i, 1], COORDS[i, 0]),
                    textcoords="offset points", xytext=(6, 5), fontsize=9)
ax.set_title("Grafo urbano — nodos = sensores, aristas = proximidad"); ax.set_xlabel("lon"); ax.set_ylabel("lat")
plt.tight_layout(); plt.show()
""".strip()))

# ---------------------------------------------------------------- §3
CELLS.append(md(r"""
## 3 · ⭐ El elemento *wow* — la STGNN

`modelado/models/stgnn.py`: **GraphSAGE + GRU**, hecho a mano (una sola dependencia, `torch` CPU).

1. Por cada hora de la ventana, `capas_gnn` pasos de *message passing* sobre el grafo → un embedding por nodo.
2. Un GRU recorre la secuencia de embeddings de cada nodo → estado final.
3. Una cabeza lineal proyecta a `[N, horizontes, targets]` — **multi-horizonte y multi-señal en un solo modelo**.

La capa `ConvGraphSAGE` promedia los mensajes de los vecinos **ponderados por `edge_weight`**, y
`edge_weight` queda en el grafo de autograd → `d(pérdida)/d(edge_weight)` es la **importancia de aristas** (§3.5).
""".strip()))

CELLS.append(md(r"""
### 3.1 · Señal espacio-temporal

Mini-Madrid: una señal de «nivel de servicio» con **ciclo diario** + **difusión espacial por las aristas**
(la congestión se propaga entre zonas conectadas) + ruido. Es lo que hace que *el grafo importe*.

> El entrenamiento real: `python -m modelado.training.train_stgnn --panel modelado/_data/panel_trafico_grafo.parquet`
> (panel de `ML_01` + aristas `PROXIMO_A` reales de Neo4j). Resultados en `modelado/evaluation/artifacts/tier2_*`.
""".strip()))

CELLS.append(code(r"""
L_HIST, T = 8, 24 * 10          # ventana de 8 h, 10 días de histórico horario
horas = np.arange(T) % 24
diurna = 0.6 * (1 + np.sin((horas - 8) / 24 * 2 * np.pi)) + 0.9 * ((horas >= 17) & (horas <= 20))
sesgo_nodo = rng.uniform(0.2, 1.4, N)
sig = np.outer(diurna, sesgo_nodo) + rng.normal(0, 0.15, (T, N))

A = np.zeros((N, N))
for k in range(EDGE_INDEX.shape[1]):
    A[EDGE_INDEX[0, k], EDGE_INDEX[1, k]] = EDGE_WEIGHT[k]
A = A / A.sum(1, keepdims=True).clip(1e-6)
for t in range(1, T):                       # difusión: cada hora se mezcla con los vecinos
    sig[t] = 0.55 * sig[t] + 0.45 * (A @ sig[t - 1])
sig = np.clip(sig, 0, None).astype("float32")

F = 3                                        # features de nodo: [nivel, hora_sin, hora_cos]
X = np.zeros((T, N, F), "float32")
X[:, :, 0] = sig
X[:, :, 1] = np.sin(horas / 24 * 2 * np.pi)[:, None]
X[:, :, 2] = np.cos(horas / 24 * 2 * np.pi)[:, None]

HOR = (1, 3, 6)
idx = np.arange(L_HIST, T - max(HOR))
Xseq = np.stack([X[i - L_HIST:i] for i in idx]).astype("float32")                     # [S, L, N, F]
Y = np.stack([np.stack([sig[i + h] for h in HOR], 1) for i in idx]).astype("float32")  # [S, N, H]
S = len(idx); corte = int(S * 0.8)

mu, sd = Xseq[:corte].mean((0, 1, 2), keepdims=True), Xseq[:corte].std((0, 1, 2), keepdims=True).clip(1e-6)
ymu, ysd = Y[:corte].mean((0, 1), keepdims=True), Y[:corte].std((0, 1), keepdims=True).clip(1e-6)
print(f"{S} ventanas de secuencia ([L={L_HIST}, N={N}, F={F}]) — {corte} train / {S - corte} test")

fig, ax = plt.subplots(figsize=(9, 3))
ax.plot(sig[:96, :4]); ax.set_title("Nivel de servicio — primeras 96 h, 4 sensores")
ax.set_xlabel("hora"); plt.tight_layout(); plt.show()
""".strip()))

CELLS.append(md(r"""
### 3.2 · Entrenamiento (unos segundos)
""".strip()))

CELLS.append(code(r"""
import torch
from modelado.models.stgnn import STGNN

ei = torch.tensor(EDGE_INDEX, dtype=torch.long)
ew = torch.tensor(EDGE_WEIGHT, dtype=torch.float32)
Xt = torch.tensor((Xseq - mu) / sd)
Yt = torch.tensor((Y - ymu) / ysd)

torch.manual_seed(0)
stgnn = STGNN(in_dim=F, hidden=16, n_horizontes=3, n_targets=1, capas_gnn=2, dropout=0.1)
opt = torch.optim.Adam(stgnn.parameters(), lr=1e-2, weight_decay=1e-4)

t0 = time.time()
for epoca in range(25):
    stgnn.train()
    for i in np.random.permutation(corte)[:48]:
        opt.zero_grad()
        pred = stgnn(Xt[i], ei, ew).squeeze(-1)
        ((pred - Yt[i]) ** 2).mean().backward()
        opt.step()
print(f"entrenado en {time.time() - t0:.0f} s  ({sum(p.numel() for p in stgnn.parameters()):,} parámetros)")
""".strip()))

CELLS.append(md(r"""
### 3.3 · Multi-horizonte y multi-señal en un solo forward
""".strip()))

CELLS.append(code(r"""
stgnn.eval()
with torch.no_grad():
    y_una = stgnn(Xt[corte], ei, ew)          # una ventana de test
print("salida del modelo para UNA hora:", tuple(y_una.shape), "= [N nodos, 3 horizontes, 1 target]")
print("→ predice el nivel de servicio de los", N, "sensores a 1 h, 3 h y 6 h vista, a la vez.")
""".strip()))

CELLS.append(md(r"""
### 3.4 · Bate a la persistencia

Baseline = «dentro de *h* horas habrá lo mismo que ahora». *Skill* = `1 − MAE_modelo / MAE_persistencia`.
""".strip()))

CELLS.append(code(r"""
with torch.no_grad():
    pred_test = torch.stack([stgnn(Xt[i], ei, ew).squeeze(-1) for i in range(corte, S)]).numpy() * ysd + ymu
y_real = Y[corte:]
persist = np.repeat(Xseq[corte:, -1, :, 0:1], 3, axis=2)   # value(t) como predicción de t+h

filas = []
for hi, h in enumerate(HOR):
    mae_stgnn = np.abs(pred_test[:, :, hi] - y_real[:, :, hi]).mean()
    mae_pers = np.abs(persist[:, :, hi] - y_real[:, :, hi]).mean()
    filas.append((h, mae_pers, mae_stgnn, 1 - mae_stgnn / mae_pers))
    print(f"h{h}:  persistencia MAE={mae_pers:.3f}   STGNN MAE={mae_stgnn:.3f}   skill={1 - mae_stgnn / mae_pers:+.2f}")

hs = [f"h{h}" for h, *_ in filas]
x = np.arange(len(hs)); w = 0.38
fig, ax = plt.subplots(figsize=(6, 3.4))
ax.bar(x - w / 2, [r[1] for r in filas], w, label="persistencia", color="0.7")
ax.bar(x + w / 2, [r[2] for r in filas], w, label="STGNN", color="#2e86c1")
ax.set_xticks(x); ax.set_xticklabels(hs); ax.set_ylabel("MAE (nivel de servicio)")
ax.set_title("STGNN vs persistencia por horizonte"); ax.legend()
plt.tight_layout(); plt.show()
""".strip()))

CELLS.append(md(r"""
### 3.5 · ⭐⭐ Importancia de aristas — *qué conexiones explican la congestión*

`edge_weight` está en el grafo de autograd, así que `mean |∂ pérdida / ∂ edge_weight|` sobre el test dice
**cuánto depende la predicción de cada conexión del grafo**. Esto es lo que un modelo de árboles no te da:
no «qué feature», sino **qué relación entre lugares**.
""".strip()))

CELLS.append(code(r"""
ew_var = ew.clone().detach().requires_grad_(True)
acum = torch.zeros_like(ew_var)
n_muestras = min(24, S - corte)
for i in range(corte, corte + n_muestras):
    stgnn.zero_grad()
    if ew_var.grad is not None:
        ew_var.grad.zero_()
    ((stgnn(Xt[i], ei, ew_var).squeeze(-1) - Yt[i]) ** 2).mean().backward()
    acum += ew_var.grad.abs()
imp = (acum / n_muestras).detach().numpy()

plegado = {}
for k in range(EDGE_INDEX.shape[1]):
    a, b = int(EDGE_INDEX[0, k]), int(EDGE_INDEX[1, k])
    clave = (min(a, b), max(a, b))
    plegado[clave] = plegado.get(clave, 0.0) + imp[k]
orden = sorted(plegado.items(), key=lambda kv: kv[1], reverse=True)

print("Conexiones más influyentes para la predicción:")
for (a, b), v in orden[:5]:
    print(f"  {NOMBRES[a]:16} ←→ {NOMBRES[b]:16}   importancia {v:.4f}")

vmax = orden[0][1] if orden else 1.0
fig, ax = plt.subplots(figsize=(7, 6))
for (a, b), v in orden:
    ax.plot(COORDS[[a, b], 1], COORDS[[a, b], 0], "-",
            color=plt.cm.magma(0.15 + 0.8 * v / vmax), lw=0.6 + 5 * v / vmax, zorder=1)
ax.scatter(COORDS[:, 1], COORDS[:, 0], s=70, c="0.2", zorder=2)
for i, nm in enumerate(NOMBRES):
    if nm.endswith("s0"):
        ax.annotate(nm.split(" · ")[0], (COORDS[i, 1], COORDS[i, 0]),
                    textcoords="offset points", xytext=(6, 5), fontsize=9)
ax.set_title("Importancia de aristas — grosor/color ∝ ∂pérdida/∂edge_weight")
ax.set_xlabel("lon"); ax.set_ylabel("lat")
plt.tight_layout(); plt.show()
""".strip()))

CELLS.append(md(r"""
### 3.6 · Servible — exportar el modelo-grafo a ONNX (`FIL_20`)

La memoria daba el STGNN por *no servible*. No es cierto: `torch.onnx.export(dynamo=True)` lo exporta
con paridad de `float32` (`≈ 1e-7`), y el nº de nodos/aristas queda como **eje dinámico** —
el mismo `.onnx` sirve para un grafo distinto.
""".strip()))

CELLS.append(code(r"""
import tempfile
from modelado.export import to_onnx

with tempfile.TemporaryDirectory() as tmp:
    with torch.no_grad():
        y_ref = stgnn(Xt[corte], ei, ew).numpy()
    r = to_onnx.exportar_stgnn(stgnn, (Xt[corte], ei, ew), Path(tmp) / "stgnn_demo.onnx", y_nativo=y_ref)
    print(f"ONNX: {r['onnx_bytes']:,} bytes"
          f"{' + sidecar .data' if r['sidecar_data'] else ''}")
    print(f"paridad torch ↔ onnxruntime:  max|Δ| = {r['paridad']['max']:.2e}  "
          f"(shape {tuple(r['paridad']['shape_onnx'])})")
""".strip()))

# ---------------------------------------------------------------- §4
CELLS.append(md(r"""
## 4 · Cerrando el bucle — el asistente MCP

`observación → predicción → asistente`. Las tools `*_prevista` construyen 19 features de las últimas 24 h
de *Gold*, corren un modelo **ONNX** (LightGBM; y el STGNN de §3 vía `calidad_aire_prevista_grafo`) y
devuelven una respuesta con **procedencia trazable**: valor, modelo exacto, ventana de datos, confianza.

Aquí se mockea Athena/Neo4j para que corra sin credenciales — con `AWS_PROFILE`/`NEO4J_*` reales
serían los mismos objetos con datos vivos.
""".strip()))

CELLS.append(code(r"""
from datetime import timedelta
from unittest.mock import patch
from asistente.mcp_agent import tools

MOMENTO = datetime(2026, 8, 29, 18, 0)   # dentro de la ventana con datos (pipeline congelado)

def _gold_trafico(inst, n=25):
    base = inst.replace(minute=0, second=0, microsecond=0)
    return [{"point_id": "PM10001",
             "date": (base - timedelta(hours=k)).date().isoformat(),
             "hour": (base - timedelta(hours=k)).hour,
             "avg_service_level": max(0.0, 2.4 - 0.05 * k), "lat": 40.415, "lon": -3.684}
            for k in range(n)]

def _gold_aire(inst, n=25):
    base = inst.replace(minute=0, second=0, microsecond=0)
    return [{"station_id": "28079035", "station_name": "Pza. del Carmen", "pollutant": "NO2",
             "unit": "µg/m³", "date": (base - timedelta(hours=k)).date().isoformat(),
             "hour": (base - timedelta(hours=k)).hour,
             "avg_value": 55.0 + (k % 6) * 6, "lat": 40.419, "lon": -3.703}
            for k in range(n)]

_GRAFO = [{"estacion_id": "trafico:PM10001", "distancia_m": 85.0}]

with patch("asistente.mcp_agent.tools.run_neo4j_query", return_value=_GRAFO), \
     patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold_trafico(MOMENTO)):
    tp = tools.trafico_prevista("Retiro", horizonte_horas=3, momento=MOMENTO)

with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold_aire(MOMENTO)):
    cap = tools.calidad_aire_prevista("Carmen", horizonte_horas=3, momento=MOMENTO)

print("trafico_prevista(«Retiro», +3 h):")
print(tp.model_dump_json(indent=1))
print("\ncalidad_aire_prevista(«Carmen», +3 h):")
print(json.dumps({k: getattr(cap, k) for k in
                  ("contaminante", "valor_actual", "valor_previsto", "unidad", "nivel_previsto",
                   "modelo", "ventana_datos", "data_completeness")}, indent=1, ensure_ascii=False))
""".strip()))

CELLS.append(md(r"""
### El STGNN, servido por MCP (`FIL_26`)

`calidad_aire_prevista_grafo` corre el **modelo de grafo** de §3 (el `@champion` real, vía ONNX
sin `torch`) y devuelve, además de la cifra, **`vecinos_influyentes`**: qué conexiones del grafo
pesan más en la predicción de esa estación. Es la explicabilidad de §3.5, ahora dentro del asistente.

> Honesto (§7.4): este STGNN pierde a `calidad_aire_prevista` (LightGBM) en métricas puntuales a
> 1 h; se sirve por la trazabilidad de grafo, con `fiabilidad` topada en BAJA.
""".strip()))

CELLS.append(code(r"""
import json as _json
from pathlib import Path as _Path
from asistente import prevision_grafo

_META = _json.loads((_Path(prevision_grafo.__file__).parent / "modelos" / "stgnn_calidad_aire.meta.json")
                    .read_text(encoding="utf-8"))
_NODOS = list(_META["node_index"])
_NOMS = {"28079049": "Parque del Retiro", "28079035": "Plaza del Carmen"}

def _gold_grafo(inst, n=40):
    base = inst.replace(minute=0, second=0, microsecond=0)
    out = []
    for nodo in _NODOS:
        sid, pol = nodo.split("__", 1)
        for k in range(n):
            t = base - timedelta(hours=k)
            out.append({"station_id": sid, "station_name": _NOMS.get(sid, sid), "pollutant": pol,
                        "unit": "µg/m³", "date": t.date().isoformat(), "hour": t.hour,
                        "avg_value": 60.0 + (hash(nodo) % 30) + (k % 6) * 3.0})
    return out

with patch("asistente.mcp_agent.tools.run_athena_query", return_value=_gold_grafo(MOMENTO)):
    g = tools.calidad_aire_prevista_grafo("Retiro", horizonte_horas=3, momento=MOMENTO)

print(f"calidad_aire_prevista_grafo(«Retiro», +3 h) — nodo {g.nodo}")
print(f"  actual {g.valor_actual} → previsto {g.valor_previsto} {g.unidad}  ({g.nivel_previsto})")
print(f"  {g.modelo}  ·  {g.n_nodos_grafo} nodos")
print("  vecinos influyentes (∂pérdida/∂edge_weight):")
for v in g.vecinos_influyentes:
    print(f"    {v.estacion} · {v.contaminante}   {v.importancia:.4f}")
""".strip()))

CELLS.append(code(r"""
# el servidor MCP real, listado de tools
import logging
logging.disable(logging.CRITICAL)
from asistente.mcp_agent.server import mcp

# `list_tools` es async; el kernel de Jupyter ya tiene su event loop, así que
# se usa `await` de nivel superior (NO `asyncio.run` / `new_event_loop`, que
# revientan con "Cannot run the event loop while another loop is running").
tools_mcp = await mcp.list_tools()
print(f"servidor MCP «madrono» — {len(tools_mcp)} tools, todas read-only:")
for t in sorted(tools_mcp, key=lambda x: x.name):
    esquema = "in+out schema" if (t.input_schema and t.output_schema) else "solo input schema"
    print(f"  {t.name:28} {esquema}")
""".strip()))

# ---------------------------------------------------------------- §5
CELLS.append(md(r"""
## 5 · Honestidad — limitaciones (memoria §7.4)

- **Ventana de datos corta** (semanas): los modelos son una *demostración de metodología*, no una
  estimación de rendimiento estacional. Por eso el asistente nunca da fiabilidad > «media».
- **En métricas puntuales, LightGBM gana a la STGNN** con esta ventana. El valor de la STGNN es
  la *explicabilidad de grafo* (§3.5) y el modelado multi-señal, no la precisión bruta.
- **Pipeline congelado** desde 2026-08-30 para no seguir gastando: los datos llegan hasta ~2026-08-29.
""".strip()))

CELLS.append(code(r"""
import pandas as pd

comp = ROOT / "modelado/evaluation/artifacts/estudios/comparacion_todos.csv"
if comp.exists():
    df = pd.read_csv(comp)
    piv = (df.pivot_table(index=["target", "horizonte"], columns="familia", values="skill")
             .reindex(columns=["baseline", "lightgbm", "stgnn"]))
    print("skill vs baseline (real, `estudio_comparacion.py`):")
    print(piv.round(2).to_string())
else:
    print("comparacion_todos.csv no presente — regenerar con `python -m modelado.evaluation.estudios.run_all`")

bt = ROOT / "modelado/evaluation/artifacts/backtest/skill_vs_fecha_calidad_aire.png"
if bt.exists():
    from matplotlib import image as mpimg
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.imshow(mpimg.imread(bt)); ax.axis("off")
    ax.set_title("Backtest incremental — el skill mejora al acumularse días de histórico")
    plt.tight_layout(); plt.show()
""".strip()))

CELLS.append(md(r"""
---

### Recap

| capa | evidencia en este cuaderno |
|---|---|
| datos | §1 — un XML real → Bronze → Silver → Gold, en Python puro |
| grafo | §2 — `:Lugar`–`PROXIMO_A`–`:EstacionMedida` (real si hay Neo4j) |
| **ML wow** | §3 — STGNN entrenada en vivo: multi-horizonte, bate a persistencia, **importancia de aristas**, exportable a ONNX |
| asistente | §4 — tool MCP `*_prevista` cerrando el bucle, con procedencia trazable |
| rigor | §5 — limitaciones reales, sin maquillar |

Comandos reales (datos completos, credenciales): `doc/VIKT-06-recorrido-e2e.md`.
Arquitectura y layout: `README.md`. Modelado: `modelado/README.md`.
""".strip()))


def main() -> None:
    nb = {
        "cells": CELLS,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    NB.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"escrito {NB}  ({len(CELLS)} celdas)")


if __name__ == "__main__":
    main()
