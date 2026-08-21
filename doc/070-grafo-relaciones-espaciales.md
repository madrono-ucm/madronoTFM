# 070 — Grafo: relaciones espaciales `UBICADO_EN` y `PROXIMO_A`

## Objetivo

Las tareas 041/067 dejaron deliberadamente pendientes las relaciones
espaciales genéricas del esquema del grafo (`infra/neo4j/schema/
schema.cypher`, tarea 043): `UBICADO_EN` (point-in-polygon de cualquier nodo
con ubicación contra `:Barrio`) y `PROXIMO_A` (proximidad genérica entre
cualquier par de nodos con ubicación). Esta tarea las implementa, sin
conectar a ninguna instancia Neo4j real (sigue bloqueada el alta manual de
AuraDB Free, tarea 043).

## Qué se ha añadido

- **`grafo/geo.py`** (nuevo, Python puro, sin `shapely` ni ninguna otra
  dependencia de geometría — decisión ya fijada por el enunciado): point-in-
  polygon por ray casting sobre GeoJSON (`Polygon` y, defensivamente,
  `MultiPolygon` aunque el fixture real commiteado solo trae `Polygon`) y
  distancia Haversine.
- **`grafo/relaciones.py`**: `ubicado_en(nodos_con_ubicacion, barrios)` y
  `proximo_a(nodos_con_ubicacion, umbral_m=300)`, ambas usando `geo.py`.
- **`grafo/cypher.py`**: `ubicado_en_query()`/`proximo_a_query()` (Python
  puro, mismo patrón que las funciones `*_query()` existentes) y
  `Neo4jLoader.load_ubicado_en`/`load_proximo_a`.
- **`grafo/cargar_grafo.py`**: `cargar_grafo()` ahora también junta los
  nodos con ubicación (`estaciones_medida + paradas_transporte + lugares`) y
  carga `UBICADO_EN`/`PROXIMO_A` tras `PERTENECE_A`.
- **Tests**: `grafo/tests/test_geo.py` (nuevo, 12 tests) +
  `grafo/tests/test_relaciones.py` ampliado (`UbicadoEnTests`/
  `ProximoATests`, 10 tests nuevos) + `grafo/tests/test_cypher.py` ampliado
  (2 tests nuevos) — 70 tests en total en `grafo/tests/`, todos en verde,
  verificados **sin** el driver `neo4j` instalado (confirmado con
  `python3 -c "import neo4j"` fallando con `ModuleNotFoundError` antes de
  correr la suite).
- `grafo/README.md`: sección nueva sobre `UBICADO_EN`/`PROXIMO_A`,
  actualizada la tabla de estructura, el bloque de "cómo se cargaría", la
  sección de tests, y "Relevante para tareas futuras" (las dos entradas
  duplicadas y ya desactualizadas sobre estas dos relaciones, dejadas por la
  tarea 069, se sustituyen por una única entrada marcándolas como
  resueltas).

## Decisiones de diseño relevantes

