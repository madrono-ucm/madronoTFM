---
kind: fil
title: "trafico_prevista: exponer la previsión de congestión (LightGBM h1/h3/h6) como tool del MCP"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-08-30"
depends_on: []
---

> **✅ HECHO 30/8.** ONNX `trafico_h{1,3,6}` exportados + vendorizados; `prevision.py` generalizado a `target`; tool `trafico_prevista` + router `GET /trafico-prevista` + registrada en el servidor MCP (8 tools). Verificado en vivo (Retiro/Sol/Atocha, Athena+Neo4j reales). `doc/FIL-13-...md`. Tests en verde.

## Contexto

El asistente sólo tiene **una** tool que sirve previsión ML
(`calidad_aire_prevista`, ML_09, ONNX). Los modelos de tráfico
(`madrono-trafico-h{1,3,6}` en MLflow, `@champion`) están entrenados y baten
a la persistencia (`doc/ML-03`/`doc/ML-05`), pero ONNX sólo tiene
`trafico_h6` exportado (`modelado/export/artifacts/`) y nada vendorizado en
`asistente/modelos/`. Sin esto, "el MCP llama al ML" se demuestra con un
solo target.

## Objetivo

`trafico_prevista(zona|punto, horizonte, momento?)` como tool MCP, espejo de
`calidad_aire_prevista`: resuelve el/los punto(s) de tráfico cercanos vía
grafo, arma las features del panel para `momento`, corre el ONNX y devuelve
la previsión de `avg_service_level` a h1/h3/h6 con su clasificación
(fluido/denso/congestionado).

## Alcance

1. `modelado/export/to_onnx.py`: exportar también `trafico_h1` y `trafico_h3`
   (o justificar h6-only). Test de paridad nativo↔ONNX como los de
   `calidad_aire_*_paridad.json`.
2. Vendorizar los `.onnx` en `asistente/modelos/` (mismo patrón que ML_09).
3. `asistente/prevision.py`: generalizar la construcción de features para
   soportar el target `trafico` (lags de `avg_service_level`, meteo/previsión
   por proximidad, calendario). Reutilizar `exogenas.py` si aplica.
4. `asistente/mcp_agent/tools.py` + `asistente/routers/trafico_prevista.py`:
   la tool + su router HTTP, registrada en `server.py`.
5. Modelo Pydantic de respuesta en `asistente/models/herramientas.py`
   (`TraficoPrevista`), con `version_modelo`, `ventana_datos`, `generado_en`.

## Criterios de aceptación

- `trafico_prevista` registrada en el servidor MCP y con router HTTP.
- Verificada **en vivo** contra Athena real (con el pipeline congelado, los
  lags salen de la Gold ya presente): devuelve una previsión numérica
  plausible para un punto real y un `momento` dentro de la ventana de datos.
- Paridad ONNX documentada. Tests de la tool (mock de Athena/ONNX).
- `doc/FIL-13-...md` con el resultado.

## Restricciones

- No reabrir el entrenamiento (los `@champion` de tráfico ya existen).
- Credenciales AWS de SSM, nunca a disco.
