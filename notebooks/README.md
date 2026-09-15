# `notebooks/`

## `demo_madrono.ipynb` — demo end-to-end (con foco en el elemento *wow*)

Recorre el sistema completo en ~4 min y se detiene en la **STGNN**: modelar la
ciudad como un grafo y aprender **qué conexiones entre lugares** explican la
congestión (importancia de aristas = `∂pérdida/∂edge_weight`).

| § | Qué | Necesita |
|---|---|---|
| 1 | Un XML del Ayuntamiento → una fila *Gold* (Bronze→Silver→Gold, Python puro) | nada |
| 2 | El grafo urbano (`:Lugar`–`PROXIMO_A`–`:EstacionMedida`) | Neo4j *(opcional)* |
| **3** | **⭐ STGNN: entrenamiento en vivo, skill vs persistencia, importancia de aristas, export ONNX** | nada |
| 4 | El bucle observación→predicción→asistente (tool MCP `*_prevista`) | nada *(mocks)* |
| 5 | Limitaciones reales (§7.4), sin maquillar | nada |

Corre **sin credenciales**: §2 cae a un mini-grafo sintético «mini-Madrid» y
§3–4 usan ese grafo + mocks del asistente. Con `AWS_PROFILE=madrono` /
`NEO4J_*` en el entorno, §2 y §5 usan datos reales y lo indican por pantalla.

### Ejecutar

```bash
# desde la raíz del repo
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r modelado/requirements.txt              # torch CPU, ver FIL_23 / modelado/README.md
pip install -r asistente/requirements.txt
pip install jupyterlab                                # o abrir el .ipynb en VS Code

jupyter lab notebooks/demo_madrono.ipynb             # → "Run All"
```

El `.ipynb` del repo lleva **las salidas ejecutadas** (13 celdas, 5 figuras,
0 errores) para que GitHub las muestre sin correrlo. Se ejecutó con
`jupyter nbconvert --execute` sin credenciales (mini-grafo + mocks).

### Regenerar / refrescar el notebook

El contenido vive en `notebooks/build_demo_notebook.py` (revisable en diff):

```bash
python notebooks/build_demo_notebook.py                 # regenera limpio
jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.timeout=360 notebooks/demo_madrono.ipynb   # vuelve a rellenar salidas
```

### Versión de comandos (datos reales, para la defensa)

`doc/VIKT-06-recorrido-e2e.md` — el mismo recorrido con `aws`/`cypher` reales
y salida verificada.

## `demo_asistente.ipynb` — demo de la capa conversacional (LLM + MCP)

Complementa a `demo_madrono.ipynb` (que se centra en el elemento *wow* de
ML). Este cuaderno es el **guion de la demo del producto**: el servidor
MCP, el bucle de tool-calling del chat, la traza `pasos` que ve el usuario
bajo cada respuesta (FIL_95), `ruta_saludable` y la degradación elegante
(el asistente dice «no lo sé» en vez de inventar).

| § | Qué | Necesita |
|---|---|---|
| 1 | Las 19 tools del servidor MCP + el catálogo del chat (`GET /chat/catalogo`) | nada |
| 2 | Una tool por dentro: el envoltorio `{disponible, motivo, datos}` | nada *(datos mock)* |
| **3** | **El bucle de tool-calling real y la traza `pasos`** | nada *(guion determinista; real si hay `LLM_API_KEY`)* |
| 4 | `ruta_saludable`: sana vs rápida, 9 perfiles, mejor hora de salida | nada *(artefacto vendorizado)* |
| 5 | Degradación elegante — no inventa una ruta ni un lugar | nada |
| 6 | Cómo lo ve el usuario y dónde probarlo en vivo | nada |

Trae también, en su segunda celda, un **guion de defensa/screencast** de
~6 min con la app en vivo (qué preguntar, en qué orden, qué señalar).

Corre **sin credenciales**: Athena/Neo4j se sustituyen por datos de demo y
el LLM por un guion determinista que ejerce *el mismo bucle real* de
`asistente/chat.py`. Con `LLM_API_KEY`/`GROQ_API_KEY` en el entorno, §3
llama al modelo de verdad.

```bash
python notebooks/build_demo_asistente_notebook.py                 # regenera limpio
jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.timeout=300 notebooks/demo_asistente.ipynb   # rellena salidas
```
