---
kind: fil
title: "Analítica de grafo sobre el grafo urbano real — centralidad, comunidades (§7 / FIL_36)"
owner: Filippos (interactive)
status: done
resolved_at: "2026-08-31"
allow_infra_apply: false
created_at: "2026-08-31"
depends_on: [FIL_51]
milestone: "M7"
target: "2026-09-11"
---

## Motivación

`infra/neo4j/README.md` justifica la elección de Neo4j por "consultas de
proximidad y conectividad que un modelo tabular expresa mal" — pero el
sistema entregado apenas hace conectividad. Este ticket produce **hallazgos
reales de algoritmo de grafo** que validan esa elección y dan material a
`§7` / `FIL_36`.

## Alcance — `modelado/grafo_analitica/` (`networkx`, offline)

Sobre `grafo/_data/grafo_urbano.json` (`FIL_51`):

1. **Centralidad en `CONECTADO_CON`** (red de transporte real):
   - grado, intermediación (betweenness), cercanía.
   - → *qué paradas/hubs son estructuralmente críticos* (los que, si caen,
     desconectan más el sistema). Tabla top-15 + figura.
2. **Detección de comunidades en `PROXIMO_A`** (Louvain/label-propagation):
   - comunidades data-driven vs los **131 barrios administrativos**:
     coincidencia (ARI/NMI), casos donde el grafo "junta" barrios que la
     administración separa (y al revés). → hallazgo para la memoria.
3. **Cruce con la importancia de aristas del STGNN** (`tier2_*_aristas.json`
   / `meta.importancia_aristas`): ¿las aristas que el STGNN marca como
   influyentes caen sobre corredores de alta intermediación del grafo? →
   ¿el modelo "redescubre" la estructura?
4. **Estadísticos de conectividad**: componentes, diámetro, distribución de
   grado, cobertura `UBICADO_EN` por distrito (qué distritos tienen pocos
   sensores — sesgo declarado en §7).

Salidas: `modelado/evaluation/artifacts/grafo_*.{csv,json,png}` +
subsección para la memoria (coord. `VIKT_10`).

## Coste

Cero AWS, cero Neo4j. `networkx` (ya disponible).

## Nota

Si hay margen y acceso, "Aura Graph Analytics" (GDS efímero, no factura en
Free) daría los mismos algoritmos nativos — pero `networkx` sobre el
artefacto de `FIL_51` es suficiente y reproducible sin credenciales.
