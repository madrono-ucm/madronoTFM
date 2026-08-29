---
kind: vic-eval
title: "Evaluación técnica — grafo/"
owner: Claude (QA)
status: pending
created_at: "2026-08-29"
---

Parte de [`doc/PLAN-EVALUACION-TECNICA.md`](../doc/PLAN-EVALUACION-TECNICA.md).
Solo lectura/test.

## Alcance

- `python3 -m unittest discover -s grafo/tests -t .` — suite completa.
- Estado real de Neo4j (conteos de nodos/relaciones vía Cypher real) vs lo
  documentado en `doc/080`/`doc/094`/`doc/107` (aforos, parques, OSM).
- Confirmar si los gaps ya conocidos (enriquecimiento OSM limitado a
  muestra, `ML_01` sin usar el grafo para meteo) siguen igual.

## Criterios de aceptación

- Resultado real de la suite.
- Conteos reales de Neo4j, comparados con la última foto documentada.
- Cualquier discrepancia documentada, con ticket `FIL_*` si implica un
  cambio de código.
