# FIL-52 — Analítica de grafo sobre el grafo urbano real

Motivación: `infra/neo4j/README.md` justifica Neo4j por "consultas de
proximidad y conectividad que un modelo tabular expresa mal", pero el
sistema entregado apenas las usa. Este análisis produce hallazgos de
algoritmo de grafo sobre el grafo reconstruido (`FIL_51`,
`grafo_urbano.json.gz`) — `networkx`, sin AWS ni Neo4j.

`python -m modelado.grafo_analitica.analisis` →
`modelado/evaluation/artifacts/grafo_*`.

## 1. Centralidad en `CONECTADO_CON` (red de transporte)

3.375 paradas, 3.947 aristas, componente mayor 3.053. Top intermediación
(betweenness), todas **paradas de autobús EMT**, no de metro:

| parada | modo | grado | intermediación |
|---|---|---|---|
| Canillejas | emt | 6 | 0,314 |
| Metro O'Donnell | emt | 8 | 0,291 |
| Aeropuerto T1 – Salidas | emt | 4 | 0,259 |
| O'Donnell | emt | 9 | 0,213 |
| Hospital Ramón y Cajal | emt | 6 | 0,211 |

**Hallazgo**: los cuellos de botella estructurales de la red no son las
grandes estaciones de metro sino los **intercambiadores de bus del este**
(Canillejas, O'Donnell) — coherente con que las líneas EMT entrelazan la
red donde el metro va radial.

**Caveat**: `crtm_red_transporte_madrid` conserva *un viaje representativo
por línea* (ver su docstring), así que `CONECTADO_CON` es un **esqueleto
disperso** (grado medio ~2,3); la intermediación describe ese esqueleto, no
la frecuencia real de servicio.

## 2. Comunidades en `PROXIMO_A` vs barrios administrativos

Louvain sobre la componente mayor de `PROXIMO_A` → **55 comunidades**
data-driven frente a los **131 barrios**. `ARI = 0,364`, `NMI = 0,753`,
`modularidad = 0,934`.

**Hallazgo**: la estructura de proximidad multi-dominio (sensores + paradas
+ lugares) recupera la mayor parte de la información de barrio (`NMI` alto)
pero es **~2,4× más gruesa** — el grafo agrupa barrios adyacentes que
"funcionan juntos" (hay comunidades que abarcan 10–11 barrios). A la vez,
~40 barrios quedan **partidos** en ≥3 comunidades: la proximidad real cruza
los límites administrativos.

## 3. Cobertura de sensores por distrito

`EstacionMedida` por distrito (vía `UBICADO_EN`→`Barrio`→`Distrito`):
mínimos en **Vicálvaro (62), Barajas (63), Villa de Vallecas (80)**;
máximos en Fuencarral-El Pardo, Ciudad Lineal, Hortaleza. **Cuantifica el
sesgo periférico** que la memoria §7 declara: la periferia sureste está
infra-instrumentada.

## 4. STGNN vs conectividad del grafo

Para las 15 aristas de `importancia_aristas` del STGNN de tráfico, se mira
el **grado en `PROXIMO_A`** de sus sensores extremo (cuántos nodos de otros
dominios tienen cerca). `Spearman(importancia, grado medio) = 0,34`
(`p = 0,22`).

**Lectura honesta**: hay una **tendencia positiva débil y no significativa**
— los sensores que el STGNN marca como influyentes tienden a estar en
puntos mejor conectados (más cruces con transporte/POIs), pero con solo 15
aristas no hay potencia para concluir. Nota: `PROXIMO_A` no conecta
sensores de tráfico entre sí (`relaciones.proximo_a` salta pares del mismo
`tipo`), así que no se puede comparar la topología del STGNN
(`coords-knn8`) arista a arista con `PROXIMO_A`.

## Para la memoria (§7 / `FIL_36`)

Figura `grafo_analitica.png` + los cuatro puntos de arriba. Valida la
elección de Neo4j con resultados de algoritmo de grafo reales, y aporta dos
hallazgos citables (comunidades ≠ barrios; hubs de bus como cuellos de
botella) además de cuantificar el sesgo de cobertura.
