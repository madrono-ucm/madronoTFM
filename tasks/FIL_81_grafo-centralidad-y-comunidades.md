---
kind: fil
title: "Analítica de grafo: centralidad (PageRank) y comunidades (Louvain) de la red de transporte — artefacto cacheado"
owner: Filippos (interactive)
status: pending
allow_infra_apply: false
created_at: "2026-09-10"
depends_on: [FIL_64]
milestone: "M7"
target: "2026-09-24"
---

## Motivación

De GDS ("Aura Graph Analytics") no se ejecuta **nada**: toda la analítica de
grafo es `networkx` offline sobre el snapshot (`FIL_64` — resiliencia). GDS
es serverless por sesión (coste posible, efímero) → misma decisión que
`FIL_64`: hacerlo **offline con networkx** y **cachearlo** como artefacto,
igual que `grafo_resiliencia.json`.

Faltan dos análisis de valor:
- **PageRank / centralidad de intermediación** sobre `CONECTADO_CON` — qué
  paradas son estructuralmente más centrales en la red (más allá de
  "articulación" sí/no).
- **Comunidades (Louvain)** — qué barrios/paradas se agrupan por
  conectividad; contraste con la división administrativa por distrito.

## Alcance

1. **`modelado/grafo_analitica/analisis.py`** += `centralidad_transporte()`:
   `nx.pagerank`, `nx.betweenness_centrality` (ya se calcula en la curva de
   robustez — reutilizar), `nx.community.louvain_communities`. Salida
   `grafo_centralidad.{json,png}` en `modelado/evaluation/artifacts/`:
   top-N paradas por PageRank y por betweenness, nº de comunidades, tamaño y
   distrito(s) dominante(s) de cada una, modularidad, y una nota-caveat
   (`CONECTADO_CON` modela 1 viaje/línea — `FIL_64`).
2. **Explorador** (`viz/build_grafo_explorador.py` + router `analisis`):
   nueva vista "Transporte · centralidad" que colorea nodos por PageRank y
   pinta las comunidades; el endpoint `/grafo/explorador/analisis` añade
   `centralidad`.
3. **Recorrido guiado del mapa**: una línea en el capítulo 6 (hallazgos del
   grafo) con el top-3 de centralidad y el nº de comunidades vs 21 distritos.
4. Sin GDS, sin coste AWS nuevo, sin tocar Neo4j en caliente.

## Verificación

- `modelado/grafo_analitica/tests/`: PageRank suma ~1, nº de comunidades en
  rango razonable, modularidad ∈ [0,1], artefacto con las claves esperadas.
- `tests/test_grafo_explorador.py`: la vista/endpoint expone `centralidad`.
- Suite `grafo_analitica` + `tests/` verde.