- **`ubicado_en(nodos_con_ubicacion, barrios)` recibe los registros Bronce
  crudos de `barrios_distritos_madrid`, no los nodos `:Barrio` ya
  transformados por `nodos.barrios_from_bronze`.** Esta era justo la
  decisión que la tarea 069 dejaba abierta ("decidir si se extiende
  `nodos.py` o si el point-in-polygon vive en un módulo separado con acceso
  al Bronze crudo"): se ha optado por lo segundo. `schema.cypher` no define
  ninguna propiedad de geometría para `:Barrio` (solo `codigo`/`nombre`/
  `distrito_codigo`), así que extender `nodos.barrio_from_bronze` para
  cargar `geometry` habría metido en el `dict` de nodo un campo que
  `cypher.barrio_query` no debería `SET` nunca en Neo4j — más limpio
  mantener `nodos.py` con el contrato que ya tenía (testado desde la tarea
  067) y pasarle la geometría cruda directamente a `geo.find_barrio` desde
  `relaciones.ubicado_en`.
- **`ubicado_en_query` hace `MATCH (n {id: $nodo_id})` sin restringir el
  label.** Los tres labels con `ubicacion` (`:Lugar`/`:EstacionMedida`/
  `:ParadaTransporte`) tienen cada uno su propio constraint `id UNIQUE`
  (`schema.cypher`), pero los prefijos `fuente` de `id` que fija `nodos.py`
  (`trafico`/`calidad_aire`/`ruido` para EstacionMedida;
  `transporte_publico_emt`/`bicimad`/`crtm_red_transporte_madrid` para
  ParadaTransporte; `poi_madrid`/`aparcamientos`/`cartelera_cines_estrenos`
  para Lugar) no se solapan entre sí — así que `id` ya es único en la
  práctica en todo el grafo, no solo dentro de su propio label, y no hace
  falta que `relaciones.ubicado_en` sepa a qué label pertenece cada nodo
  para construir la relación.
- **"Tipo distinto" en `PROXIMO_A` usa la propiedad `tipo` de `nodos.py`
  (`"trafico"`, `"bicimad"`, `"poi_turistico"`...), no el label de Neo4j.**
  El enunciado ilustraba la regla con "dos `:EstacionMedida` de tráfico no
  necesitan `PROXIMO_A` entre sí" — la lectura literal más ajustada de ese
  ejemplo es que la distinción es a nivel de `tipo` (el mismo campo que ya
  usa `nodos.py`/`cypher.py`), no solo de label: así, una `:EstacionMedida`
  de tráfico y una de ruido sí generan `PROXIMO_A` entre sí, aunque
  compartan label.
- **Umbral 300 m fijado por el enunciado, sin límite de relaciones por
  nodo** — implementado tal cual, verificado con un test dedicado (20
  vecinos dentro del umbral generan 20 relaciones).
- **`proximo_a` es `O(n²)`, sin ningún índice espacial** (p. ej. un grid de
  celdas de ~300 m). No se ha optimizado: el enunciado no lo pedía y añadir
  esa complejidad sin datos reales que la justificaran habría sido
  sobre-ingeniería. Documentado en `grafo/README.md` como posible punto a
  revisar si el volumen de nodos crece mucho antes de ejecutar
  `cargar_grafo.py` contra una instancia real (con los volúmenes reales
  conocidos desde la tarea 069 — unos pocos miles de nodos con ubicación en
  total — es factible en Python, aunque no instantáneo).

## Verificación de `geo.py` contra datos reales

Point-in-polygon y Haversine se han verificado con datos reales, no
inventados:

- **Point-in-polygon**: el barrio "011" Palacio del fixture real
  commiteado (`ingesta/capturas/samples/
  barrios_distritos_madrid_barrios_sample.json`) contiene el Palacio Real
  de Madrid (40.4180, -3.7143) y no contiene un punto de Barcelona
  (41.3874, 2.1686) — verificado tanto manualmente (antes de escribir el
  test) como en el propio test (`test_geo.py::FindBarrioTests`).
- **Haversine**: Puerta del Sol (40.4169, -3.7035) a Plaza Mayor (40.4155,
  -3.7074) da ~365 m con la implementación de este módulo, dentro del rango
  conocido de esa distancia real (~350-400 m en línea recta); Madrid a
  Barcelona da ~505 km, también dentro del rango real conocido (~500-510
  km).

## Restricciones respetadas

- No se ha añadido `shapely` ni ninguna otra dependencia de geometría —
  `grafo/geo.py` es Python puro (solo `math` de la stdlib).
- No se ha implementado `CONECTADO_CON` (tarea 071, alcance deliberadamente
  separado).
- No se ha conectado a ninguna instancia Neo4j real — `cargar_grafo.py`
  sigue sin ejecutarse contra nada real, solo sus funciones `*_query()` y
  `relaciones.py`/`geo.py` se han testado con fixtures.
- No se ha instalado el driver `neo4j` en esta EC2 — confirmado con
  `python3 -c "import neo4j"` fallando antes de correr los 70 tests, todos
  en verde.

## Relevante para tareas futuras

- Con `UBICADO_EN`/`PROXIMO_A` implementadas, la única relación que falta
  del esquema es `CONECTADO_CON` (tarea 071). A diferencia de las dos de
  esta tarea, necesitará datos de secuencia/orden de paradas por línea, que
  `extract.py` no expone todavía — los `fetch_paradas_*` actuales devuelven
  paradas sueltas, no secuencias ordenadas. `crtm_red_transporte_madrid` es
  la fuente más prometedora (su Bronze sí trae `stops` en el orden de la
  ruta dentro de cada `route_id`), pero esa información no llega hoy a
  `extract.fetch_paradas_crtm_bronze()` en forma utilizable para esto
  (solo la lista plana de paradas, ya deduplicada por `nodos.py`) — probablemente
  haga falta una función nueva en `extract.py` que conserve el orden de
  `stops` por ruta.
- La nota de rendimiento de `proximo_a` (`O(n²)`, ver arriba) no bloquea
  nada hoy, pero conviene revisarla antes de un primer `cargar_grafo.py`
  end-to-end si el volumen de nodos con ubicación crece significativamente
  respecto a los ~6000 conocidos desde la tarea 069.
- El bloqueo real para ejecutar cualquier parte de `grafo/` contra un grafo
  real sigue siendo el mismo desde la tarea 043 (alta manual de AuraDB
  Free) — ninguna tarea de ETL puede resolverlo.
