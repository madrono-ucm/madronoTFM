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

El `.ipynb` se guarda **sin outputs** (repo limpio); genera las figuras al
ejecutarlo.

### Regenerar el notebook

El contenido vive en `notebooks/build_demo_notebook.py` (revisable en diff):

```bash
python notebooks/build_demo_notebook.py
```

### Versión de comandos (datos reales, para la defensa)

`doc/VIKT-06-recorrido-e2e.md` — el mismo recorrido con `aws`/`cypher` reales
y salida verificada.
