---
kind: fil
title: "Mapa animado — capas ricas (ghost, panel de arista, pulso de distrito) + hosting"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-08-30"
depends_on: [FIL_34]
milestone: M4
---

## Alcance — capa rica (E2 / E4 / E6) + publicación

- **E2 — modelo vs baseline**: toggle que dibuja la persistencia como capa
  atenuada; las celdas donde STGNN y persistencia divergen se resaltan.
  Marcador en una esquina con el skill del fotograma actual.
- **E4 — panel glass-box de arista**: clic en un nodo/corredor → panel
  lateral con las curvas de previsión a 24 h (tráfico/aire/ruido) +
  "explicado por: [corredor aguas arriba] (importancia 0.42)" de la
  importancia de aristas del STGNN.
- **E6 — pulso de distrito**: panel enlazado con los 21 distritos ordenados
  por índice de salud actual, las barras se reordenan con el reloj; clic →
  encuadra/filtra a ese distrito.
- Layout: mapa al centro · izquierda controles + timeline · derecha panel de
  contexto con pestañas (arista / distrito) · abajo-izquierda ticker meteo +
  marcador de skill.
- **Hosting**: publicar `viz/mapa_trafico_madrid.html` en **GitHub Pages**
  (`docs/` o rama `gh-pages`), enlace en `README.md` raíz + `viz/PROGRESO_MAPA.md`.
  Esto materializa el ítem de encuadre "**hosted endpoint**" (no una API de
  producción).

## Coste

Cero AWS. GitHub Pages es gratis y sin límite de CSP.

## Entregable / progreso

Milestone **M4** en `viz/PROGRESO_MAPA.md` — mapa "wow" completo y
**publicado en una URL**.
