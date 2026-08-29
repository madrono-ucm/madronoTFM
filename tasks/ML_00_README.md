---
kind: ml-index
owner: Filippos (interactive, pista Sistema)
created_at: "2026-08-28"
---

# `ML_*` tickets — pista de modelado (`modelado/`)

El elemento central del TFM (memoria §3.2: *"modelar la ciudad como un
grafo y entrenar modelos predictivos de afluencia, congestión y calidad del
aire"*, §2 keywords: *"redes neuronales de grafos"*). Fuera de la cola del
demonio (mismo criterio que `FIL_*`): se trabajan interactivamente porque
varias etapas necesitan credenciales AWS/Neo4j y registro real de modelos.

Diseño aprobado (28/8, ver `NEXT_STEPS.md` §5.3):

- **Tier 0** — fundación: feature store sin fugas, arnés de CV temporal,
  líneas base, MLflow tracking+registry, Evidently, export ONNX.
- **Tier 1** — forecasters LightGBM multi-horizonte (1/3/6 h) para **calidad
  del aire, congestión de tráfico y afluencia derivada** + clasificador de
  "episodio" por target. SHAP.
- **Tier 2 (el "wow")** — **GNN espacio-temporal** sobre el grafo Neo4j,
  multi-tarea, multi-horizonte. Importancia de aristas para explicabilidad.
- **Tier 4** — tool del asistente `*_prevista` servida desde ONNX;
  reentrenamiento nocturno; backtest incremental.

Realidad de datos (`NEXT_STEPS.md` §4): la ingesta en continuo arrancó el
2026-08-14 → ~2-4 semanas de histórico horario a la entrega. Modelo =
demostración de metodología con holdout temporal (últimos 3 días); ventana
corta = limitación declarada de §7.4. Los estudios de ablación de §7.3 sí
son viables con esa ventana.

## Tickets

| Ticket | Qué | Depende de |
|---|---|---|
| `ML_01` | `modelado/` esqueleto + **feature store** | 🟡 mayoría hecha — paneles reales de `calidad_aire`/`trafico` (ambos scopes) verificados; falta join meteo + festivos. `doc/ML-01` |
| `ML_02` | Splits temporales + **líneas base** + **módulo de métricas** | ✅ **HECHO** — `splits.py`/`baselines.py`/`metrics.py`/`run_baselines.py`, 16 tests. Suelo real medido (calidad_aire: persistencia MAE 2.74 a h1; trafico: climatología skill +0.74 a h6). `doc/ML-02` |
| `ML_03` | **Tier 1**: LightGBM multi-horizonte + episodio + SHAP | ✅ **HECHO** (regresión) — bate a la mejor baseline en los dos targets y todos los horizontes (calidad_aire h6 skill +0.68; trafico h6 +0.78). SHAP: `value_roll24h_mean` domina. Episodio -> ML_08. `doc/ML-03` |
| `ML_04` | **MLflow** tracking + model registry (params/metrics/artifacts, stages) | ✅ **HECHO** — `registry/mlflow_setup.py` (`configurar`/`log_run`/`marcar_champion`), `train_gbt.py --mlflow`. Backend SQLite local (coste 0). Verificado: 6 runs en `tier1`, 6 modelos registrados con alias `@champion`. `doc/ML-04` |
| `ML_05` | **Tier 2**: GNN espacio-temporal multi-tarea + multi-horizonte + importancia de aristas | ✅ **HECHO** — `stgnn.py` (GraphSAGE+GRU, capa a mano → importancia de aristas por gradiente, sin `torch_geometric`), `graph_snapshots.py`, `train_stgnn.py --mlflow tier2`. `calidad_aire`: bate a persistencia a h3/h6 (+0.48/+0.55), pierde a h1. `trafico` (1798 nodos): bate a persistencia en todos los horizontes (+0.39/+0.64/+0.79). Aristas interpretables. 2 modelos `@champion`. Multi-tarea real → `ML_08`. `doc/ML-05` |
| `ML_06` | **Evidently** — informe de deriva (train vs reciente) | ✅ **HECHO** — `evaluation/drift.py`: PSI+KS (numpy) + informe Evidently HTML/JSON (best effort). Real: solo las 3 features de día-de-semana con PSI>0.2 (artefacto de partición), señal estable. Ilustrativo (§7.4). `doc/ML-06` |
| `ML_07` | **ONNX** export del modelo registrado + test de paridad nativo↔ONNX + contrato de entrada documentado | ✅ **HECHO** — `export/to_onnx.py`; 4 `.onnx` (`calidad_aire_h{1,3,6}` + `trafico_h6`) desde el registry, paridad media 0.06–0.13 % (cola p99 = artefacto conocido del convertidor LightGBM), `export/CONTRATO.md`. STGNN→ONNX bloqueado por `torch.export` → §7.5. `doc/ML-07` |
| `ML_08` | **Cuadernos de evaluación §7** — baseline vs GBT vs GNN; + las 2 ablaciones de §7.3 (pendiente decisión 8) | ✅ **HECHO (estudios 1+2)** — `evaluation/estudios/` (`estudio_comparacion.py` + `run_all.py`), tablas + explicabilidad consolidadas a `artifacts/estudios/` + MLflow `tags.study=`. Ablaciones 3/4 descartadas (decisión 8). `doc/ML-08` |
| `ML_09` | **Tier 4**: tool del asistente `calidad_aire_prevista` / `afluencia_prevista` desde ONNX | `ML_07` |
| `ML_10` | **Tier 4**: reentrenamiento nocturno programado + backtest incremental (los datos crecen hasta la entrega) | `ML_04` |

## Reparto daemon vs interactivo (pendiente de confirmar)

Candidatos a la cola numerada del demonio (`NNN-*.md`, código puro,
`force: false`): esqueleto de `ML_01`, clases de modelo de `ML_03`/`ML_05`,
módulo de métricas de `ML_02`, SHAP/edge-importance. Quedan interactivos:
materializar features contra Athena real, entrenar, registrar en MLflow,
promover ONNX, desplegar la tool.
