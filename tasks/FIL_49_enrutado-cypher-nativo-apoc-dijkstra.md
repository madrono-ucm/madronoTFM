---
kind: fil
title: "Enrutado saludable nativo en Neo4j (apoc.algo.dijkstra) en vez de dos reimplementaciones Python paralelas"
owner: propuesto por Claude (QA), sin asignar
status: framing
allow_infra_apply: false
created_at: "2026-08-31"
depends_on: [FIL_37, FIL_43]
---

## Qué es

Encuadre técnico, a petición del usuario ("scope concretely what's actually
doable on Free tier — real Cypher-native routing vs. the current
export-and-reimplement pattern"), tras el hallazgo de `FIL_43`. No es una
implementación ni un compromiso de hacerlo — es la investigación pedida
para poder decidir con criterio.

## Por qué esto y no otra cosa

`ruta_saludable` es la única funcionalidad del proyecto genuinamente
*graph-shaped* (encaja con Neo4j), pero **hoy no toca Neo4j en absoluto en
tiempo de consulta**: `viz/rutas.py` (`networkx`) y
`asistente/ruta_saludable.py` (Dijkstra a mano con `heapq`) son dos
reimplementaciones independientes que leen un export JSON estático
(`viz/grafo_madrid.json` / `asistente/modelos/grafo_ruta.json`) — la base
de datos de grafo se usa como fuente de un volcado puntual, no como motor
de consulta. `FIL_43` (bug real, ya corregido) es evidencia directa del
riesgo de mantener dos implementaciones paralelas del mismo algoritmo: la
fórmula de coste divergió de la métrica reportada en una de las dos
copias, y solo se encontró por QA manual.

## Lo que permite realmente el tier gratuito (investigado, no supuesto)

Verificado contra la documentación oficial de Neo4j Aura (agosto 2026),
no memoria de entrenamiento:

- **APOC Core viene preinstalado en Aura** (todos los tiers, `Free`
  incluido — la página de soporte de APOC en Aura no distingue por tier
  para los procedimientos que lista), y dentro de APOC Core están
  `apoc.algo.dijkstra` y `apoc.algo.aStar` — **shortest path
  ponderado real**, sin necesitar la librería GDS completa (que sí es de
  pago fuera de Aura Graph Analytics, ver abajo).
  Fuente: <https://neo4j.com/docs/aura/apoc/>.
- Firma exacta de `apoc.algo.dijkstra`:
  `apoc.algo.dijkstra(startNode, endNode, relationshipTypesAndDirections,
  weightPropertyName, defaultWeight, numberOfWantedPaths) :: (path, weight)`.
  Fuente: <https://neo4j.com/docs/apoc/current/overview/apoc.algo/apoc.algo.dijkstra/>.
- **La restricción real**: `weightPropertyName` es el **nombre de una
  propiedad de relación ya almacenada**, no una expresión Cypher
  calculada al vuelo. No se le puede pasar
  `w_dist·dist + w_traf·traf_h1 + ...` directamente — el coste tiene que
  **existir como número guardado en la arista** antes de llamar al
  procedimiento.
- Aparte, **"Aura Graph Analytics"** (el GDS completo como servicio
  efímero, por sesión) **sí está disponible y no se factura en el tier
  Free/Trial** (fuente: <https://neo4j.com/docs/aura/graph-analytics/>) —
  pero es una herramienta distinta, pensada para análisis puntual por
  lotes (centralidad, detección de comunidades — encaja con `FIL_36`,
  "grafo como eje de memoria"), no para servir una consulta de enrutado
  por petición HTTP/MCP en vivo (arranca una sesión efímera, con un
  mínimo facturable de 10 minutos en el tier de pago).

## La implicación práctica: hace falta materializar el coste, no solo consultar

Como la exposición (tráfico/NO₂/O₃/ruido) varía por día y hora, y el
coste depende del perfil (4 combinaciones de pesos), un enrutado
Cypher-nativo con `apoc.algo.dijkstra` necesitaría un paso de
**materialización previa**: escribir en cada arista relevante (`PROXIMO_A`/
una relación de enrutado dedicada) una propiedad de coste por
`(perfil, hora)` — p. ej. `coste_general_h14`, `coste_ciclista_h8` — antes
de poder consultarla. No es exótico (es el mismo patrón que ya usa el
proyecto para `distancia_m` en `PROXIMO_A`, precalculado al cargar el
grafo, `grafo/relaciones.py`), pero es un paso de escritura nuevo que hoy
no existe.

**Orden de magnitud** (con las cifras reales verificadas esta sesión):
`viz/grafo_madrid.json` tiene **8.758 aristas**; si se materializaran las
**4 perfiles × 24 horas = 96** combinaciones de coste sobre todas ellas,
son ~840k valores numéricos escritos como propiedades de relación — un
volumen de *propiedades*, no de nodos/relaciones nuevas (que es lo que
cuenta contra el límite de tamaño del tier Free, ver
`infra/neo4j/README.md`), así que no debería chocar con el límite de
50k/200k nodos. Se puede acotar más fácilmente aún: el proyecto ya sirve
solo **3 días curados** de agosto (mismo patrón que `ruta_saludable` y el
mapa animado), así que materializar coste solo para esa ventana (no las
~29 días completas) reduce el volumen sin perder funcionalidad frente a
lo que ya existe.

## Qué se ganaría

- **Una sola fuente de verdad** para el coste de enrutado, en vez de dos
  implementaciones Python que ya han divergido una vez (`FIL_43`).
- Consultas nuevas que hoy no son prácticas en Python plano: p. ej. "qué
  otros lugares de interés quedan a ≤2 saltos de `CONECTADO_CON` de esta
  ruta" — traversal nativo de Cypher, no hay que reimplementarlo.
- Encaja con el argumento ya existente de `infra/neo4j/README.md` sobre
  por qué se eligió Neo4j: "consultas de proximidad y conectividad que un
  modelo relacional/tabular expresa mal o de forma cara" — el enrutado es
  exactamente ese caso, y hoy se resuelve fuera de Neo4j.

## Qué NO se gana / coste real

- **No es gratis en esfuerzo**: hay que diseñar y construir el paso de
  materialización (batch que escribe las propiedades de coste, con su
  propio ciclo de refresco), más migrar dos rutas de código
  (`viz/rutas.py` y `asistente/ruta_saludable.py`) a llamar
  `apoc.algo.dijkstra` vía el driver de Neo4j en vez de `networkx`/
  `heapq` — no es un cambio pequeño.
- El código Python actual **ya funciona y ya tiene el bug de `FIL_43`
  corregido** — esto no es una urgencia, es una mejora de arquitectura.
- Requiere acceso de escritura real a la instancia AuraDB Free (bloqueado
  para esta sesión de Claude, igual que el resto de credenciales de
  Neo4j — ver `doc/VIKT-06-recorrido-e2e.md`), así que la implementación
  la tendría que hacer la pista interactiva (Filippos), no `VIC_*`/`VIKT_*`.

## Recomendación

Dado lo cerca que está la entrega (17/9) y que el enrutado actual ya
funciona correctamente, **no urgir esto antes de la entrega** — encaja
mejor como mejora post-entrega o, si hay margen, como un M7 opcional
después de que `FIL_45`/`FIL_46` (capa social, framing) se resuelvan.
Vale la pena mantener este ticket como referencia técnica concreta (con
la firma real de `apoc.algo.dijkstra` y el orden de magnitud ya
calculado) para cuando alguien decida si merece la pena.

## Restricciones

- Ticket de encuadre (`framing`), sin código ni cambios de infraestructura
  aplicados.
- Sin acceso a la instancia Neo4j real desde esta sesión — todo lo de
  arriba está verificado contra documentación oficial de Neo4j, no contra
  la instancia real del proyecto. Antes de implementar, confirmar en la
  consola de Aura real que `apoc.algo.dijkstra` responde (`CALL
  apoc.help('dijkstra')` o una llamada de prueba) — la documentación
  pública no distingue tiers explícitamente, pero no se ha probado en
  vivo contra esta instancia concreta.
