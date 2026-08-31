---
kind: fil
title: "Mapa animado — capas ricas (ghost, panel de arista, pulso de distrito) + hosting"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
updated_at: "2026-08-30"
depends_on: [FIL_34]
milestone: M4
target: "2026-09-10"
---

## Alcance — capa rica (E2 / E4 / E6) + publicación

- **E2 — modelo vs baseline**: toggle que dibuja la persistencia
  (`y_traf_persist`) como capa atenuada; los nodos donde STGNN y persistencia
  divergen se resaltan. Marcador en una esquina con el skill del fotograma
  (MAE STGNN vs MAE persistencia sobre los nodos con lectura real esa hora).
- **E4 — panel glass-box de arista**: clic en un nodo → panel lateral con
  las curvas de previsión a 24 h (tráfico + aire IDW; ruido = línea plana
  diaria del distrito) + "explicado por: [nodo del top-15 de
  `importancia_aristas` que toca este] (importancia bruta N)". La
  importancia es **estática**; el panel lo dice.
- **E6 — pulso de distrito**: panel enlazado con los 21 distritos ordenados
  por índice de salud actual, barras que se reordenan con el reloj; clic →
  encuadra/filtra. El término de ruido del índice es constante en el día
  (diario por distrito) — el movimiento del ranking lo dan tráfico y aire.
- Layout: mapa al centro · izquierda controles + timeline · derecha panel de
  contexto con pestañas (arista / distrito) · abajo-izquierda ticker meteo +
  marcador de skill.
- **Hosting** — necesita **acción del usuario una vez**: habilitar GitHub
  Pages en `Settings → Pages` del repo `madrono-ucm/madronoTFM`. El repo usa
  `doc/` (no `docs/`) para la memoria → servir Pages desde **rama
  `gh-pages`** (o carpeta `docs/` nueva). `viz/build_mapa_animado.py`
  escribe el HTML + su JSON de datos + el bundle deck.gl vendorizado a esa
  ubicación. Enlace en `README.md` raíz + `viz/PROGRESO_MAPA.md`.
  Materializa el ítem de encuadre "**hosted endpoint**" (no una API).

## Coste

Cero AWS. GitHub Pages gratis y sin límite de CSP.

## Entregable / progreso

Milestone **M4** en `viz/PROGRESO_MAPA.md` — mapa "wow" completo y
**publicado en una URL**.

## Ampliación pendiente — capa social (`FIL_45`), bajo E6

- **Drill-down a barrio**: clic en un distrito del pulso → desglose por
  barrio (nodos agregados por barrio, ordenados por índice de salud), con
  el mismo criterio de agregado por zona.
- **Pie de guardarraíles** siempre visible en el panel: "agregados por
  zona, sin datos personales · previsión, no un mapa de estigma · apoyo a
  la decisión, no consejo médico".
