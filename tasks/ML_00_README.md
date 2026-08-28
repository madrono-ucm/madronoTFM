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
| `ML_01` | `modelado/` esqueleto + **feature store** (Athena→Parquet, panel horario por estación sin fugas) | fundación de datos (`FIL_*`, hecha) |
| `ML_02` | Splits temporales + **líneas base** (persistencia, climatología horaria, seasonal-naive) + **módulo de métricas** (MAE/RMSE, skill vs persistencia, por horizonte y tipo de nodo; PR-AUC de cruce de umbral) | `ML_01` |
| `ML_03` | **Tier 1**: LightGBM multi-horizonte (AQ, congestión, afluencia) + clasificadores de episodio + SHAP | `ML_02` |
| `ML_04` | **MLflow** tracking + model registry (params/metrics/artifacts, stages) | `ML_02` |
| `ML_05` | **Tier 2**: GNN espacio-temporal multi-tarea + multi-horizonte + importancia de aristas | `ML_02`, grafo real (hecho) |
| `ML_06` | **Evidently** — informe de deriva (train vs reciente) | `ML_01` |
| `ML_07` | **ONNX** export del modelo registrado + test de paridad nativo↔ONNX + contrato de entrada documentado | `ML_04` |
| `ML_08` | **Cuadernos de evaluación §7** — baseline vs GBT vs GNN; + las 2 ablaciones de §7.3 (pendiente decisión 8) | `ML_03`, `ML_05` |
| `ML_09` | **Tier 4**: tool del asistente `calidad_aire_prevista` / `afluencia_prevista` desde ONNX | `ML_07` |
| `ML_10` | **Tier 4**: reentrenamiento nocturno programado + backtest incremental (los datos crecen hasta la entrega) | `ML_04` |

## Reparto daemon vs interactivo (pendiente de confirmar)

Candidatos a la cola numerada del demonio (`NNN-*.md`, código puro,
`force: false`): esqueleto de `ML_01`, clases de modelo de `ML_03`/`ML_05`,
módulo de métricas de `ML_02`, SHAP/edge-importance. Quedan interactivos:
materializar features contra Athena real, entrenar, registrar en MLflow,
promover ONNX, desplegar la tool.
