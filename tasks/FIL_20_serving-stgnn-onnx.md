---
kind: fil
title: "Serving del STGNN — investigar una ruta de export/serving (opcional, §7.5)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
resolved_at: "2026-08-30"
---

Bullet opcional de `doc/PLAN-REVISION-TFM.md` ("sólo si sobra tiempo").
La memoria daba el STGNN por no servible vía ONNX (§7.5).

## Resolución (2026-08-30)

**El STGNN SÍ se exporta a ONNX** con `torch.onnx.export(dynamo=True)`
(torch ≥ ~2.6). Paridad `max |Δ| ≈ 6e-8` (epsilon `float32`), verificada
también con un grafo y un nº de nodos distintos a los del ejemplo (nodos y
aristas quedan como ejes dinámicos reales). El exportador TorchScript legacy
—el que probaba el código antiguo— fallaba / daba paridad ~0.12.

- `modelado/export/to_onnx.py`: `exportar_stgnn` reescrita (dynamo, ya no
  *best effort*), `paridad_stgnn`, `exportar_stgnn_desde_registry` +
  `--stgnn` en el CLI (carga el champion pytorch, arma una ventana de test
  con `train_stgnn._preparar`, exporta con paridad `tol 1e-4`).
- `modelado/tests/test_ml07.py::StgnnOnnxExportTests` (export sintético +
  paridad + nodos dinámicos, `skipUnless(torch)`).
- `modelado/export/CONTRATO.md`: sección STGNN reescrita (contrato
  `x_seq/edge_index/edge_weight` → `y [N,3,1]` estandarizado).

**No** se integra como tool del asistente: el contrato de entrada (ventana
de snapshots de grafo + estandarización aparte) es mucho más pesado que el
vector de 19 features, y `calidad_aire_prevista`/`trafico_prevista`
(LightGBM) ya cubren la demo §6.7. Queda como trabajo aditivo.

Efecto memoria: la limitación §7.5 "STGNN no servible por ONNX" ya no
aplica → redacción corregida en `doc/FIL-20-...md` (para `VIKT_07`/`VIKT_10`).
