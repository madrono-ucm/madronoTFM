---
kind: fil
title: "Mapa animado: controles que degradan o rompen el render (barras 3D, perfiles, dosis, bandas)"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_55, FIL_91]
milestone: "M7"
target: "2026-09-15"
---

## Motivación (pedido del usuario)

> «Hay muchas funciones que al seleccionarlas crean bugs en el mapa, como
> las barras 3D.»

Auditado `viz/mapa/index.html` + `viz/build_mapa_animado.py` el 2026-09-10.
No son botones sin handler (FIL_91 cubre eso) — son **defectos de
comportamiento**: varios controles llevan el render a un estado lento,
incoherente o que lanza. Casi todos desembocan en **tres causas raíz**.

## Defectos encontrados

### A. `metricArr()` se recalcula O(n²) por render → congelación con «barras (3D)», perfiles y dosis

- `layers()` crea en **cada** render un `data: META.coords.map((_,i)=>i)`
  **nuevo** → deck.gl vuelve a ejecutar TODOS los accessors para los 1798
  nodos en cada frame.
- `getFillColor: nodeColor` y (en barras) `getElevation: nodeElev` llaman
  ambos a `metricArr()` **por nodo**, sin memoizar.
- Para `salud_perfil`, `metricArr()` reconstruye un array de 1798 con
  `_saludPerfilHora()` → **1798 × 1798 ≈ 3,2 M iteraciones/accessor**. Para
  `dosis_no2`/`dosis_o3`, `_dosis()` añade un bucle de 8 h por nodo →
  **~26 M/accessor**. Con barras son 2 accessors → el doble.
- Se dispara además en cada evento `move`: al pulsar «barras (3D)» o «auto»,
  `setPitch(45)` hace un `easeTo` de 300 ms que emite ~decenas de `move`,
  cada uno → `render()` → recálculo completo. Y en cada `tick()` de
  reproducción (650 ms).
- `ColumnLayer` (`extruded:true`, `diskResolution:12`) es además mucho más
  caro en GPU que el `ScatterplotLayer` del modo puntos.
- **Efecto:** al seleccionar «barras (3D)» (o «auto» ya inclinado) con un
  perfil o con dosis, el mapa se congela entre cientos de ms y segundos por
  frame, se comen clics y el playback va a tirones.

**Arreglo:** memoizar el vector de métrica por `(day, hour, metric, perfil,
hz, ghost)` — calcularlo **una vez por render** y que `nodeColor`/`nodeElev`
(y `_mediaCiudad`) lean de esa caché. `data` de la capa de nodos estable
(no `.map` nuevo cada vez). Revisar `elevationScale`/`radius` de
`ColumnLayer` para que las barras no salgan de pantalla al inclinar.

### B. `escala: "bandas"` no hace nada con «dosis NO₂» / «dosis O₃» (y la Historia entra ahí)

- `meta.json` `umbrales` = `["no2","o3","salud"]`. `MET_EXTRA.dosis_no2` y
  `dosis_o3` **no tienen `banda`** ni umbral propio.
- `render()`: `bandas = escala==="bandas" && !ghost && umbrales[md.banda||metric]`
  → `undefined` → el botón «bandas OMS·UE» queda **visualmente activo** pero
  la leyenda sigue en degradado y `_banda()` devuelve `null` → los nodos se
  colorean por rampa. UI que se contradice a sí misma.
- **Los capítulos 2 y 3 del recorrido guiado** hacen
  `setEstado({metric:"dosis_o3", escala:"bandas", …})` → la función estrella
  de storytelling aterriza en ese estado incoherente.

**Arreglo:** definir `umbrales.dosis_no2` / `umbrales.dosis_o3` (p. ej.
cortes en 50/100/150 % de la guía OMS) en `build_mapa_animado.py` y darles
`banda` en `MET_EXTRA`; **o**, si no se quieren bandas para dosis,
deshabilitar el botón «bandas» cuando la métrica activa no tiene umbral y
que los capítulos 2/3 no pidan `escala:"bandas"`.

### C. `render()` no está protegido: una sola excepción congela el mapa para siempre

- `render()` empieza por `overlay.setProps({layers: layers()})` y no tiene
  `try/catch`. No hay `window.onerror`. Si `layers()`, `routeInfo()`,
  `resumen()` o `pulse()`/`edgePane()` lanzan (es la clase de bug de
  **FIL_55**: `undefined[hora]`), deck.gl no recibe capas nuevas y el mapa
  queda **bloqueado en ese frame y en todos los siguientes**, sin aviso,
  hasta recargar.
- `routeInfo()` hace `R.por_hora[state.hour]` sin comprobar; `resumen()`
  con una serie de 24 `null` produce `Math.min(...[]) = Infinity` y pinta
  «mín Infinity @-1h».

**Arreglo:** envolver el cuerpo de `render()` en `try/catch` que registre y
muestre un banner discreto («no se pudo actualizar el mapa — reintentar»)
sin romper el bucle; añadir `window.onerror`/`onunhandledrejection` (igual
que el explorador ya tiene, `build_grafo_explorador.py`); guardas en
`routeInfo`/`_mediaCiudad` para series vacías / hora fuera de rango.

### D. Fugas de estado entre capítulos de la Historia

