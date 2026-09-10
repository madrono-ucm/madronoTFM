---
kind: fil
title: "MCP: tool de probabilidad de episodio de contaminación (superación de umbral OMS/UE)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_26, ML_03, ML_09]
milestone: "M7"
target: "2026-09-20"
---

## Motivación

Auditoría de arquitectura (2026-09-10): los 8 modelos de regresión
(LightGBM + STGNN, tráfico/aire, h1/h3/h6) están servidos, pero **ninguna
tool responde la pregunta que de verdad importa para decidir**: "¿va a haber
un episodio (superación de umbral) de NO₂/O₃ en las próximas N horas y con
qué probabilidad?". El clasificador GBT de `ML_03`
(`modelado/models/gbt.py`, `objective=binary`) existe pero no se exporta ni
se sirve.

## Alcance

1. **`calidad_aire_episodio(zona, contaminante, horizonte_horas)`** — 16.ª
   tool MCP + `GET /calidad-aire-episodio`.
   - Vía sin artefacto nuevo (recomendada para arrancar): corre la previsión
     de regresión ya existente (`asistente/prevision.py`) para el
     contaminante, y transforma la distancia al umbral en probabilidad con
     una logística calibrada por la desviación del residuo del backtest
     (`P = σ((ŷ − umbral)/s)`), s de `ML_08`/`FIL_38`. Devuelve también el
     veredicto determinista (ŷ ≷ umbral) y el umbral aplicado
     (guía OMS 24 h / límite UE, por contaminante).
   - Umbrales: reutiliza `viz/build_mapa_animado.py::_meta()::umbrales`
     (NO₂ 25/40/200, O₃ 100/120/180…) — extraerlos a un módulo compartido
     `asistente/umbrales.py` (única fuente de verdad, la usan mapa + tool).
2. **Opción B (follow-up, si sobra tiempo)**: exportar el clasificador GBT a
   ONNX (`modelado/export/to_onnx.py` ya tiene el flujo) y servir
   `predict_proba` real en vez de la logística sobre la regresión. Dejar
   la interfaz de la tool igual para poder cambiar por dentro.
3. **Fiabilidad**: BAJA (§7.4 — ventana de entrenamiento corta, pipeline
   congelado); el `motivo` lo dice.
4. `contexto_urbano` y el chat deben poder llamarla.

## Verificación

- `asistente/tests/test_episodio.py`: la logística es monótona en ŷ,
  P∈[0,1], veredicto coherente con P≷0.5, sin red (previsión mockeada).
- Registrada (16 tools) — actualizar `server.py` `_TOOLS`/`_ANOTACIONES`,
  `test_mcp_tools`, `test_mcp_transport`, `asistente/README.md`.
- `curl` en vivo: "probabilidad de episodio de O₃ cerca de Retiro a 6 h".
