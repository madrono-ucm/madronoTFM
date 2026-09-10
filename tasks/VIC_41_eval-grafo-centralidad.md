---
kind: vic-eval
title: "QA — grafo_centralidad (FIL_81): PageRank/Louvain, artefacto, vista del explorador"
owner: Claude (QA)
status: done
depends_on: [FIL_81]
created_at: "2026-09-10"
---

## Contexto

FIL_81 añade `centralidad_transporte()` a `modelado/grafo_analitica/
analisis.py` → `grafo_centralidad.{json,png}`, más una vista en el
explorador.

## Alcance — verificación

1. **Propiedades numéricas**: `Σ pagerank ≈ 1` (tol 1e-6); modularidad
   Louvain ∈ [0, 1); nº de comunidades > 1 y « nº de nodos; betweenness
   reutiliza el cálculo de la curva de robustez (no recalcula dos veces —
   `grep`).
2. **Caveat presente**: el JSON lleva la nota de `CONECTADO_CON` = 1
   viaje/línea (misma que `grafo_resiliencia.json`).
3. **Sin GDS**: `grep -rn "gds\.\|gds.session\|graph.project"` en el código
   nuevo → 0. Sin llamada a Neo4j en caliente en el análisis (es offline
   sobre el snapshot).
4. **Explorador**: `/grafo/explorador/analisis` incluye `centralidad`;
   `viz/build_grafo_explorador.py` tiene la vista y `tests/
   test_grafo_explorador.py` la cubre.
5. **Reproducibilidad**: semilla fija en Louvain (`seed=`) para que el
   artefacto no cambie entre corridas → test de estabilidad.
6. **Memoria**: el hallazgo (top-3 centralidad, nº comunidades vs 21
   distritos) llega a `VIC_38` / capítulo 6 del recorrido guiado.

## Criterios de aceptación

- Tests de `grafo_analitica` verdes, incluido el de propiedades.
- Artefacto determinista (dos corridas → mismo JSON salvo `generado`).
- 0 dependencia de GDS o de red.

## Hecho (2026-09-10, Claude QA)

Los 6 puntos verificados contra el artefacto real y el grafo real
(`grafo/_data/grafo_urbano.json.gz`). `pagerank_suma=0.999999` ✓,
`modularidad=0.932` ∈[0,1) ✓ (alto pero explicable: Louvain sobre grafo
de proximidad espacial), 54 comunidades vs 131 barrios ✓, sin GDS ni
Neo4j en caliente ✓. El explorador sí expone y testea `centralidad`
(`asistente/routers/grafo_explorador.py::_centralidad()` +
`asistente/tests/test_grafo_explorador_router.py`) — el ticket apuntaba
a los ficheros equivocados (`viz/build_grafo_explorador.py` es el
explorador estático alternativo, no tiene `centralidad`).
Reproducibilidad de `centralidad_transporte` confirmada byte-idéntica en
dos corridas reales; no se pudo ejercer `main()` completo dos veces en
esta EC2 por el bloqueador ya conocido de `FIL_61`
(`networkx==2.6.3` sin `louvain_communities`, no es una regresión de
`FIL_81`).

Un hallazgo real, menor: `centralidad_transporte` y el paso 0 de
`curva_robustez` calculan el mismo `betweenness_centrality` del grafo
completo por separado — recomputación evitable, sin impacto en
corrección. Abierto `FIL_85`.

Detalle completo en
[`doc/VIC-41-eval-grafo-centralidad.md`](../doc/VIC-41-eval-grafo-centralidad.md).
