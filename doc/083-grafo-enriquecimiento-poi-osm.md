# 083 — Grafo: enriquecer `:Lugar` con POIs y etiquetas de OpenStreetMap

## Qué se implementó

Nueva fuente de **enriquecimiento** (no de nodos nuevos, decisión ya fijada
por el enunciado) para los `:Lugar` del grafo urbano: OpenStreetMap vía
Overpass API (pública, sin API key), unida por proximidad geográfica
(≤30 m, Haversine) a los `:Lugar` ya existentes (`poi_madrid`,
`aparcamientos`, `cartelera_cines_estrenos`), añadiendo `osm_id`,
`osm_amenity` (categoría/`amenity`/`shop`/`tourism`/`leisure`) y
`osm_opening_hours` cuando hay match.

- **`ingesta/capturas/enriquecimiento_osm_lugares.py`** (nuevo, mismo patrón
  que `poi_madrid.py`/`barrios_distritos_madrid.py`: carga batch puntual de
  referencia, sin `--interval-seconds` ni `BronzeWriter`). Consulta Overpass
  QL sobre el bounding box real del municipio de Madrid
  (`(40.3119774, -3.8889539, 40.6437293, -3.5183264)`, obtenido en vivo con
  `out bb;` sobre la relación administrativa oficial de OSM,
  `relation(5326784)`, `ine:municipio=28079`) para los tags `amenity`,
  `shop`, `tourism`, `leisure`, con la salida truncada a 250 elementos
  (`out body 250;`) — una consulta sin límite devuelve más de 75.000 nodos
  (`out count;` verificado en vivo), demasiado para commitear como muestra.
  `select_sample_pois` filtra en local los que tienen `name` y coordenadas,
  quedándose con los primeros 6.
- **`grafo/geo.py::nearest_within_radius(lat, lon, candidates, radius_m,
  get_coords)`**: helper genérico (no específico de OSM) sobre
  `haversine_m`, ya existente desde la tarea 070.
- **`grafo/nodos.py::enrich_lugar_con_osm`/`enrich_lugares_con_osm`**: añade
  las 3 propiedades opcionales a un `:Lugar` si hay un POI de OSM a ≤30 m
  (el más cercano si hay varios); sin match, o sin `ubicacion` en el
  `:Lugar`, no añade ninguna propiedad `null` de más.
- **`grafo/extract.py::fetch_osm_pois_sample()`**: lee la muestra
  commiteada en vez de repetir la consulta Overpass real en cada carga del
  grafo (ver "Decisiones no obvias").
- **`grafo/cargar_grafo.py`**: llama a `enrich_lugares_con_osm` sobre
  `lugares` justo antes de `loader.load_lugares(lugares)`. No se ha
  ejecutado contra la instancia real de Neo4j (restricción explícita del
  enunciado).
