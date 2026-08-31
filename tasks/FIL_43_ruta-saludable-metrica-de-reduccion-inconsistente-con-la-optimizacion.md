---
kind: fil
title: "ruta_saludable — la métrica de 'reducción de exposición' no coincide con lo que la ruta realmente optimiza (puede salir negativa)"
status: done
created_at: "2026-08-31"
resolved_at: "2026-08-31"
source: "QA pass sobre FIL_37 (ruta_saludable, PR #211)"
severity: media
---

## Resolución (2026-08-31) — opción 1

`_metricas` (en `viz/rutas.py` **y** en `asistente/ruta_saludable.py`) pasa
a acumular la exposición **por arista** con la MISMA agregación que el coste
de Dijkstra: `Σ_aristas 0.5·(extremo_u + extremo_v)`, normalizada por señal,
y su combinación ponderada por perfil `E_ponderada` (el término de
exposición del coste que se minimiza).

- **`reduccion_exposicion_pct`** ahora es **un solo número**: la reducción
  de `E_ponderada` de la ruta sana frente a la rápida. Por construcción de
  Dijkstra (la sana minimiza `w_dist·dist + Σ w·expo` y la rápida sólo
  `dist`, con `dist_sana ≥ dist_rapida`) **nunca es negativa**. Verificado:
  0/144 combinaciones hora·ruta negativas (antes 14/144), `pareto()` con
  mínimo +0,1 %.
- Las señales individuales pasan a **`cambio_por_senal_pct`** (± permitido y
  etiquetado como "cambio", no "reducción"): la ruta sana canjea unas
  señales por otras y eso ahora se dice explícitamente.
- Mapa (capa E3): el readout muestra `−X% exposición ponderada` + una línea
  de "cambio por señal" con signo. `viz/mapa/rutas.json` regenerado
  (`python -m viz.rutas` vía `build_mapa_animado`) y **republicado a
  `gh-pages`** (`FIL_42`).
- `mejor_hora()` y `pareto()` usan `E_ponderada`. Tests:
  `tests/test_rutas.py::test_reduccion_ponderada_nunca_negativa`.
- `asistente/ruta_saludable.py` (12.ª tool, `FIL_37` PR #213) nace ya con la
  métrica corregida — la respuesta de la tool no hereda el problema.

## Qué está roto (verificado en vivo)

`viz/rutas.py` calcula la "ruta sana" minimizando un coste **por arista**
(`_ruta_con_pesos`/`_coste_arista`): para cada arista, `w_dist·(length_m/1000)
+ Σ_señal w_señal · promedio(exposición de los dos extremos)`, sumado sobre
todas las aristas del camino (Dijkstra vía `networkx.shortest_path`).

Pero la métrica que se **reporta al usuario** como "reducción de
exposición" (`_metricas`, usada en `ruta()`, en `viz/mapa/rutas.json`, y
mostrada literalmente en el mapa público) es una cantidad **distinta**: el
promedio simple de la exposición **por nodo** del camino
(`acc[s] += e.get(s, 0.0)` para cada nodo, dividido por `len(path)`), sin
ponderar por longitud de arista y sin ser la misma agregación que Dijkstra
usó para elegir la ruta.

Como caminos distintos pueden tener densidades de nodo distintas (más o
menos cruces por km según qué calles recorran), minimizar el coste por
arista **no garantiza** minimizar el promedio por nodo que se reporta —
pueden divergir, y de hecho divergen con frecuencia real:

**Verificado contra el `viz/mapa/rutas.json` ya commiteado** (3 pares
origen/destino × 2 perfiles × 24 h = 144 combinaciones):

- **14/144 (10 %) de las reducciones agregadas (media de las 4 señales)
  son negativas** — la "ruta sana" es, en promedio, **peor** que la ruta
  rápida en esa hora concreta.
- **263/576 (46 %) de las reducciones por señal individual son
  negativas** (mayoría en `noise`, también `traf`/`o3`/`no2`).

**Ejemplo reproducido en vivo** (`ruta("Príncipe Pío", "Plaza Castilla",
"general", dia="2026-08-26", hora=14)`):

```
ruta sana:   27 nodos, 6637 m, tráf_medio=44.94, ruido_medio=61.02
ruta rápida: 33 nodos, 6512 m, tráf_medio=42.14, ruido_medio=60.38
reduccion_exposicion_pct: {'traf': -6.6, 'no2': 1.4, 'o3': 0.0, 'noise': -1.1}
```

