---
kind: vic-eval
title: "Evaluación técnica ronda 7 — QA en navegador real del mapa publicado tras FIL_55"
owner: Claude (QA)
status: done
depends_on: []
---

Parte de [`doc/PLAN-EVALUACION-TECNICA-7.md`](../doc/PLAN-EVALUACION-TECNICA-7.md).
Ningún cambio de código — solo verificación.

## Por qué

`FIL_55` (PR #234, mergeado) arregló un `TypeError` que rompía el panel de
resumen del mapa animado (`https://madrono-ucm.github.io/madronoTFM/`) al
pulsar cualquiera de los 9 perfiles de sensibilidad o las métricas
`salud (perfil)` / `dosis NO₂` / `dosis O₃`, más 3 bugs de repintado
(`updateTriggers` de nodos sin `perfil`/`escala`, `ArcLayer` sin
`getTargetColor`, `onViewStateChange` sin `render()`). **Todo se verificó
con un arnés headless jsdom** (deck.gl / maplibre / fetch mockeados): 51
controles, 0 excepciones. Eso valida la máquina de estados, **no** el
render real (WebGL), el layout, el móvil, ni el comportamiento en
interacción continua.

## Alcance — abrir el mapa en un navegador de verdad

Servir en local (`python -m http.server -d viz/mapa` → `localhost:8000`) o
usar la URL publicada. Con la **consola abierta**, recorrer:

1. **Métricas virtuales de `FIL_45`** (el bug de `FIL_55`): pulsar los 9
   perfiles (`general`, `ciclista`, `sensible_aire`, `sensible_ruido`,
   `asma_epoc`, `mayor`, `infancia`, `movilidad_reducida`,
   `trabajo_exterior`) y `salud (perfil)` / `dosis NO₂` / `dosis O₃`.
   Confirmar en cada uno: los nodos recolorean, el panel inferior
   (`#resumen`: media ciudad 24 h + barras por distrito) se actualiza, el
   pulso de distrito se actualiza, **cero errores en consola**.
2. **Escala** `lineal` ↔ `bandas OMS·UE` con un perfil activo → los nodos
   deben recolorear (era uno de los 3 bugs de repintado).
3. **Bucle de 24 h** (play): arcos + panel de resumen animan; dejarlo
   correr ≥2 vueltas y mirar el perfil de memoria de la pestaña (Chrome
   DevTools → Performance/Memory) — que no crezca de forma monótona
   (el `mejorHoraPerfil` memoizado y el `requestAnimationFrame` de
   `onViewStateChange` no deberían acumular).
4. **Zoom / giro con el ratón** (no con los botones): el radio de nodo
   (`nodeRmin`), la opacidad de las etiquetas de distrito y el cambio
   puntos↔barras en modo `auto` (pitch > 5) deben reaccionar sin tener
   que tocar otro control.
5. **Resto**: `ghost` (E2 modelo vs persistencia), ruta E3 (2
   desplegables), 2D/3D/encajar/vista limpia, selector de basemap
   (`ninguno` → Positron/Dark Matter/Voyager), todas las capas
   conmutables, clic en nodo → panel E4 + anillo de selección, tooltip.
6. **Móvil / viewport estrecho** (DevTools device toolbar, ~390 px): los
   paneles de control hacen scroll interno, **el body no hace scroll
   horizontal**, los `<details>` colapsables funcionan.
7. **Degradación**: simular `maplibregl` no disponible (bloquear el CDN en
   la pestaña Network) → el selector de basemap queda `disabled` y el
   `DeckGL` plano sigue funcionando.

## Comprobación de sincronía (sin navegador)

- `viz/mapa/index.html` en `main` == salida de `_html()` de
  `viz/build_mapa_animado.py` (sin drift manual).
- `gh-pages:index.html` == `main:viz/mapa/index.html`.
- Releer `tests/test_mapa_animado.py::test_resumen_soporta_metricas_virtuales`:
  ¿de verdad cazaría una regresión del mismo tipo? ¿cubre las 3 métricas
  virtuales + el uso de `metDef` en `resumen()`?

## Criterios de aceptación

- Recorrido de los 7 puntos hecho en un navegador real con la consola
  abierta, con capturas o notas concretas por punto (no "parece que va").
- Si no hay navegador disponible en el entorno de QA: decirlo
  explícitamente y hacer la pasada estática más profunda posible
  (releer el `_TEMPLATE` completo buscando más rutas `DATA[dia][clave]`
  sin guardia, más `updateTriggers` incompletos, listeners sin limpiar).
- Verdicto explícito por hallazgo: cosmético / no bloqueante / real
  (→ `FIL_56`+).
- Cero cambios de código aquí.

## Restricciones

- Solo lectura / navegación. No re-publicar `gh-pages`.
- No “arreglar de paso” — si aparece un bug, va a un `FIL_*` nuevo con su
  repro.

## Hecho (2026-09-01, Claude QA)

Sí hubo navegador real disponible: se instaló Playwright + Chromium
headless en el `.venv` de esta EC2 y se sirvió `viz/mapa/` en local con
`python -m http.server`. Recorridos los 7 puntos con interacción real de
WebGL (no el arnés jsdom que ya usó `FIL_55`): los 9 perfiles + 3
métricas virtuales, escala lineal/bandas, bucle de 24h (sin crecimiento
de heap detectable), 2D/3D/encajar/ghost, selector de basemap (las 4
opciones cargan tiles reales de Carto sin error), ruta E3, layout móvil
390px (sin scroll horizontal) y degradación sin maplibre (selector
correctamente `disabled`) — **cero errores de consola en ~30
interacciones distintas**. Confirmado que `#resumen` cambia de contenido
real (no solo longitud) entre perfiles. Sincronía estática también
verificada: `_html()` == `viz/mapa/index.html` == `gh-pages`, y el test
de regresión (`test_resumen_soporta_metricas_virtuales`) sí cazaría una
reaparición del bug. Único punto no ejercido con el mismo rigor: gestos
de ratón reales de zoom/giro (punto 4).

**Cero `FIL_*` nuevos.** Detalle completo en
[`doc/VIC-32-eval-fil55-mapa-navegador.md`](../doc/VIC-32-eval-fil55-mapa-navegador.md).