- **`grafo/cypher.py::lugar_query`**: persiste `osm_id`/`osm_amenity`/
  `osm_opening_hours` con `node.get(...)` (mismo criterio "SET plano, sin
  preservar valor anterior" que `nombre`/`tipo`/`fuente`).
- **`infra/neo4j/schema/schema.cypher`**: documenta las 3 propiedades como
  opcionales en el bloque de `:Lugar`.

## Verificación real contra Overpass

Se ejecutó `python3 -m ingesta.capturas.enriquecimiento_osm_lugares` en
vivo durante esta sesión (sin credenciales, endpoint público): la muestra
commiteada (`ingesta/capturas/samples/enriquecimiento_osm_lugares_sample.json`)
son 6 POIs reales de Madrid (dos gasolineras, un hotel, un cine, una pista
de hielo y un restaurante con `opening_hours` real), no datos inventados.
Un primer intento con una consulta más pesada recibió un error transitorio
de "servidor ocupado" de Overpass, resuelto reintentando tras una breve
espera — comportamiento ya cubierto por los reintentos con backoff de
`_fetch_with_retries`.

## Tests

- `ingesta/tests/test_enriquecimiento_osm_lugares.py` (10 tests, sin red):
  fixture propio `overpass_pois_sample.json` con 7 elementos y casos límite
  (tag `shop` en vez de `amenity`, campos opcionales ausentes, elemento con
  tag reconocido pero sin `name`, elemento sin ningún tag de interés,
  elemento sin `lat`/`lon`), más un test de que la muestra commiteada
  cumple el esquema esperado.
- `grafo/tests/test_geo.py::NearestWithinRadiusTests` (5 tests) y
  `grafo/tests/test_nodos.py::EnrichLugaresConOsmTests` (4 tests): usan la
  muestra real commiteada de POIs de OSM, no coordenadas inventadas — un
  `:Lugar` construido con las coordenadas exactas de un POI real de la
  muestra ("Café Comercial", match, distancia 0, verifica
  `osm_amenity="restaurant"` y el `opening_hours` real), y otro en Puerta
  del Sol (a más de 1 km de cualquier punto de la muestra, verificado con
  `haversine_m`, sin match, sin propiedades `osm_*` añadidas).

`grafo/tests/` pasa completo: 89 tests. `ingesta/tests/`: 277 tests.

## Decisiones no obvias

- **`cargar_grafo.py` lee la muestra local (`fetch_osm_pois_sample`), no
  repite la consulta Overpass real en cada carga.** El bounding box
  completo de Madrid devuelve más de 75.000 nodos — recargar eso cada vez
  que se ejecuta `cargar_grafo.py` no sería un uso responsable de una
  instancia pública gratuita de terceros, y tampoco tiene sentido para un
  dato de referencia que apenas cambia. Con solo 6 POIs en la muestra, el
  enriquecimiento real sobre los ~381 `:Lugar` de la tarea 080 será casi
  nulo hasta que exista una captura completa subida a Bronze S3 (ver
  "Relevante para tareas futuras").
- **`amenity` como nombre de campo genérico en el esquema normalizado**: el
  valor del tag que matcheó (`amenity`/`shop`/`tourism`/`leisure`, en ese
  orden de prioridad) se guarda bajo la clave `"amenity"` independientemente
  de cuál de los 4 tags de OSM era en origen — para que coincida
  directamente con el nombre de la propiedad `osm_amenity` del `:Lugar`
  enriquecido, sin tener que traducir el nombre del campo entre la captura
  y el grafo.
- **Umbral de 30 m, distinto del umbral de 300 m de `PROXIMO_A`**: aquí se
  busca "es el mismo sitio" (enriquecer un `:Lugar` con sus propias
  etiquetas), no "está cerca" (la semántica de `PROXIMO_A`, pensada para
  relacionar nodos distintos). Fijado por el enunciado, no derivado de
  ningún cálculo.
- **`osm_id` con formato `"<osm_type>:<osm_id>"`** (p. ej. `"node:26065697"`),
  coherente con el formato `"<fuente>:<id_origen>"` que ya usa `id` en el
  resto de labels del grafo.

## Restricciones respetadas

- No se han creado `:Lugar` nuevos a partir de OSM — solo enriquecimiento
  de los ya existentes por proximidad geográfica.
- No se ha añadido `osmnx`, `overpy` ni ninguna otra dependencia de
  terceros para Overpass — solo `requests` (ya en
  `ingesta/requirements.txt`) + Overpass QL a mano.
- No se ha tocado `afluencia_prevista`, `populartimes` ni nada relacionado
  con Google Maps (fuera de alcance, tareas 084/085).
- No se ha ejecutado `grafo/cargar_grafo.py` contra la instancia real de
  Neo4j en esta tarea — el código queda listo, la recarga real es
  responsabilidad de quien revise el PR.

## Relevante para tareas futuras

- **Cobertura real limitada a 6 POIs de muestra.** El siguiente paso
  natural es una captura real y completa de POIs de OSM (todo el bounding
  box de Madrid, no solo 250 elementos truncados — posiblemente iterando
  por distrito para mantener cada respuesta individual manejable) subida a
  Bronze S3, igual que se hizo con `poi_madrid` en la tarea 080.
  `cargar_grafo.py` no necesitaría ningún cambio salvo apuntar
  `fetch_osm_pois_sample` (o una función equivalente que lea de S3) a esos
  datos completos.
- El bloqueo real para ejecutar `cargar_grafo.py` end-to-end (incluido este
  enriquecimiento) sigue siendo el mismo desde la tarea 043: aunque ya
  existe una instancia AuraDB Free real con datos cargados (tarea 080), esta
  tarea no ha vuelto a ejecutar la carga completa — queda para quien revise
  el PR decidir si recargar el grafo de producción con estas propiedades
  nuevas.
