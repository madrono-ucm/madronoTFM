---
kind: vic-eval
title: "Memoria — integrar los hallazgos de grafo (FIL_52/64/65/66/67) en §6 y §7"
owner: Víctor / Claude (QA)
status: pending
created_at: "2026-09-09"
depends_on: [FIL_52, FIL_64, FIL_65, FIL_66, FIL_67, VIC_34, VIC_36]
---

## Contexto

`infra/neo4j/README.md` justifica Neo4j por "consultas de proximidad y
conectividad que un modelo tabular expresa mal", pero la versión actual de
la memoria apenas explota esa idea. La sesión del 2026-09-09 produjo
material real para el capítulo de grafo:

- **FIL_52** centralidad + comunidades Louvain (grafo vs 21 distritos).
- **FIL_64** resiliencia: puntos de articulación / puentes / k-core / curva
  de robustez (ataque dirigido vs aleatorio). Con caveat de modelado.
- **FIL_65/66** el grafo pasó de índice espacial mínimo a incluir estaciones
  meteo, recintos de eventos y **atributos por entidad** (qué contaminantes
  mide cada estación de aire, capacidades, subárea, altitud).
- **FIL_67** marco conceptual: *grafo = "dónde y qué hay cerca" · Gold =
  "qué valor, en el tiempo" · ML = "qué valor tendrá"*; y `consulta_grafo`
  (15ª tool) como acceso flexible al grafo.

## Alcance — redacción de memoria (coordinar con VIKT_10 editorial)

1. **§6 (arquitectura/explotación del grafo)**: actualizar el inventario del
   grafo a las cifras finales (`VIC_34`): 5 labels, ~9.8k nodos, 4
   relaciones, atributos por nodo. Explicar el patrón medallion→grafo
   (entidades fijas geolocalizadas = nodos; series de medidas = Gold) y por
   qué `agenda_eventos`/`aforos`/`transporte_publico_emt` quedan como
   quedan.
2. **§7 (resultados)**: subsección de analítica de grafo con FIL_52 + FIL_64.
   Incluir la figura `grafo_resiliencia.png` y la tabla top de puntos de
   articulación / comunidades. Redactar el **caveat** (`k_max=2`, "un viaje
   por línea") de forma que no se lea como diagnóstico operativo real
   (texto propuesto en `VIC_36`).
3. **§7.4 (limitaciones)**: pipeline congelado desde 2026-08-30 → los
   atributos de FIL_66 se calculan sobre una ventana corta; `contaminantes`
   por estación es estable, pero `magnitudes` de meteo salió fino
   (`temperature_c`/`humidity_pct`) por la congelación.
4. **Cruce STGNN ↔ grafo**: FIL_52 ya reportaba Spearman(importancia de
   arista, grado `PROXIMO_A`); tras FIL_66 subió a ρ≈0,64 (p<0,01) al
   densificarse el grafo. Decidir si va en §7 como "el modelo redescubre la
   estructura del grafo".

## Criterios de aceptación

- Borrador de las subsecciones (§6 grafo, §7 analítica de grafo, nota §7.4)
  entregado y revisado con `VIKT_10`.
- Todas las cifras trazables a un artefacto commiteado o a una consulta
  reproducible (`grafo/consulta.py`).
- Sin afirmaciones que `VIC_34`/`VIC_36` no hayan validado.
