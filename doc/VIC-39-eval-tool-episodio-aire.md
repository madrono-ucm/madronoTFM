# VIC_39 — QA de `calidad_aire_episodio` (FIL_79, 2026-09-10)

Verificación de la 16.ª (hoy una de las 19) herramientas MCP:
P(superación de umbral OMS/UE) del contaminante más crítico de una
estación, derivada de la previsión de regresión existente
(`calidad_aire_prevista`) vía una logística sobre el margen normalizado.

## 1. Monotonía y rango — ✅ correcto, ya cubierto por tests reales

`asistente/tests/test_episodio.py::ProbSuperacionTests` ya prueba
exactamente lo que pedía el ticket: `P` estrictamente creciente en `ŷ`
sobre un barrido de 24 valores, acotada en `(0,1)`, `P(ŷ=umbral)≈0.5`
(6 decimales), y el signo del veredicto coherente con `P ≷ 0.5`
(`test_por_debajo_y_por_encima`). No hizo falta añadir ningún test nuevo.

## 2. Umbrales — ⚠️ correctos hoy, pero duplicados en 4 sitios sin módulo compartido

La premisa del ticket ("los umbrales de la tool = los de
`asistente/umbrales.py` = los del mapa") es falsa como está escrita: **ese
módulo no existe**. Los valores de NO2 (200 µg/m³) y O3 (180 µg/m³) están
hoy repetidos, coincidiendo, en cuatro ficheros independientes:
`asistente/mcp_agent/tools.py::_LIMITES_REFERENCIA_UGM3`,
`viz/build_mapa_animado.py` (cortes de banda `[25,40,100,200]` /
`[100,120,180,240]`), `viz/build_grafo_ruta.py::_NORM` y
`viz/rutas.py::_NORM`. Ningún test detectaría una divergencia futura entre
ellos. No es un bug hoy — los cuatro sitios están de acuerdo — pero es
deuda real. Abierto `FIL_87` para extraer un módulo único.

## 3. Registro de la tool — ✅ ya consistente en todos los sitios

A fecha de hoy el recuento real ya es **19** (no 15/16 como asumía el
ticket original, que se escribió antes de que `FIL_80`–`83` aterrizaran).
Verificado uno a uno: `server.py` (`_TOOLS`, `_INSTRUCCIONES` la menciona
por nombre), `test_mcp_tools.py::TOOL_FUNCTIONS` la incluye,
`test_mcp_transport.py::_ESPERADAS` la incluye y
`test_list_tools_expone_las_19` ya está renombrado al número real (no
quedó ningún `_las_16`), `asistente/README.md` tiene su fila. El `README.md`
raíz no nombra tools individuales (usa «…» tras varios ejemplos), consistente
con su propio estilo — no hace falta añadirla ahí.

## 4. Fiabilidad ante el pipeline congelado — ✅ correcto

El router (`asistente/routers/calidad_aire_episodio.py`) fija
`fiabilidad=NivelFiabilidad.BAJA` en **ambas** ramas (con y sin previsión
disponible), coherente con el docstring de `CalidadAireEpisodio`
("Fiabilidad **BAJA** (§7.4 + pipeline congelado)"). La rama sin datos
además explica el motivo real (`r.motivo`) en la explicación devuelta al
usuario, no solo en un campo interno.

## 5. Exposición en el chat — ✅ ya expuesta

`asistente/chat.py::_TOOLS_CHAT` ya incluye `"calidad_aire_episodio"` con
una descripción propia para el LLM. Coherente con la recomendación del
ticket (es conversacional, no requiere parámetros técnicos del grafo).

## Verificación

`pytest asistente/tests/test_episodio.py asistente/tests/test_mcp_tools.py
asistente/tests/test_mcp_transport.py` → 44 passed, 57 subtests, en verde.

## Veredicto

Herramienta correcta y bien integrada. Único hallazgo real: duplicación de
constantes de umbral sin módulo compartido (`FIL_87`, prioridad baja, no
bloqueante para el 17/9).
