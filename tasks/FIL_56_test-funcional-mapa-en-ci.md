---
kind: fil
title: "Mapa animado — test funcional de la interfaz en CI (evitar regresiones tipo FIL_55)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
depends_on: [FIL_55]
---

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
