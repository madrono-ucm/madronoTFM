---
kind: vic-eval
title: "QA — anclaje temporal del asistente (FIL_84): un momento explícito gana, sin env no cambia nada"
owner: Claude (QA)
status: pending
depends_on: [FIL_84]
created_at: "2026-09-10"
---

## Contexto

FIL_84 añade `ASSISTANT_ANCHOR_DATE` + `ahora_o_ancla()` en
`asistente/timeutils.py`, y cambia 13 sitios de `tools.py` de
`now_madrid()` a `ahora_o_ancla()`.

## Alcance — verificación

1. **`momento` explícito siempre gana**: para cada tool con `momento`,
   pasar una fecha ≠ ancla y ≠ hoy y comprobar que la SQL / la lógica usa
   esa fecha, con y sin `ASSISTANT_ANCHOR_DATE` puesta.
2. **Sin env, cero cambio**: `grep` de que ningún test hardcodea una fecha
   "de hoy" que ahora se desvíe; la suite `asistente/` pasa igual con la
   env sin definir. `ahora_o_ancla() == now_madrid()` cuando no hay env.
3. **Los 13 sitios**: `grep -n "now_madrid()" asistente/mcp_agent/tools.py`
   → 0 (todos migrados); `now_madrid` sigue importado solo si se usa (no lo
   usa → import retirado). Ningún `instante = ahora_o_ancla()` fuera de la
   rama `else` de `if momento is not None`.
4. **`DIAS_CURADOS`** coincide **exactamente** con
   `viz/build_mapa_animado.py` y `asistente/modelos/grafo_ruta.json`
   (mismo trío, mismo orden). Un solo sitio canónico sería mejor — anotar
   si merece un FIL de deduplicación.
5. **Hora-del-día**: `ahora_o_ancla()` conserva `hour`/`minute` del reloj
   real (no los pone a 00:00) — importante para las tools que eligen "la
   hora más reciente con dato".
6. **`_INSTRUCCIONES`**: menciona el anclaje y cómo consultar otro día
   curado (`momento`).
7. **Interacción con la caché (FIL_83)**: con `ASSISTANT_CACHE_TTL` puesto,
   la clave de `run_athena_query` incluye la fecha anclada → no hay
   colisión entre "hoy" y el día anclado.

## Criterios de aceptación

- Tests de FIL_84 verdes + un caso por tool de "momento explícito gana".
- Suite `asistente/` verde con y sin `ASSISTANT_ANCHOR_DATE`.
- `infra/OPERACION.md` documenta la env y el valor de despliegue.
