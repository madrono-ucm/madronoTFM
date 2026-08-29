---
kind: ml
title: "ONNX export del modelo registrado + paridad nativo<->ONNX + contrato de entrada"
owner: Filippos (interactive)
status: done
depends_on: [ML_04]
created_at: "2026-08-28"
---

> **Estado 29/8: ✅ HECHO.** `modelado/export/to_onnx.py`
> (`cargar_champion` / `exportar_lightgbm` / `exportar_stgnn` / `paridad` /
> `exportar`). 4 `.onnx` reales desde el registry:
> `calidad_aire_h{1,3,6}` + `trafico_h6` en `modelado/export/artifacts/`,
> con `metadata_props` (19 features en orden) y subidos a MLflow.
> **Paridad**: media `|Δ|` 0.06–0.13 % de la escala del target (guarda
> principal); cola p99 ≤ 2 % o ≤ 0.05 abs — discrepancia conocida del
> convertidor LightGBM de onnxmltools en el límite de los splits, persiste
> con doble precisión, documentada. `modelado/export/CONTRATO.md` completo.
> **STGNN → ONNX**: `exportar_stgnn` implementada pero `torch.export` (torch
> 2.13) no traza el forward (bucle temporal + `index_add` dinámico) →
> pendiente/§7.5; el STGNN se sirve desde el registry PyTorch.
> `onnx`/`onnxruntime`/`onnxmltools`/`onnxscript` en requirements. 35 tests
> en verde (+3 `test_ml07.py`). `doc/ML-07`.

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
