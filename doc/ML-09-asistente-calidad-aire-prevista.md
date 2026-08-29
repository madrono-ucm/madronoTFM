# ML-09 — Tool del asistente `calidad_aire_prevista` (previsión desde ONNX)

Cierra el bucle de la memoria **§6.7 / §4.1**: observación → predicción →
asistente. La 7ª tool del agente MCP sirve una **previsión** de calidad del
aire corriendo el modelo ONNX de `ML_07`.

## Qué se creó

- **`asistente/prevision.py`** — puro y testable:
  - `FEATURES` — las 19 features de `modelado/export/CONTRATO.md` en orden.
  - `construir_features(actual, historial, *, instante, lat, lon, festivos)`
    → `(vector[19], data_completeness)`. Lags 1/2/3/24 h + rolling 3 h/24 h
    (media y desv. típica muestral, igual que `pandas.rolling().std()`) +
    calendario. **NaN → 0.0** (igual que el test de paridad de `ML_07`).
    `data_completeness` = fracción de {valor actual, lag 1/2/3/24 h} real.
  - `predecir(vector, *, horizonte)` — `onnxruntime` sobre
    `asistente/modelos/calidad_aire_h{1,3,6}.onnx` (sesiones cacheadas).
- **`asistente/modelos/calidad_aire_h{1,3,6}.onnx`** — copia vendida de los
  artefactos de `modelado.export.to_onnx` (el servicio no importa
  `modelado/`).
- **`asistente/mcp_agent/tools.py::calidad_aire_prevista(zona, horizonte_horas=6, momento=None)`**
  - resuelve `zona` por texto sobre `station_name`/`station_id` (igual que
    `calidad_aire`), lee las últimas ~25 h de
    `gold.calidad_aire_por_estacion_contaminante_hora` (Athena),
  - elige `(estación, contaminante)` por mayor ratio frente al límite de
    referencia (peor caso, mismo criterio que `calidad_aire`),
  - **ancla el forecast en la última hora con lectura real** (Gold va con
    varias horas de retraso; anclar en "ahora" dejaba el vector casi todo a
    cero → predicción degenerada — bug detectado en la verificación en vivo
    y corregido),
  - construye las features, corre el ONNX, devuelve `CalidadAirePrevista`
    (`valor_previsto`, `valor_actual`, `nivel_previsto` = índice
    simplificado, `data_completeness`, `modelo`).
- **`asistente/routers/calidad_aire_prevista.py`** — `GET /calidad-aire-prevista`
  → `RespuestaAsistente` trazable; `fiabilidad` MEDIA (tope, por la ventana
  de datos corta §7.4) si `data_completeness ≥ 0.8`, BAJA si no; `sin_datos`
  / sin-modelo devuelven BAJA sin excepción.
- Registrada en `asistente/mcp_agent/server.py` y `asistente/main.py`
  (v0.8.0). `onnxruntime` + `numpy` en `asistente/requirements.txt`.
- **`asistente/tests/test_calidad_aire_prevista.py`** — 9 tests (orden de
  features, math de lags/rolling, `data_completeness`, ONNX real devuelve
  finito, tool con Athena mockeada, horizonte inválido, `sin_datos`, router
  trazable). `test_mcp_tools.py` actualizado a 7 tools.
  `python -m pytest asistente/ -q` → **74 passed**.

## Verificación en vivo (Athena real, `AWS_PROFILE=madrono`)

`tools.calidad_aire_prevista(zona, h)` contra Gold real (ancla 2026-08-28
15:00, la última hora con datos):

| zona | contaminante | actual | previsto h1 | previsto h6 | `data_completeness` |
|---|---|---|---|---|---|
| Parque del Retiro | O₃ | 97 | 86.9 | 30.4 | 0.8 |
| Escuelas Aguirre | O₃ | 96 | 87.0 | 30.4 | 0.8 |
| Barrio del Pilar | O₃ | 96 | 86.4 | 29.8 | 0.8 |
| Castellana | PM10 | 12 | 9.6 | 8.1 | 0.8 |

Coherente: el O₃ a 6 h vista (anclado a las 15:00 → 21:00) **cae con
fuerza** (97 → ~30), que es el ciclo diurno real del ozono (pico de tarde,
desplome al anochecer); PM10 se mantiene plano y bajo. `nivel_previsto`
= "buena" en todos (ratio < 0.5 del límite de referencia).

## Criterios de aceptación

- [x] La tool responde con una previsión real desde el ONNX, verificada en
  vivo contra Athena.
- [x] `asistente/README.md` actualizado (7ª tool; ninguna con
  `NotImplementedError`).
- [x] Tests: construye el input correcto y parsea la salida ONNX (modelo
  real + Athena mockeada).
- [x] `onnxruntime` en `asistente/requirements.txt`.
- [x] Fiabilidad baja explícita cuando faltan features
  (`data_completeness`).

## Notas / futuras líneas

- La previsión se ancla al último dato de Gold, no a la hora del reloj:
  cuando la latencia de Gold baje, el horizonte efectivo se acerca al
  nominal.
- `festivos` se deja en `frozenset()` vacío (misma laguna que el feature
  store de `ML_01`); cuando `ML_01` haga el join real con
  `calendario_laboral_madrid`, pasarlo aquí también.
- `afluencia_prevista` desde ONNX: pendiente de que el STGNN exporte a ONNX
  (`ML_07`, bloqueado por `torch.export`) o de un modelo de árbol para
  `afluencia` (el panel ya existe, `_TARGETS["afluencia"]` en
  `modelado/features/build.py`).
