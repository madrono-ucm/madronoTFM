# ML-05 — Tier 2: GNN espacio-temporal (el elemento *wow*)

## Qué se creó

- **`modelado/models/stgnn.py`** — `STGNN` = **GraphSAGE + GRU**.
  - `ConvGraphSAGE` **a mano**: `h' = W_self·h + W_vec·mean_w(vecinos)`, con
    la media de vecinos ponderada por `edge_weight` vía `index_add`. Sin
    `torch_geometric`: así `edge_weight` queda en el grafo de autograd y
    `d(loss)/d(edge_weight)` da la **importancia de aristas** directamente,
    y la única dependencia nueva es `torch` (CPU).
  - Por hora: `capas_gnn` (=2) pasos de message passing → embedding de nodo.
    Un `GRU` recorre la secuencia de embeddings de cada nodo. Cabeza lineal
    → `[N, n_horizontes, n_targets]`.
  - Pequeño y regularizado a propósito (hidden 48, dropout 0.3, weight decay
    1e-4) para la ventana corta — demostración de metodología, no SOTA
    (§7.4).
- **`modelado/datasets/graph_snapshots.py`** — funciones puras panel →
  tensores de grafo:
  - `indice_nodos`, `columnas_features`, `coordenadas_por_nodo`.
  - `edges_desde_coords` — grafo de proximidad k-NN (u opcionalmente por
    radio) con núcleo gaussiano `exp(-(d/σ)²)` sobre la distancia haversine;
    simétrico, sin self-loops.
  - `edges_desde_lista` — mismas aristas desde `[(id_a, id_b, dist_m), …]`,
    p. ej. las `PROXIMO_A` reales exportadas de Neo4j.
  - `construir_snapshots` → `X [T,N,F]`, `Y [T,N,H]`, `M [T,N,H]` (máscara).
  - `ventanas_secuencia` → `Xseq [S,L,N,F]` + objetivo `Y[i]` / `M[i]` para
    el GRU, sin fuga (`Xseq` mira `X[i-L+1 … i]`, el objetivo es `Y` en
    `i`).
- **`modelado/training/train_stgnn.py`** — entry point end-to-end:
  panel → snapshots → split temporal (mismos cortes que `ML_02`) →
  estandarización con estadística **de train** → entrenamiento con early
  stopping sobre val (`--semilla` fija) → test destandarizado vs
  persistencia en **la misma tabla que Tier 1** → importancia de aristas →
  MLflow (`ML_04`, registra `madrono-stgnn-<target>`).
- **Importancia de aristas** — `mean |d(loss)/d(edge_weight)|` sobre hasta
  32 snapshots de test, plegada a aristas no dirigidas; top-15 + un ejemplo
  por nodo. Artefacto `modelado/evaluation/artifacts/tier2_<target>_aristas.json`.

`torch 2.13.0+cpu` (wheel binario, Python 3.14). `torch>=2.2,<3` en
`modelado/requirements.txt`. `python -m pytest modelado/ -q` → **27 passed**
(+7 de `test_ml05.py`: grafo simétrico sin self-loops, `edges_desde_lista`
ignora nodos fuera, formas/máscara de snapshots, ventanas sin fuga, forward
del STGNN, `edge_weight` recibe gradiente).

## Grafo usado

Por defecto el grafo se deriva de las **coordenadas del propio panel**
(k-NN, k=8, núcleo gaussiano) — reproducible sin credenciales. Para las
estaciones de calidad del aire (dispersas, km entre sí) el k-NN es el
criterio correcto; las `PROXIMO_A` de Neo4j entre estaciones del mismo tipo
son ellas mismas de proximidad (`distancia_m`), así que el grafo de
coordenadas las aproxima. `--aristas-json` conmuta al grafo real exportado
de Neo4j sin tocar nada más.

## Resultados reales — STGNN vs persistencia (test = últimos 3 días)

### `calidad_aire` (µg/m³, scope `grafo-lugares`, 54 nodos, grafo k-NN)

