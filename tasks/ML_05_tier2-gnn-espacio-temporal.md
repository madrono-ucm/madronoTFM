---
kind: ml
title: "Tier 2 — GNN espacio-temporal multi-tarea sobre el grafo Neo4j (el elemento wow)"
owner: Filippos (interactive)
status: done
depends_on: [ML_02]
created_at: "2026-08-28"
---

> **Estado 29/8: ✅ HECHO.** `models/stgnn.py` (GraphSAGE+GRU, capa
> `ConvGraphSAGE` a mano → `d(loss)/d(edge_weight)` = importancia de
> aristas, sin `torch_geometric`), `datasets/graph_snapshots.py` (grafo
> k-NN gaussiano de coordenadas o `--aristas-json` de las `PROXIMO_A`
> reales; snapshots `X/Y/M`; ventanas de secuencia sin fuga),
> `training/train_stgnn.py` (end-to-end, split de `ML_02`, early stopping,
> `--semilla`, MLflow `tier2` → `madrono-stgnn-<target>`).
> `calidad_aire` (54 nodos): STGNN pierde con persistencia a h1 (esperado)
> y la bate a h3/h6 (skill +0.48 / +0.55). Importancia de aristas
> interpretable (O₃@28079035 ← O₃@28079049). `torch>=2.2,<3` en
> requirements. 27 tests en verde (+7 `test_ml05.py`). `doc/ML-05`.

## Objetivo

El elemento central del TFM (memoria §2 keywords: *"redes neuronales de
grafos"*): un GNN espacio-temporal que **fusiona señales multi-modales sobre
el grafo urbano** para predecir el estado de la ciudad (calidad del aire,
congestión, afluencia) a 1/3/6 h, por nodo.

## Diseño

- **Grafo**: el urbano de Neo4j. Nodos = estaciones de sensor + `:Lugar`.
  Aristas = `PROXIMO_A` (con `distancia_m` como peso), opcionalmente
  `CONECTADO_CON` para la red de transporte. Exportar una vez a un formato
  estático (edge list + node index) — no consultar Neo4j en cada época.
- **Features de nodo por hora** = el panel de `ML_01` alineado al snapshot
  (`ML_02` windowing).
- **Arquitectura** (elegir la más simple que funcione con ~500 snapshots):
  - **GraphSAGE + GRU** (recomendada: robusta con pocos datos): message
    passing espacial por hora + un GRU sobre la secuencia de embeddings.
  - Alternativas: A3T-GCN, DCRNN (más parámetros, más riesgo con la ventana
    corta).
- **Cabeza multi-tarea**: predice AQ + congestión + afluencia a la vez
  (comparten el encoder) — la historia de "fusión" de §7.3.
- **Multi-horizonte**: salida `[n_nodos, n_horizontes, n_targets]`.

## Alcance

- `modelado/models/stgnn.py`: la red (PyTorch + `torch_geometric` **o** una
  implementación a mano de GraphSAGE si `torch_geometric` no instala limpio
  en el entorno — decidir y documentar).
- `modelado/datasets/graph_snapshots.py`: construye los tensores
  `(x, edge_index, edge_weight, y)` por hora desde el panel + la edge list.
- `modelado/training/train_stgnn.py`: entrenamiento con early stopping sobre
  val, `random_state` fijo; loguea en MLflow (`ML_04`).
- **Explicabilidad — importancia de aristas**: gradiente de la pérdida
  respecto a `edge_weight` (o GNNExplainer si `torch_geometric` está) — qué
  vecinos del grafo pesan más en la predicción de un nodo. Figura +
  comentario.

## Criterios de aceptación

- `train_stgnn.py` entrena end-to-end contra el panel real y produce
  métricas (`ML_02`) comparables con Tier 1 en la misma tabla.
- Importancia de aristas: al menos un ejemplo interpretable ("la predicción
  de NO2 en la estación X depende sobre todo de sus vecinos Y, Z a <150 m").
- Tests: `stgnn.py` hace un forward con tensores de juguete (formas
  correctas); `graph_snapshots.py` construye un snapshot de una fixture
  pequeña.

## Restricciones

- Ventana corta (~500 snapshots): modelo pequeño (2 capas, hidden <=64),
  dropout alto, weight decay. Es una **demostración de metodología**, no un
  SOTA — decirlo en el `doc/` y remitir a §7.4.
- `torch` (CPU), `torch_geometric` opcional → `modelado/requirements.txt`.
- Determinista y reproducible.
