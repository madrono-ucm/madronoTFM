---
kind: fil
title: "grafo_analitica: betweenness del grafo completo se calcula dos veces en la misma ejecución"
status: done
severity: baja (rendimiento, no correctitud)
created_at: "2026-09-10"
source: "VIC_41 (QA de FIL_81)"
depends_on: [FIL_81, FIL_64]
---

## Hecho (2026-09-10, Claude)

Aplicada la sugerencia del propio ticket: `centralidad_transporte` y
`curva_robustez` aceptan ahora un `bet_inicial: dict | None = None`
opcional; si se da, se usa en el paso 0 en vez de recalcular
`nx.betweenness_centrality`. `resiliencia_transporte` lo pasa a través.
`main()` calcula el betweenness del componente mayor **una sola vez** y lo
comparte entre ambas llamadas.

Verificado que no cambia ningún resultado: nuevo test
`test_centralidad_acepta_betweenness_precalculado` confirma que pasar un
`bet_inicial` precalculado da exactamente la misma `intermediacion` que
dejar que la función lo calcule; `test_curva_robustez_bet_inicial_no_
recalcula_el_paso_0` confirma con un spy sobre `nx.betweenness_centrality`
que con `bet_inicial` se hace **una llamada menos** que sin él, y que la
curva resultante es idéntica. Suite completa de `modelado/tests/
test_grafo_analitica.py` verde salvo los 2 fallos preexistentes de
`FIL_61` (louvain_communities, sin relación con este cambio).

No se ejecutó `python -m modelado.grafo_analitica.analisis` completo sobre
el grafo real en esta sesión (no hace falta para verificar este cambio:
`bet_inicial` no toca ninguna consulta a Neo4j ni a Athena, es puro
`networkx` en memoria, y el test de arriba ya confirma con un spy que
evita la llamada duplicada sin cambiar el resultado) -- queda pendiente de
quien regenere `grafo_centralidad.json`/`grafo_resiliencia.json` la
próxima vez confirmar que salen igual que antes (deberían, por
construcción) y algo más rápido.

## Qué pasa

`modelado/grafo_analitica/analisis.py::main()` llama, en la misma
ejecución:

1. `centralidad_transporte(G_conn, nombres)` (línea 104) — calcula
   `nx.betweenness_centrality(H, normalized=True, seed=42)` sobre el
   componente mayor completo de `CONECTADO_CON`.
2. Más abajo, `resiliencia_transporte(G_conn, nombres)` →
   `curva_robustez(G_conn)` (línea 326) — en su primera iteración
   (`i=0`, antes de quitar ningún nodo), calcula
   `nx.betweenness_centrality(H, normalized=True, seed=seed)` sobre
   `H0.copy()`, que es el **mismo grafo** (mismo componente mayor, mismos
   parámetros, misma semilla).

Es decir: el betweenness del grafo completo (sin ninguna baja) se
calcula dos veces con entradas idénticas → mismo resultado, coste
duplicado. `betweenness_centrality` es O(V·E); en el componente de 3053
nodos del grafo real esto no es gratis (varios segundos por corrida,
verificado en vivo durante `VIC_41`).

No es la recomputación **intencional** de `curva_robustez` en cada lote
de `recalc_cada` bajas (esa sí hace falta: el grafo cambia en cada
iteración) — es específicamente el paso 0 de esa curva, que coincide con
lo que `centralidad_transporte` ya calculó por separado.

## Por qué importa

Bajo impacto: no afecta a la corrección de ningún resultado (ambos
cálculos dan el mismo número), solo al tiempo de ejecución de
`modelado.grafo_analitica.analisis` — un script offline que no está en
ninguna ruta caliente ni bloquea el pipeline de producción. Vale la pena
arreglarlo por higiene antes de que alguien añada una tercera llamada a
`betweenness_centrality` sobre el mismo grafo sin darse cuenta del
patrón.

## Sugerencia (no aplicada — este ticket es solo el hallazgo, `VIC_41`
## tenía alcance de verificación, sin cambios de lógica)

Calcular el betweenness del grafo completo una sola vez en `main()` (o
dentro de `resiliencia_transporte`) y pasarlo como argumento opcional a
`centralidad_transporte` y a `curva_robustez` (con un `bet_inicial:
dict | None = None` que, si se da, se usa en vez de recalcular en
`i=0`). Cuidado con no romper la reproducibilidad ya verificada
(`VIC_41`): mismo `seed=42`, mismo grafo de entrada.

## Fuente

`doc/VIC-41-eval-grafo-centralidad.md` §1.
