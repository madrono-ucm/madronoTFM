---
kind: fil
title: "Asistente: anclaje temporal a los días curados del mapa (ASSISTANT_ANCHOR_DATE)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_73, FIL_83]
milestone: "M7"
---

## Motivación (pedido del usuario)

El mapa animado muestra **3 días concretos** con datos reales
(`2026-08-19` laborable / `2026-08-23` domingo / `2026-08-26` miércoles
cargado). Las tools MCP, en cambio, usan el **reloj real** como referencia
cuando no se les pasa `momento`, y la ingesta está **congelada desde
2026-08-30** → la ventana "últimas ~48 h" cae vacía y devuelven "sin datos".
El usuario quiere que el MCP se centre en esos días para tener información.

## Hecho

- **`asistente/timeutils.py`**:
  - `DIAS_CURADOS = ("2026-08-19", "2026-08-23", "2026-08-26")` — el mismo
    trío que `viz/build_mapa_animado.py` y `asistente/modelos/grafo_ruta.json`.
  - `fecha_ancla()` — lee `ASSISTANT_ANCHOR_DATE` (YYYY-MM-DD) del entorno;
    `None` si no está o es inválida (con `warning`).
  - `ahora_o_ancla()` — el reloj real, salvo que `ASSISTANT_ANCHOR_DATE`
    esté puesta, en cuyo caso **esa fecha con la hora-del-día actual** (para
    que la dimensión "hora" siga variando), en tz de Madrid.
  - `dia_curado_mas_cercano(d)` — utilidad para snap.
- **`asistente/mcp_agent/tools.py`**: los 13 `instante = now_madrid()` (la
  rama `else` de `if momento is not None`) pasan a `instante =
  ahora_o_ancla()`. Un `momento` explícito del cliente **siempre gana**.
- **`server.py` `_INSTRUCCIONES`**: una línea para el LLM cliente — "sin
  momento, el asistente se ancla a un día curado; para otro, pásalo como
  `momento`".
- **Sin la env** (tests, desarrollo): comportamiento idéntico al de antes
  (`now_madrid()`).
- **Despliegue**: `ASSISTANT_ANCHOR_DATE=2026-08-26` en la unit
  `madrono-web.service` de la EC2 (runbook en `infra/OPERACION.md`).

## Verificación

- `asistente/tests/test_anclaje.py`: sin env = ahora; con env = esa fecha
  conservando la hora; env inválida se ignora; `calidad_aire` sin `momento`
  y con el ancla puesta consulta la fecha anclada en su SQL.
- Suite `asistente/` verde (225) con la env sin definir — sin cambio de
  contrato.
- En vivo tras el deploy: `/calidad-aire?zona=Retiro` devuelve lecturas
  reales del 2026-08-26 en vez de "sin datos".
