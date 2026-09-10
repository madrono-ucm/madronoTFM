---
kind: fil
title: "Web: consolidación del frontend (JS compartido, estados carga/error/vacío, caché, accesibilidad)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-09"
depends_on: [FIL_69, FIL_74]
milestone: "M7"
target: "2026-09-27"
---

## Motivación

El frontend son dos generadores de HTML en Python que emiten JS embebido
como cadenas de texto:

- `viz/build_mapa_animado.py` — el mapa animado (grafo STGNN `coords-knn8`,
  deck.gl + maplibre), ~1.000 líneas de JS en un string.
- `viz/build_grafo_explorador.py` — el explorador (grafo Neo4j real),
  otro bloque de JS en un string, con su propia copia de utilidades
  (fetch con reintento, banner de error, `window.onerror`…).

Funciona y hay tests jsdom (`viz/test/mapa.test.mjs`) + Playwright para
render real, pero: lógica duplicada entre los dos, sin lint, sin paso de
build, difícil de razonar, y los estados de carga/error/vacío se han ido
añadiendo a parches distintos en cada uno.

## Alcance

1. **Extraer un módulo JS compartido** — `viz/static/comun.js` (o
   equivalente) con lo que ambos usan: `fetchConReintento(url, n)`, banner
   de error + `window.onerror`/`onunhandledrejection`, helpers de formato,
   `API_BASE` / resolución de `?api=`. Los dos generadores lo `<script
   src>`-ean o lo inyectan una vez.
2. **Estados consistentes** — un patrón único de *loading / error /
   vacío / ok* para cada panel que hace fetch (mapa: rutas, weather, chat;
   explorador: data, vecindario, analisis, ruta). Mismo aspecto, mismos
   textos, mismo botón "Reintentar".
3. **Caché del payload del grafo** — `/grafo/explorador/data` es grande;
   además del TTL de servidor (600 s) cachear en el cliente
   (`sessionStorage` o memoria) para que cambiar de vista no vuelva a
   descargarlo. Invalidación simple por versión/fecha.
4. **Lint** — pasar el JS extraído por un linter (ESLint config mínima) en
   CI; el JS embebido restante al menos por `node --check` (ya lo hace
   FIL_57 para el mapa, extenderlo al explorador).
5. **Accesibilidad básica** — foco visible, `aria-label` en los controles
   icónicos, contraste del tema oscuro del explorador, navegación por
   teclado de los paneles plegables. No es una auditoría completa, es el
   mínimo decente.

## Fuera de alcance

- Reescribir a un framework (React/Svelte) — desproporcionado para dos
  páginas y el calendario del TFM.
- Un bundler pesado; basta con concatenar/servir estáticos.

## Verificación

- `viz/test/mapa.test.mjs` + un test jsdom equivalente para el explorador,
  verdes.
- Cambiar de vista en el explorador no dispara un segundo fetch de `data`
  (comprobable en el test o con un contador).
- Lint en verde en CI.
- Recorrido de teclado por los paneles del mapa y del explorador sin
  ratón.

## Criterios de aceptación concretos (afinado 2026-09-10)

- **Módulo compartido** — `rg -n "function fetchConReintento" viz/` devuelve
  **un solo** sitio (`viz/static/comun.js`); ambos generadores lo inyectan
  una vez. Idéntico para el banner de error + `window.onerror` +
  `onunhandledrejection` y para la resolución de `API_BASE`/`?api=`.
- **Estados** — un helper `estado(panelEl, tipo, detalle)` con
  `tipo ∈ {cargando, error, vacio, ok}`. Cada panel que hace fetch —
  mapa: rutas, weather, chat; explorador: data, vecindario, analisis, ruta
  — muestra los 4 estados con el mismo aspecto, textos y botón
  «Reintentar». Un test dirige cada panel por los 4 estados con `fetch`
  mockeado. **Los textos coinciden con los de FIL_92** (landing).
- **Caché** — `/grafo/explorador/data` se cachea en cliente
  (`sessionStorage`, clave con la fecha/versión del payload). Test o
  contador: **cambiar de vista 2 veces = 1 solo fetch de `data`**.
- **Lint** — job del CI `frontend` (creado en FIL_91) corre ESLint sobre
  `viz/static/*.js`: **0 errores** (warnings permitidos). El JS embebido
  restante sigue pasando por `node --check` (ya en FIL_91).
- **a11y** — `:focus-visible` en todos los controles de ambas páginas;
  `aria-label` en los botones icónicos (`▶︎`, `➤`, tabs); navegación por
  teclado de los grupos plegables del mapa y de los paneles del explorador;
  contraste ≥ 4.5:1 en el tema oscuro del explorador (listar en el PR los
  tokens de color ajustados). Recorrido de teclado documentado en
  `viz/README.md`.

## Prioridad y secuencia

**Baja / candidato a partir en dos.** Es el ticket más invasivo — reescribe
partes de ~1000 líneas de JS-en-string en **cada** generador, con 7 días
para la entrega y alto riesgo de regresión. Propuesta:

- **Antes de la entrega (2026-09-17):** solo el helper `estado(...)`
  compartido + los 4 estados consistentes + a11y mínima (`:focus-visible`,
  `aria-label`, teclado). Sin extraer el módulo entero.
- **Post-defensa:** extracción de `viz/static/comun.js`, caché de payload,
  ESLint sobre el extraído, deduplicación completa.

Depende de **FIL_74** (publicar primero lo que ya funciona) y de **FIL_91**
(el job `frontend` de CI donde entra el lint).
