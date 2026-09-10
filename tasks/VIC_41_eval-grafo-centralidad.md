---
kind: vic-eval
title: "QA — grafo_centralidad (FIL_81): PageRank/Louvain, artefacto, vista del explorador"
owner: Claude (QA)
status: pending
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