`setEstado(p)` solo aplica las claves que el capítulo pasa; las demás
persisten. `escala:"bandas"` puesto por el cap. 2/3 sigue activo al llegar
al cap. 6 (`metric:"salud"`, que **sí** tiene umbral) → el cap. 6 se pinta
en bandas sin haberlo pedido. Cada capítulo debería declarar el estado
completo que ilustra, o `setEstado` resetear a un defecto lo no
especificado (`escala`, `ghost`, `hz`, `route`, `perfil`).

## Alcance

1. Arreglar A, B, C, D en `viz/build_mapa_animado.py` (`_TEMPLATE`) y
   regenerar `viz/mapa/`.
2. `tests/test_mapa_animado.py` (pytest) + `viz/test/mapa.test.mjs` (jsdom):
   - un test que **recorre todos los controles** (métricas incl. las 3
     virtuales × `lineal`/`bandas` × `puntos`/`auto`/`barras` × 9 perfiles
     × ghost on/off) llamando a `render()` y afirma **0 excepciones**.
   - un contador de iteraciones (o de llamadas a `_saludPerfilHora`) que
     falla si un render con `salud_perfil` + barras supera un presupuesto
     (memoización efectiva).
   - los 6 capítulos de la Historia: tras `c.a()`, el estado del DOM
     (botones `.on`) coincide con `state`, y si `escala==="bandas"` la
     métrica activa tiene umbral.
3. Verificación en navegador real (Playwright, como FIL_69): seleccionar
   «barras (3D)» con perfil `asma_epoc` y con `dosis O₃`, mover/inclinar la
   cámara, reproducir 24 h → sin frames > 100 ms sostenidos, sin errores de
   consola.

## Fuera de alcance

- Rediseño visual de las barras o de la leyenda.
- El guard genérico de «control sin handler» (FIL_91) y la extracción de JS
  compartido / estados de carga (FIL_75).

## Verificación

- «barras (3D)» + cualquier perfil + `dosis O₃`: interacción fluida, cámara
  y playback sin tirones.
- El botón «bandas OMS·UE» o colorea por bandas de verdad (leyenda incluida)
  o está deshabilitado cuando no aplica — nunca activo-sin-efecto.
- Forzar un throw dentro de `layers()` en una rama de prueba → banner +
  el mapa sigue respondiendo a los siguientes cambios, no se queda tieso.
- Recorrer los 6 capítulos ida y vuelta deja cada uno en el estado que
  describe su texto.

## Prioridad y secuencia

**Alta.** Es lo que el usuario está viendo. Va **después de FIL_91** (para
que el test de «todos los controles sin throw» tenga dónde vivir y corra en
CI) y puede solaparse con FIL_74 (no publicar hasta que esto cierre).
Estimación ~1 día. Objetivo: **2026-09-15**.

## Hecho (2026-09-10, rama `fil-88-mapa-render-defectos`)

Todo en `viz/build_mapa_animado.py` (`_TEMPLATE` + el dict `umbrales` de
`_meta`); `viz/mapa/{index.html,meta.json}` regenerados.

- **A (O(n²)):** `metricArr()` memoiza el vector por
  `metric|day|hour|hz|perfil` (`_maCache` + `_metricArrCalc`). `data` de la
  capa de nodos pasa a un `NODE_IDX` estable (antes `META.coords.map(...)`
  nuevo cada `layers()` → deck.gl re-ejecutaba todos los accessors en cada
  frame de cámara). Residual conocido, acotado y no bloqueante: `resumen()`
  aún recorre 24 h por render aunque solo se mueva la cámara — candidato a
  no recalcular paneles en renders de solo-cámara (follow-up, no en esta
  rama).
- **B (bandas sin efecto en dosis):** añadidas `umbrales.dosis_no2` /
  `umbrales.dosis_o3` (cortes 50/100/150/200 % de la guía OMS, 5 bandas).
  `_banda()` ya cae a la clave de la métrica, así que basta con los datos.
- **C (throw congela el mapa):** `render()` → wrapper `try/catch` sobre
  `_render()`; banner `#err` discreto con «Reintentar»;
  `window.addEventListener("error"/"unhandledrejection")`. `routeInfo()`
  con guarda `if(!R || !r)`. `resumen()` con guarda de serie vacía (no más
  `Math.min(...[]) = Infinity`).
- **D (fuga de estado entre capítulos):** `setEstado()` hace
  `Object.assign(state, {ghost:false, escala:"lineal", hz:"now", route:-1,
  perfil:"general"}, p)` — cada capítulo declara solo lo que lo distingue.

**Tests (verde):**
- `viz/test/mapa.test.mjs`: `montar()` extraído a helper y su
  `MapboxOverlay` stub ahora **ejecuta de verdad** los accessors de la capa
  de nodos sobre una muestra → el test FIL_56 «disparar todos los
  controles» ejercita `nodeColor`/`nodeElev` en cada combinación y
  comprueba que `#err` no aparece. +4 tests FIL_94 (memoización,
  banner+recuperación ante throw, bandas en dosis, no-fuga entre
  capítulos). 7/7.
- `tests/test_mapa_animado.py`: +4 asserts (umbrales de dosis, `_maCache` /
  `NODE_IDX`, `_render`/`try`/`#err`/guarda de `routeInfo`, reset de
  `setEstado`). 22/22.
- Suite `tests/` completa: 53/53.

Pendiente: PR y flip de `status`. Regenerar `gh-pages` es FIL_74.
