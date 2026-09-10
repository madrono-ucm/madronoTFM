---
kind: fil
title: "Web: panel de control como barra lateral de botones (sin iconos, chat aparte, sobre el mapa)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_69, FIL_76]
milestone: "M7"
---

## Motivación (pedido del usuario)

1. Los nodos de deck.gl se colaban por encima de los paneles de control.
2. El chat vivía como un `<details>` más dentro del stack; se quería como
   su propio menú.
3. Las cabeceras de sección llevaban emoji (📖 ⏱ 🎨 ♿ 🧭 🚶 💬) — poco
   profesional.
4. Se quería que las secciones se muestren/oculten con botones, tipo barra
   lateral, en vez del acordeón de `<details>`.

## Hecho

- **Stacking**: `#map` pasa a `z-index:0` (crea su propio contexto de
  apilado, deja el canvas de deck.gl contenido); todos los `.panel` a
  `z-index:5`+, el rail a `7`. Fondo de panel opaco (`.95`) + borde +
  sombra → los nodos ya no se transparentan por debajo.
- **Barra lateral `#rail`**: `<nav>` con un botón por sección (Historia,
  Tiempo, Capa de color, Salud, Vista, Ruta saludable, **Asistente**). Al
  pulsar un botón se muestra su sección y se ocultan las demás (una
  visible a la vez); volver a pulsar el botón activo cierra el panel.
  `mkRail()` en el JS; `aria-expanded` por botón; al abrir "Asistente" el
  foco va al input del chat.
- **Acordeón fuera**: los 7 `<details>/<summary>` pasan a
  `<section class="sec" data-sec="…">` con `<h3>` de cabecera **sin emoji**.
  Todos los `id`/`class` internos intactos → `mkControls`/`mkHistoria`/
  `mkChat` y los tests jsdom siguen igual.
- **Chat = sección propia** (`data-sec="chat" id="g-chat"`), con su botón
  "Asistente" en el rail.
- Botones del recorrido guiado: `◀`/`▶ animar`/`▶` → `Anterior`/`Animar`/
  `Siguiente` (texto). Capítulo 2 del guion: «▶ animar» → «Animar».
- `vista limpia` ahora también atenúa el rail.
- Media query `<=640px`: el rail se pone horizontal y el panel debajo.

## Verificación

- `tests/test_mapa_animado.py` (18, +`test_panel_es_barra_lateral_sin_iconos`)
  + `viz/test/mapa.test.mjs` jsdom (3, ahora también abre cada sección del
  rail) verdes. Suite `tests/` + `viz/` completa (48).
- Playwright/Chromium: rail con los 7 botones, "Asistente" abre el chat y
  enfoca el input, doble clic en un botón cierra el panel, sin errores de
  página; los nodos quedan por debajo de los paneles.
- Republicado en `gh-pages`.
