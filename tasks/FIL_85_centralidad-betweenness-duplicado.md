---
kind: fil
title: "grafo_analitica: betweenness del grafo completo se calcula dos veces en la misma ejecución"
status: pending
severity: baja (rendimiento, no correctitud)
created_at: "2026-09-10"
source: "VIC_41 (QA de FIL_81)"
depends_on: [FIL_81, FIL_64]
---

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
