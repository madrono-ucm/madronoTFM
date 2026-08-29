---
kind: ml
title: "Tier 4 — tool del asistente calidad_aire_prevista / afluencia_prevista desde ONNX"
owner: Filippos (interactive)
status: done
depends_on: [ML_07]
created_at: "2026-08-28"
---

> **Estado 29/8: ✅ HECHO (`calidad_aire_prevista`).** `asistente/prevision.py`
> (features de CONTRATO.md + `onnxruntime`) + tool + router
> `GET /calidad-aire-prevista` + registro MCP/FastAPI (v0.8.0).
> `.onnx` de `ML_07` vendido en `asistente/modelos/`. **Verificado en vivo**
> contra Athena real: O₃ Retiro 97 → h6 30.4 (ciclo diurno real del ozono),
> PM10 Castellana 12 → 8.1. `data_completeness` baja la fiabilidad. Ancla el
> forecast en la última hora con dato (bug de "anclar en ahora" detectado y
> corregido en la verificación). `onnxruntime`+`numpy` en requirements.
> 74 tests del asistente en verde (+9). `doc/ML-09`.
> `afluencia_prevista` → pendiente (STGNN sin ONNX, `ML_07`).

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
