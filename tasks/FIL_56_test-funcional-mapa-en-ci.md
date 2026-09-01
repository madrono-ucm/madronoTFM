---
kind: fil
title: "Mapa animado — test funcional de la interfaz en CI (evitar regresiones tipo FIL_55)"
owner: Filippos (interactive)
status: done
allow_infra_apply: false
depends_on: [FIL_55]
resolved_at: "2026-09-01"
---

## Resolución (2026-09-01)

`viz/test/mapa.test.mjs` (`node:test` + `jsdom`, `viz/package.json` con
`jsdom` como única `devDependency`). El subtest de FIL_56 carga
`viz/mapa/index.html` con stubs de `deck` (clases de capa que solo guardan
props), `maplibregl` y `fetch` (devuelve los `viz/mapa/*.json` reales), y
dispara los 51 controles: 4 métricas base + 3 virtuales, 9 perfiles,
escala, 4 horizontes, 3 días, representación, 2D/3D/encajar/vista limpia,
las 6 capas conmutables, las 2 pestañas, selección de ruta y play.
Aserción: cero `window error` / `jsdomError`, y `#titulo-sub` deja de ser
"—" tras la carga.

**Con dientes**: reintroduciendo a mano el bug de FIL_55 en `_mediaCiudad`
el subtest se pone rojo; restaurado, verde.

`node_modules/` añadido a `.gitignore`; `viz/package-lock.json` sí se
versiona. FIL_57 se resolvió en el mismo fichero de test.

### Pendiente: el job de CI (necesita `workflow` scope)

El código y el test están mergeados. Falta añadir el job a
`.github/workflows/ci.yml` — el token de `madrono-ucm` no tiene el scope
`workflow` y GitHub rechaza el push que toca `.github/workflows/`. Lo tiene
que aplicar alguien con ese scope (`gh auth refresh -s workflow` o desde la
web), añadiendo tras el job `terraform`:

```yaml
  # Tests funcionales del mapa animado publicado (FIL_56 / FIL_57): jsdom
  # carga viz/mapa/index.html con deck.gl/maplibre/fetch simulados y dispara
  # todos los controles; falla si el JS generado no es válido o si render()
  # lanza. Única parte del repo que usa Node -- job propio, sin tocar Python.
  mapa:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: viz
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: viz/package-lock.json
      - run: npm ci
      - run: npm test
```

Mientras tanto el test corre en local con `cd viz && npm ci && npm test`.

## Contexto

`FIL_55` fue un `TypeError` que rompía el panel de resumen del mapa
publicado al pulsar cualquiera de los 9 perfiles de sensibilidad o las
métricas de dosis. **Se coló hasta producción** porque los tests del mapa
(`tests/test_mapa_animado.py`) solo comprueban presencia de cadenas en el
HTML generado — no ejecutan el JS ni simulan un clic. El bug se encontró y
se verificó con un arnés `jsdom` **ad-hoc, no commiteado**.

## Objetivo

Convertir ese arnés en un test real bajo `tests/` que corra en CI y que
habría fallado con el bug de `FIL_55`.

- `tests/test_mapa_animado_dom.py` (o `.mjs` con `node --test` si se
  prefiere JS): carga `viz/mapa/index.html` en `jsdom`, con stubs de
  `deck` (clases de capa que solo guardan props), `maplibregl` y `fetch`
  (devuelve los `viz/mapa/*.json` reales del repo).
- Dispara **todos** los controles: las 4 métricas base + `salud_perfil` +
  `dosis_no2` + `dosis_o3`, los 9 perfiles, escala `lineal`/`bandas`,
  `ghost`, los 4 horizontes, slider de hora (0 y 23), los 3 días, 2D/3D,
  `auto`/`puntos`/`barras`, `encajar`, `vista limpia`, todas las capas
  conmutables, las 2 pestañas de contexto, selección de ruta, y `play`.
- Aserción: **cero excepciones** (capturar `window.onerror` +
  `jsdomError` del `VirtualConsole`) y que `#titulo-sub` deja de ser "—"
  tras la carga (prueba de que `render()` completó).
- Si `jsdom` no está en el entorno de test: instalarlo como
  `devDependency` mínima (`package.json` en `viz/` o raíz) o declararlo en
  el job de CI; documentar la decisión.

## Criterios de aceptación

- El test falla si se revierte el fix de `FIL_55` (verificarlo: revertir
  a mano, correr, ver rojo, restaurar).
- Corre en el mismo job de CI que el resto de `tests/`.
- < 15 s de ejecución (jsdom + stubs, sin navegador).

## Restricciones

- No es un test de navegador real (WebGL/layout/móvil) — eso es `VIC_32`.
  Este cubre la máquina de estados y el pipeline de `render()`.
- No tocar `viz/build_mapa_animado.py` salvo para exponer el `_TEMPLATE`
  de forma testeable si hiciera falta.