| h | modelo | n | MAE | RMSE | skill vs persistencia |
|---|---|---|---|---|---|
| 1 | stgnn | 3359 | 4.93 | 7.37 | **−0.51** |
| 1 | persistencia | 3359 | 2.63 | 6.01 | 0.00 |
| 3 | **stgnn** | 3255 | **5.14** | 8.63 | **+0.48** |
| 3 | persistencia | 3255 | 5.56 | 11.91 | 0.00 |
| 6 | **stgnn** | 3088 | **6.35** | 11.24 | **+0.55** |
| 6 | persistencia | 3088 | 8.55 | 16.81 | 0.00 |

Lectura honesta: **a 1 h la persistencia es muy difícil de batir** (la
concentración de contaminante cambia poco en una hora) y el STGNN pierde;
**su valor aparece a 3–6 h**, donde el contexto espacio-temporal aporta
(RMSE ~33 % por debajo de la persistencia a h6). Es el patrón esperado en
forecasting de calidad del aire / tráfico y coherente con la ventana corta
de datos. Tier 1 (LightGBM) rinde algo mejor en MAE puntual; el STGNN es la
pieza de **fusión sobre el grafo** y la de **explicabilidad por aristas**.

### `trafico` (`avg_service_level`, scope `grafo-lugares`, 1813 nodos)

El STGNN también corre sobre el grafo de tráfico de 1.813 nodos, pero el
bucle temporal por hora en CPU lo hace lento (~decenas de segundos por
época) y no se re-entrena en cada commit. La comparación STGNN vs LightGBM
vs persistencia en tráfico se consolida en los cuadernos de `ML_08` (§7),
donde los tres modelos se corren bajo el mismo arnés. Expectativa razonada:
en tráfico, donde la red es densa y LightGBM ya rinde muy alto (skill +0.78
a h6, `doc/ML-03`), el margen del GNN es menor que en calidad del aire —
su ventaja es la red de sensores **dispersa** y la fusión multi-señal.

## Explicabilidad — importancia de aristas

Ejemplo real (`calidad_aire`, grafo k-NN): la predicción de **O₃ en la
estación `28079035`** depende sobre todo de su vecina **`28079049` (mismo
contaminante, O₃)** — importancia ~10× la de la siguiente arista — y luego
de los canales NOx/NO₂/NO de esa misma estación vecina (química troposférica
O₃↔NOx) y del SO₂ de la propia estación. Es exactamente el tipo de
afirmación interpretable que pide el ticket: *"la predicción de O₃ en X
depende sobre todo de su vecina Y"*. JSON completo (top-15 + ejemplo) en
`modelado/evaluation/artifacts/tier2_<target>_aristas.json`.

## Criterios de aceptación

- [x] `train_stgnn.py` entrena end-to-end contra el panel real y produce
  métricas de `ML_02` comparables con Tier 1 en la misma tabla.
- [x] Importancia de aristas con al menos un ejemplo interpretable.
- [x] Tests: forward del STGNN con tensores de juguete (formas) +
  construcción de un snapshot desde una fixture pequeña.
- [x] Modelo pequeño / regularizado; determinista (`--semilla`).
- [x] `torch` (CPU) en `modelado/requirements.txt`; `torch_geometric` no
  hace falta (capa a mano) — decisión documentada arriba.

## Pendiente / lo retoman otros tickets

- **Multi-tarea real** (AQ + congestión + afluencia con un encoder
  compartido): requiere un panel conjunto sobre un conjunto de nodos común
  — los paneles de `ML_01` son por target. La cabeza ya está dimensionada
  (`n_targets`) para ello. Es la historia de fusión de `ML_08` §7.3.
- Grafo real de Neo4j vía `--aristas-json` (exportar las `PROXIMO_A`).
- `ML_08` — STGNN en los cuadernos de evaluación §7 junto a baseline y GBT.
- `ML_07` — export ONNX del `madrono-stgnn-*@champion`.
