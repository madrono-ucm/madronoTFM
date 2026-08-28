---
kind: ml
title: "ONNX export del modelo registrado + paridad nativo<->ONNX + contrato de entrada"
owner: Filippos (interactive)
status: pending
depends_on: [ML_04]
created_at: "2026-08-28"
---

## Objetivo

Export ONNX que pide la memoria (§5.2/§5.4: ONNX como formato de despliegue
y portabilidad).

## Alcance

- `modelado/export/to_onnx.py`: toma un modelo del registry (`ML_04`) y lo
  exporta a ONNX.
  - LightGBM -> `onnxmltools` / `skl2onnx`.
  - GNN (PyTorch) -> `torch.onnx.export` (con `dynamic_axes` para el nº de
    nodos/aristas si el modelo es el GNN).
- **Test de paridad**: sobre un lote de validación, `max |ŷ_nativo -
  ŷ_onnx|` < tolerancia (documentar la tolerancia). Falla la tarea si no.
- **Contrato de entrada**: `modelado/export/CONTRATO.md` — nombres, orden,
  tipos y unidades de las features de entrada, y forma de la salida
  (`[horizonte, target]`), para que `ML_09` (la tool del asistente) lo
  consuma sin ambigüedad.
- Subir el `.onnx` como artefacto de la versión del modelo en MLflow.

## Criterios de aceptación

- `.onnx` generado para al menos el mejor modelo de calidad del aire.
- Test de paridad en verde, con la tolerancia anotada.
- `CONTRATO.md` completo.

## Restricciones

- `onnx`, `onnxruntime`, `skl2onnx`/`onnxmltools` a `modelado/requirements.txt`.
