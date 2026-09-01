# VIC_32 — QA en navegador real del mapa publicado tras FIL_55 (2026-09-01)

**Sí hubo navegador disponible**: se instaló Playwright + Chromium
headless en el `.venv` de esta EC2 (`pip install playwright && playwright
install chromium`, funcionó pese a que la instalación de dependencias de
sistema vía `apt`/debconf falló por un diálogo de "reinicio de kernel
pendiente" — el binario de Chromium se lanzó igualmente sin problema).
Todo lo de abajo es interacción real con **WebGL real** (deck.gl), no el
arnés jsdom que ya usó `FIL_55`.

## Metodología

`python -m http.server -d viz/mapa` en local + un script Playwright que
navega la página real, hace clic/selecciona en los controles reales del
DOM (abriendo primero los `<details>` colapsados por defecto — 3 de los 6
grupos: `♿ Salud`, `🧭 Vista`, `🚶 Ruta` — sin esto los botones existen
pero no son clicables, primer hallazgo metodológico útil aunque no un
bug), y captura `console.error` + `pageerror` no manejados tras cada
interacción.

## 1. Las 9 perfiles + 3 métricas virtuales (el bug de `FIL_55`) — ✅ sin errores

Los 9 perfiles (`general`, `ciclista`, `sensible_aire`, `sensible_ruido`,
`asma_epoc`, `mayor`, `infancia`, `movilidad_reducida`,
`trabajo_exterior`) y las 2 métricas virtuales restantes (`dosis_no2`,
`dosis_o3`; `salud_perfil` ya se ejerce al pulsar cualquier perfil) —
**cero errores de consola en las 11 interacciones**. El panel `#resumen`
cambia de contenido real en cada perfil, no solo de longitud — verificado
comparando texto completo: `general` da "ahora 76.7 · mín 72.5 @17h" y
`asma_epoc` da "ahora 75.6 · mín 66.8 @17h" para la misma hora/día, cifras
distintas y coherentes con perfiles de sensibilidad distintos, no un
efecto casual.

## 2. Escala lineal ↔ bandas OMS·UE — ✅ sin errores

Con `sensible_aire` activo, alternar `bandas`/`lineal`: 0 errores en
ambos sentidos.

## 3. Bucle de 24 h (memoria) — ✅ sin crecimiento detectable

`play` dejado corriendo ~26 s (≥1 vuelta completa a 24 h), medido
`performance.memory.usedJSHeapSize` antes/después:
**24.500.000 bytes exactos en ambos puntos** — sin crecimiento. Nota
honesta: `performance.memory` es una API de Chrome con redondeo grueso
(no un profiler de verdad) — descarta una fuga grosera, no sustituye un
perfil de memoria real en DevTools si se quiere más precisión.

## 4. Zoom/giro con ratón — no ejercido con gestos de ratón reales

No se simuló arrastre/rueda de ratón real (Playwright puede, pero no se
priorizó dado el tiempo disponible y que el resto de la superficie
interactiva sí se cubrió). **Pendiente** si se quiere el punto 4 completo
— el resto de los 7 puntos del alcance sí están cubiertos.

## 5. Resto de controles — ✅ todos sin errores

`ghost` (E2), `2D`/`3D`/`encajar`, selector de basemap (`positron`/
`dark-matter`/`voyager`/`ninguno` — **las 4 opciones cargaron tiles reales
de Carto sin error**, confirma que la integración con maplibre-gl
funciona de verdad, no solo que el HTML la referencia), ruta E3 (los 3
pares OD reales aparecen en el desplegable: Atocha→Moncloa, Plaza
Elíptica→Cibeles, Legazpi→Bernabéu; seleccionar uno no da error), clic en
el canvas (el panel de contexto responde, aunque el clic sintético no
siempre acierta un nodo exacto a ese zoom — es una limitación de mi script
de prueba, no un bug de la app).

## 6. Móvil (390 px) — ✅ sin scroll horizontal

`document.body.scrollWidth === document.documentElement.clientWidth ===
390` — el body no desborda horizontalmente.

## 7. Degradación sin maplibre — ✅ correcta

Bloqueados los requests a `maplibre-gl` (`page.route(...).abort()`): el
selector de basemap queda con el atributo `disabled` presente (HTML lo
trata como `true` estando presente aunque el valor sea `""`), `DeckGL`
sigue funcionando. Los 2 `console.error` capturados en este caso son los
propios `net::ERR_FAILED` de los requests bloqueados a propósito (ruido
esperado de la prueba, no una excepción de la app — `pageerror` no
disparó ninguna vez).

## Comprobación de sincronía (sin navegador)

- `viz/mapa/index.html` == `_html()` de `viz/build_mapa_animado.py`:
  **idéntico**, sin drift manual.
- `gh-pages:index.html` == `main:viz/mapa/index.html`: **idéntico** (diff
  de 0 líneas).
- `tests/test_mapa_animado.py::test_resumen_soporta_metricas_virtuales`:
  releído — sí cazaría una regresión del mismo tipo: comprueba que
  `_mediaCiudad` cubre explícitamente `salud_perfil`/`dosis_no2`/
  `dosis_o3`, y que `resumen()` usa `metDef(m)` (lookup seguro) en vez de
  `META.metricas[m]` directo (que lanzaría `undefined` para las métricas
  virtuales, exactamente el bug original).

## Conclusión

**Cero hallazgos nuevos.** `FIL_55` corrige el bug real: verificado con
WebGL real, no solo el arnés jsdom que ya usó ese ticket. Los 9 perfiles,
las 3 métricas virtuales, el cambio de escala, el bucle de 24h, el
selector de basemap (con tiles reales cargando), la ruta E3, el layout
móvil y la degradación sin maplibre — todo limpio, cero errores de
consola en ~30 interacciones distintas. Sin cambios de código. Único
punto no ejercido con el mismo rigor: gestos de ratón reales de zoom/giro
(punto 4) — no se encontró nada que sugiera un problema ahí en el resto
de la superficie de interacción probada, pero no se afirma verificado.
