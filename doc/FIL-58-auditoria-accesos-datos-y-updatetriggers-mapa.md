# FIL-58 — Auditoría de las dos clases de bug de FIL_55 en el `_TEMPLATE`

`FIL_55` arregló, **solo donde reventaba**, dos patrones frágiles del JS
del mapa (`_TEMPLATE` en `viz/build_mapa_animado.py`). Este barrido revisa
el fichero entero.

## Clase 1 — acceso a `DATA[dia][clave]` con clave calculada

Regla: o la clave está acotada al conjunto real de claves de `data.json`
(`salud`, `trafico`, `no2`, `o3`, `traf_now/h1/h3/h6`, `traf_h1_act`), o
hay una rama explícita para las métricas virtuales (`salud_perfil`,
`dosis_no2`, `dosis_o3`), que **no** viven en `data.json`.

| Función | Acceso | Clave | Veredicto |
|---|---|---|---|
| `trafArr(hz)` | `DATA[state.day]["traf_"+hz]` | `hz` ∈ {now,h1,h3,h6} (botones `.hz`) | ✅ acotada |
| `_dosis(campo,…)` | `DATA[state.day][campo]` | `campo` ∈ {"no2","o3"} (2 llamadas literales) | ✅ acotada |
| `_saludPerfilHora` | `md.trafico/no2/o3` | claves literales | ✅ |
| `metricArr` (fallback) | `DATA[state.day][state.metric]` | solo se llega con `state.metric` ∈ {salud,no2,o3} (trafico y las 3 virtuales se interceptan antes) | ✅ acotada |
| `nodeColor`/`nodeElev` (ghost) | `["traf_h1"]`, `["traf_now"]` | literales | ✅ |
| `skill` | `md.traf_h1/traf_now/traf_h1_act` | literales | ✅ |
| `pulse` | `DATA[state.day].salud` | literal | ✅ |
| `edgePane` | `md.traf_now/traf_h1/no2/o3` | literales | ✅ |
| `tooltip` | `md.salud/no2/o3` | literales | ✅ |
| `_mediaCiudad` | rama por métrica + fallback `DATA[dia][metric]` | virtuales interceptadas (fix de `FIL_55`); fallback solo {salud,no2,o3} | ✅ acotada |
| `resumen` (parte 2) | `DATA[dia].salud` | literal (el panel por distrito es siempre salud) | ✅ |

**Resultado: sin accesos sin guarda.** `FIL_55` (`_mediaCiudad`) era el
único caso. `state.metric` solo puede tomar 7 valores (los `data-m` de los
botones `.met` + `"salud_perfil"` que fijan los perfiles), y las 4 rutas
que indexan `DATA` por `state.metric` cubren los 7.

## Clase 2 — `updateTriggers` incompletos

Regla: si un accessor `get*` de una capa lee `state.*` o `selNode`, ese
valor tiene que estar en el `updateTriggers` de esa clave, o el mapa no se
repinta al cambiarlo.

| Capa | Accessor con estado | `state`/`selNode` leído | En `updateTriggers`? |
|---|---|---|---|
| `imp` (ArcLayer) | `getSourceColor`, `getTargetColor` → `arcCol(trafNow[…])` | day, hour, hz | ✅ (ambos; `getTargetColor` lo añadió `FIL_55`) |
| `nodes` (Column/Scatter) | `getFillColor`→`nodeColor`, `getElevation`→`nodeElev` | day, hour, metric, hz, ghost, perfil, escala | ✅ `trig` (perfil/escala los añadió `FIL_55`) |
| `nodes` (Scatter) | `radiusMinPixels`→`nodeRmin()` | view.zoom | ✅ |
| `d-tx` (TextLayer) | `getColor` (α por zoom) | view.zoom | ✅ |
| `r-fast`/`r-safe` (PathLayer) | `data` (`R.por_hora[hour]`) | route, hour | ✅ |
| **`sel` (ScatterplotLayer)** | **`getRadius`→`nodeRmin()*3`** | **view.zoom** | ❌ → **corregido en este ticket** |
| `r-end`/`r-lbl` | `data` recomputada (ref nueva cada render) | route, hour (indirecto) | ✅ (por referencia fresca) |
| resto (`distr`,`ejes`,`tex`,`idw`,`pq-*`,`h-*`) | accessors constantes o solo `data`/`META` | — | n/a |

### Corrección aplicada

`viz/build_mapa_animado.py`, capa `sel` (el aro de selección de nodo):

```js
updateTriggers:{getRadius:[state.view.zoom]}   // el aro escala con el zoom, como los nodos
```

Antes, al hacer zoom con el ratón el aro de selección se quedaba con el
radio en píxeles de la escala anterior (los nodos sí se reajustaban, vía
`FIL_55` + su propio `updateTrigger`). Impacto bajo (el aro seguía visible,
solo con tamaño ligeramente desfasado), pero es exactamente la clase de
`FIL_55`.

## Cobertura de test

`viz/test/mapa.test.mjs` (`FIL_56`) ya dispara zoom implícito vía `fit` y
los cambios de perfil/escala/hz; el aro de selección solo aparece tras un
clic en nodo, que jsdom no puede simular sobre una capa de deck.gl (no hay
render real). La corrección es de una línea y de bajo riesgo; queda cubierta
de verdad por la pasada en navegador de `VIC_32`.
