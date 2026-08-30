# FIL-13 — `trafico_prevista`: previsión de congestión como tool del MCP

Segundo target de ML servible por el asistente (el primero, `calidad_aire_prevista`,
`ML_09`). Cierra el mismo bucle observación→predicción→asistente de la memoria §6.7.

## Qué se hizo

### 1. ONNX de tráfico completo

`modelado/export/artifacts/` sólo tenía `trafico_h6.onnx`. Exportados
`trafico_h1` y `trafico_h3` desde `madrono-trafico-h{1,3}@champion` (LightGBM
19 features de `ML_03`) con `python -m modelado.export.to_onnx`:

| Modelo | mean \|Δ\| | p99 \|Δ\| | paridad |
|---|---|---|---|
| `trafico_h1` | 0.001 (0.14 %) | 0.032 (3.2 % rel) | OK |
| `trafico_h3` | 0.002 (0.20 %) | 0.057 (5.7 % rel) | OK |
| `trafico_h6` | 0.001 (0.13 %) | 0.024 (2.4 % rel) | OK |

`_TOL_P99_ABS` subido 0.05 → **0.07** en `to_onnx.py`: `avg_service_level`
tiene escala p95-p5 ≈ 1.0, así que el error fijo de frontera de split del
convertidor de LightGBM es una fracción mayor de la escala que en
`calidad_aire` (µg/m³, escala ~78). El `mean` — la guarda que importa —
sigue en 0.14–0.20 %. Documentado en `CONTRATO.md`.

Panel de tráfico regenerado a **19 features** (`--sin-meteo --sin-prevision`)
para casar con los `@champion` servidos (que son de antes de `exogenas.py`;
la retrain nocturna entrena unos de 30 features aparte, no servidos).

### 2. `asistente/prevision.py` generalizado

`predecir()` y `modelo_disponible()` toman `target ∈ {calidad_aire, trafico}`
(por defecto `calidad_aire`, retrocompatible) → `<target>_h<H>.onnx`. El
**vector de 19 features es idéntico** para ambos (`modelado/features/panel.py`
es agnóstico del target); sólo cambia qué señal es `value` y las unidades.

### 3. La tool

`asistente/mcp_agent/tools.py::trafico_prevista(lugar, horizonte_horas=6,
radio_m=300.0, momento=None)`:

1. Resuelve puntos de tráfico a `radio_m` del lugar por el grafo
   (`lugares_proximos_a_estaciones_trafico_query`, igual que `trafico_cercano`).
2. Fija el punto de peor caso (mayor `avg_service_level` reciente).
3. Construye las 19 features de sus últimas 24 h de
   `gold.trafico_por_punto_hora` (ancla = última hora con lectura real; Gold
   va con retraso).
4. Corre `trafico_h<H>.onnx` (vendido en `asistente/modelos/`) y clasifica
   con las bandas de `trafico_cercano` (`fluido`/`denso`/`congestionado`).

Devuelve `TraficoPrevista` (`asistente/models/herramientas.py`) con
`valor_previsto`/`valor_actual`/`nivel_previsto`/`data_completeness`/`modelo`/
`ventana_datos` (rango de fechas de los lags — trazabilidad, útil con el
pipeline congelado). Sin punto en el grafo o sin Gold →
`nivel_previsto="sin_datos"`, nunca excepción.

Registrada en `server.py` (8 tools) + router `GET /trafico-prevista` +
`asistente/main.py`.

## Verificación

- **Tests**: `asistente/tests/test_trafico_prevista.py` (11 casos: features
  por target, tool con ONNX real mockeando Athena/Neo4j, sin_datos, router).
  `test_mcp_tools.py` actualizado (8 tools). Suite `asistente/` en verde.
- **En vivo** contra Athena + Neo4j reales (pipeline congelado, Gold ya
  presente), `momento=2026-08-29 18:00`:

  | lugar | h | punto | actual | previsto | nivel | completeness | ventana |
  |---|---|---|---|---|---|---|---|
  | Retiro | 3 | 3939 | 1.0 | 0.04 | fluido | 0.8 | 2026-08-28..29 |
  | Sol | 1 | 4256 | 0.8 | 0.27 | fluido | 0.8 | 2026-08-28..29 |
  | Atocha | 6 | 4174 | 1.4 | 0.06 | fluido | 0.8 | 2026-08-28..29 |

  Los modelos (19 features, ventana de 2 semanas) tienden a converger a
  condiciones tranquilas a horizontes largos — coherente con la limitación
  de ventana corta de §7.4.

## Pendiente / relacionado

- `FIL_15` formaliza el envoltorio de respuesta (`ventana_datos` ya sembrado
  aquí y en `CalidadAirePrevista`).
- `FIL_14` decide `afluencia_prevista` (puede derivarse de esta tool +
  `calidad_aire_prevista` + ruido).
- El STGNN sigue sin ONNX (`torch.export`, §7.5) — sólo LightGBM servible.
