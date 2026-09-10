---
kind: fil
title: "Web: publicar el recorrido guiado del mapa + el explorador del grafo en vivo"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_67, FIL_69, FIL_70]
milestone: "M7"
target: "2026-09-18"
---

## Motivación

FIL_69 (recorrido guiado + rutas céntricas + chat en `viz/mapa/`) y FIL_67
(explorador del grafo en vivo) están hechos y verdes en local/CI, pero
**no están publicados**. La versión que ve un tribunal / un enlace público
sigue siendo la anterior. El flujo de publicación existe (FIL_42,
`gh-pages`), solo hay que ejecutarlo con los artefactos nuevos y comprobar
en un navegador real.

## Alcance

1. **Regenerar artefactos** — `python viz/build_mapa_animado.py` y
   `python viz/build_grafo_explorador.py --live`; confirmar que
   `viz/mapa/` y `viz/grafo_explorador_live.html` quedan al día.
2. **`API_BASE` / `?api=`** — verificar que en `gh-pages` el mapa apunta a
   la EC2 pública (`https://35-42-164-183.nip.io`) y el explorador a sus
   endpoints `/grafo/explorador/*`. El chat del mapa debe funcionar desde
   la página publicada (CORS ya abierto en `main.py`; el mapa servido
   también desde `/mapa` en el propio asistente como alternativa mismo
   origen).
3. **Publicar** con el flujo FIL_42 a `gh-pages` (rama del repo público).
4. **QA en navegador real** (no jsdom): abrir la URL publicada en
   Chrome/Firefox y recorrer los 6 capítulos de la Historia, cambiar
   día/hora/métrica/ruta, lanzar 3 preguntas al chat, abrir el explorador y
   sus 6 vistas + una ruta entre 2 puntos. Screenshots.
5. **Enlaces** — actualizar `README.md` / `viz/PROGRESO_MAPA.md` con las
   URLs vivas.

## Riesgos

- El explorador en vivo depende de que la EC2 y Neo4j estén arriba; si
  Neo4j cae, el explorador muestra 503 con botón de reintento (ya
  implementado) — documentarlo como comportamiento esperado.
- La instancia AuraDB gratuita se pausa por inactividad; puede haber una
  primera carga lenta.

## Verificación

- URL pública del mapa con la Historia y el chat operativos.
- URL pública del explorador con datos reales de Neo4j.
- `viz/test/mapa.test.mjs` y `tests/test_grafo_explorador.py` verdes antes
  de publicar.

## Hecho (2026-09-10)

- **Mapa en `gh-pages`**: ya trae el recorrido guiado + chat de `FIL_69`
  (publicado con el arreglo de `FIL_94`) y ahora el **capítulo 6 enlaza al
  explorador en vivo** (`<a href=".../grafo/explorador">`, regenerado y
  republicado). `gh-pages/index.html` == `main:viz/mapa/index.html`
  (verificado por hash).
- **Explorador en vivo**: NO necesita copia en `gh-pages` — el asistente lo
  sirve en `GET /grafo/explorador` (mismo origen que `/grafo/explorador/*`,
  detrás del Basic Auth `demo`/`demo` de nginx). Enlazado desde el mapa y
  el `README`.
- **QA headless de la EC2** (2026-09-10): `/health` 200, `/grafo/explorador`
  200 (HTML), `/grafo/explorador/data` 200 (2,67 MB, **9 657 nodos**),
  `/grafo/explorador/analisis` 200 (`sin_aire_cerca` 4 525 / 4 705). El
  backend y Neo4j están arriba.
- **Enlaces**: `README.md` + `viz/PROGRESO_MAPA.md` actualizados con las dos
  URLs vivas.
- `tests/test_grafo_explorador.py` (7) y `viz/test/*` (25) verdes.

## Pendiente (pasos de operación, fuera de esta sesión)

1. **Redesplegar la EC2** — el asistente sirve un build **anterior**
   (`/health` sin el campo `chat` de `FIL_73`; el HTML de
   `/grafo/explorador` sin el panel de chat de `FIL_68` ni los estados de
   `FIL_75`). `git pull` + `systemctl restart madrono-web.service` en
   `i-0aa45f0df26b4b7e6` recoge FIL_68/71/72/73/75/93. Runbook:
   `infra/OPERACION.md`.
2. **Recorrido en navegador real** — abrir la URL publicada en
   Chrome/Firefox, recorrer los 6 capítulos + el explorador y sus 6 vistas,
   3 preguntas a cada chat, capturas. (Aquí solo hay arnés jsdom/Playwright
   headless; la pasada visual es manual.)
