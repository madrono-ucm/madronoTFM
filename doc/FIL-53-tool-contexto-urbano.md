# FIL-53 — `contexto_urbano`: consulta multi-salto del grafo

Las 12 tools anteriores que tocan el grafo hacen `MATCH` de **1 salto**
(`(:Lugar)-[:PROXIMO_A]-(:EstacionMedida)` + lookup en Gold). Esta 13.ª
tool hace un **traversal real** — el caso que `infra/neo4j/README.md` usa
para justificar la elección de Neo4j.

## Cómo funciona sin Neo4j

Lee `asistente/modelos/grafo_urbano.json.gz` (copia del artefacto de
`FIL_51`, reconstrucción offline del grafo real) y hace BFS ≤2 saltos en
Python puro (`heapq`/`deque`, sin `networkx`). Autocontenido, mismo criterio
que `asistente/athena.py` respecto a `grafo/`.

Si `NEO4J_*` estuviera en el entorno, la variante nativa sería
`MATCH path = (l:Lugar)-[:PROXIMO_A*1..2]-(x) ...` — queda para `FIL_54`.

## Qué devuelve (`ContextoUrbano`)

Para un `:Lugar` resuelto por texto:

| campo | vía |
|---|---|
| `barrio` / `distrito` | jerarquía **real** `UBICADO_EN`→`:Barrio` `PERTENECE_A`→`:Distrito` (no point-in-polygon al vuelo) |
| `estaciones_1_salto` | vecinos `PROXIMO_A` que son `:EstacionMedida`, por tipo (tráfico/aire/ruido/aforos), con `distancia_m` |
| `lugares_cercanos_2_saltos` | `:Lugar` a ≤2 saltos de `PROXIMO_A`, por tipo (parque/aparcamiento/cine/POI) |
| `transporte` | paradas alcanzables a ≤2 saltos de `CONECTADO_CON` desde la parada más cercana (nombre del ancla + conteo + ejemplos) |

Sin artefacto o sin lugar reconocido → `disponible=false` + `motivo` (con
ejemplos de lugares), nunca excepción.

## Ejemplo verificado

`contexto_urbano("Retiro")`:
- → **Jardines de El Buen Retiro** (parque) · barrio **Los Jerónimos** ·
  distrito **Retiro**
- 6 estaciones de tráfico a ≤300 m (la más cercana a 106 m)
- POIs a 1–2 saltos: Fuente de los Galápagos, Iglesia de San Manuel y San
  Benito, Palacio de Zabálburu…
- transporte: ancla **«Alcalá - Puerta de Alcalá»**, **21 paradas** a ≤2
  saltos (Cibeles, Círculo de Bellas Artes, Felipe II, Escuelas Aguirre…)

## Límites

- Los `:Lugar` son 586 (POIs turísticos + parques + aparcamientos + cines);
  un sitio que no esté en esas fuentes no se resuelve (p. ej. museos por su
  nombre común).
- `CONECTADO_CON` es un esqueleto (CRTM conserva un viaje por línea, ver
  `doc/FIL-52`), así que "alcanzable a ≤2 saltos" cuenta topología, no
  frecuencia de servicio.

`asistente/tests/test_contexto_urbano.py` (8). Suite `asistente/`+`tests/`
→ 186 en verde.
