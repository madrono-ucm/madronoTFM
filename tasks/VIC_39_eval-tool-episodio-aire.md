---
kind: vic-eval
title: "QA — tool calidad_aire_episodio (FIL_79): probabilidad vs veredicto, umbrales, registro"
owner: Claude (QA)
status: pending
depends_on: [FIL_79]
created_at: "2026-09-10"
---

## Contexto

FIL_79 añade `calidad_aire_episodio` (16.ª tool) — P(superación de umbral)
por contaminante y horizonte, sobre la previsión de regresión + una
logística calibrada.

## Alcance — verificación, sin cambios de lógica

1. **Monotonía y rango**: para ŷ creciente, P creciente y ∈ [0,1]; ŷ = umbral
   → P ≈ 0.5; veredicto determinista coherente con P ≷ 0.5.
2. **Umbrales**: los de la tool = los de `asistente/umbrales.py` = los del
   mapa (`viz/build_mapa_animado.py`). Un solo módulo, sin números sueltos
   duplicados. `grep` por `[25, 40, 100, 200]` / `[100, 120, 180, 240]`.
3. **Registro 15→16**: `server.py` (`_TOOLS`, texto "N tools"),
   `test_mcp_tools`, `test_mcp_transport` (`_ESPERADAS`,
   `test_list_tools_expone_las_16`), `asistente/README.md` (fila nueva),
   `README.md` raíz, `asistente/mcp_agent/server.py::_INSTRUCCIONES`.
4. **Fiabilidad**: la tool devuelve BAJA con `motivo` (§7.4 + freeze); el
   router lo refleja en la `RespuestaAsistente`.
5. **Chat**: `_TOOLS_CHAT` en `asistente/chat.py` — ¿debe exponerla? (sí,
   es conversacional y graph-first-adjacent).

## Criterios de aceptación

- `grep -rn "15 tool\|15 herramientas\|las 15"` → 0 obsoletos.
- Tests de FIL_79 verdes + un caso de propiedad (monotonía) explícito.
- Sin dobles definiciones de umbrales OMS/UE en el repo.
