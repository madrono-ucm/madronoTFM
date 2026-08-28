---
kind: ml
title: "Tier 4 — tool del asistente calidad_aire_prevista / afluencia_prevista desde ONNX"
owner: Filippos (interactive)
status: pending
depends_on: [ML_07]
created_at: "2026-08-28"
---

## Objetivo

Cerrar el bucle memoria §6.7 / §4.1 (observación -> predicción -> asistente):
una tool nueva del agente MCP que sirve la previsión desde el modelo ONNX.

## Alcance

- `asistente/`: nueva tool `calidad_aire_prevista(estacion|lugar, horizonte)`
  (y/o `afluencia_prevista`) — mismo patrón que las 6 tools actuales
  (`asistente/mcp_agent/tools.py` + router + registro en `server.py`).
- Carga el `.onnx` (de `ML_07`, artefacto de MLflow o `s3://.../models/`)
  con `onnxruntime`; construye el vector de features de entrada leyendo los
  mismos datos que el feature store (`ML_01`) para el instante actual,
  respetando `export/CONTRATO.md`.
- Respuesta trazable: veredicto (valor previsto + banda), nivel de fiabilidad
  según `data_completeness` de las features disponibles, y qué modelo/versión
  la produjo.
- Verificar en vivo (`GET /calidad-aire-prevista`) contra datos reales.

## Criterios de aceptación

- La tool responde con una previsión real desde el ONNX, verificada en vivo.
- `asistente/README.md` actualizado (7ª/8ª tool, ya ninguna con
  `NotImplementedError`).
- Tests: la tool construye el input correcto y parsea la salida ONNX (con un
  modelo ONNX de juguete o mock de `onnxruntime`).

## Restricciones

- `onnxruntime` a `asistente/requirements.txt`.
- La fiabilidad baja explícita cuando faltan features (mismo criterio que
  `afluencia_estimada`).