La ruta "sana" tiene **más** distancia (+1,9 %) y **más** tráfico y ruido
medios que la ruta rápida — el algoritmo la recomienda igual porque
minimizó el coste por arista, no el promedio por nodo que luego se
muestra.

Ejemplo más extremo, real, ya en `viz/mapa/rutas.json`: `Legazpi→Bernabéu`,
perfil `ciclista`, 01:00 → `reduccion_exposicion_pct.traf = -24.4` (24 %
**más** tráfico en la ruta "sana").

## Por qué importa

Esta métrica **se muestra tal cual en el mapa público**
(`https://madrono-ucm.github.io/madronoTFM/`, capa E3): el readout dice
literalmente *"exposición −: tráf X% / NO₂ X% / O₃ X% / ruido X%"` con el
signo que salga, incluyendo negativo — cualquier visitante que pruebe
"Atocha→Moncloa, general" durante buena parte del día ve la ruta verde
("saludable") con **−3,2 % de ruido**, es decir, más ruido que la ruta
gris ("rápida"), contradiciendo la etiqueta "saludable" delante de sus
ojos. Mismo dato alimentaría el `pareto()` de §7 de la memoria y una
futura 12.ª tool MCP (`FIL_37` todavía la tiene pendiente) — si se sirve
tal cual, el mismo problema llega a la respuesta de la tool.

No es un caso raro ni un extremo teórico: 1 de cada 10 combinaciones
hora/ruta agregadas y casi la mitad de las señales individuales ya
commiteadas al repo tienen el signo "equivocado".

## Qué hacer (propuesto, no aplicado aquí)

La forma más directa de arreglarlo es que `_metricas` reporte la **misma**
cantidad que `_coste_arista` optimiza (promedio ponderado por arista de
`0.5·(extremo_u + extremo_v)`, no un promedio simple por nodo), en vez de
una métrica distinta calculada por separado. Alternativas:

1. Acumular la exposición por **arista** (no por nodo) al recorrer el
   camino en `_metricas`, replicando exactamente el término de
   `_coste_arista` — así la métrica reportada es, por construcción, la
   misma que Dijkstra minimizó, y la reducción nunca puede salir negativa
   respecto a lo que la propia optimización garantiza.
2. Si se prefiere mantener el promedio por nodo por ser más intuitivo,
   documentarlo explícitamente como una aproximación distinta de lo
   optimizado, y filtrar/advertir cuando salga negativo en vez de
   mostrarlo sin más en el mapa público y en el `pareto()` de la memoria.

Se recomienda la opción 1 — es un cambio localizado en `_metricas` (o en
cómo se acumula `acc` dentro de esa función), sin tocar `_ruta_con_pesos`
ni el resto del pipeline.

## Restricciones

- No se ha aplicado el cambio aquí (ticket de solo lectura).
- El mapa público en `gh-pages` seguirá mostrando el dato inconsistente
  hasta que se corrija `viz/rutas.py`, se regenere `viz/mapa/rutas.json`
  (`python -m viz.rutas`) y se vuelva a publicar
  (`python -m viz.build_mapa_animado` + republish a `gh-pages`, ver
  `FIL_42`).
- Antes de envolver esto como la 12.ª tool MCP (pendiente en `FIL_37`),
  corregir esto primero — la tool heredaría el mismo problema en su
  respuesta si se sirve la métrica tal cual está hoy.

## Criterios de aceptación

- `_metricas` (o la función que calcule la reducción reportada) usa la
  misma agregación por arista que `_coste_arista`, o el mismo criterio
  documentado explícitamente si se opta por la alternativa 2.
- Tras corregir, `viz/mapa/rutas.json` regenerado no debería tener
  ninguna reducción agregada negativa para el perfil que optimiza esa
  señal (algún negativo residual en una señal que el perfil no pesa
  — p. ej. `o3` en `general`, que ya pesa poco — es aceptable y se puede
  documentar, pero no en la señal que el perfil sí prioriza).
- Suite de `tests/test_rutas.py` sigue en verde, y se añade un caso que
  falle si la reducción agregada de la ruta sana es negativa para el
  perfil correspondiente.
