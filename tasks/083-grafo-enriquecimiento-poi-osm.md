---
id: 83
slug: grafo-enriquecimiento-poi-osm
title: 'Grafo: enriquecer :Lugar con POIs y etiquetas de OpenStreetMap'
status: in_review
force: false
allow_infra_apply: false
branch: task/083-grafo-enriquecimiento-poi-osm
pr_number: 131
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/131
attempts: 0
next_retry_at: null
last_error: null
created_at: null
updated_at: '2026-08-25T20:40:44.254238+00:00'
started_at: '2026-08-25T20:27:33.080131+00:00'
submitted_at: '2026-08-25T20:40:44.254213+00:00'
merged_at: null
---

## Contexto

Los nodos `:Lugar` del grafo (381 a fecha de `080`) vienen hoy de
`poi_madrid` (dataset oficial de datos.madrid.es), `aparcamientos` y
`cartelera_cines` (ver `grafo/cargar_grafo.py::cargar_grafo`). Ninguno de
esos tres usa OpenStreetMap. Esta tarea añade OSM como fuente adicional,
**gratuita y sin API key**, para enriquecer esos lugares con etiquetas que
ninguna fuente municipal trae hoy (categoría/`amenity`, horario de apertura,
accesibilidad, cocina de un restaurante, etc.) — decisión tomada tras
descartar Google Places para esto: OSM cubre bien geodatos/etiquetas de
lugar, pero **no tiene ningún dato de afluencia o popularidad en vivo**
(eso lo cubren las tareas `084`/`085` con `aforos_peatones_bicicletas`, no
esta).

**Decisión ya tomada — no la reabras**: esta tarea *enriquece* `:Lugar` ya
existentes con propiedades adicionales, no crea nodos `:Lugar` nuevos a
partir de OSM. Unir por geolocalización (Haversine, ya en `grafo/geo.py`,
tarea 070) es más seguro que unir por nombre para una primera integración:
evita duplicar cobertura con `poi_madrid` y mantiene el número de nodos
estable. Si en el futuro se quiere ampliar cobertura con lugares que solo
existen en OSM, que sea una tarea aparte, deliberada.

**API elegida**: [Overpass API](https://overpass-api.de/api/interpreter)
(instancia pública, sin autenticación). Respeta su uso razonable: una sola
consulta por bounding box de Madrid (o unas pocas, una por distrito si el
tamaño de la respuesta lo justifica), nunca en bucle, con un `User-Agent`
descriptivo identificando el proyecto — mismo criterio de "carga puntual,
no programada" que ya usan `poi_madrid.py`/`barrios_distritos_madrid.py`
(dato de referencia que cambia muy rara vez, no un productor continuo).

## Objetivo

Nuevo productor `ingesta/capturas/enriquecimiento_osm_lugares.py` que
consulta Overpass por POIs (`amenity`/`shop`/`tourism`/`leisure`) dentro del
bounding box de Madrid, y una extensión de `grafo/` que une esos POIs por
proximidad a los `:Lugar` ya cargados, añadiendo sus etiquetas OSM como
propiedades nuevas del nodo.

## Alcance concreto

1. `ingesta/capturas/enriquecimiento_osm_lugares.py` (nuevo, mismo patrón
   que el resto de `ingesta/capturas/`: `fetch_*`/`normalize_*`,
   `capture_sample(..., out_path)`, sin bucle ni `--interval-seconds`, sin
   `BronzeWriter` — dato de referencia puntual, igual que `poi_madrid.py`).
   Usa `requests` (ya en `ingesta/requirements.txt`, no añadas ninguna
   librería nueva de OSM) contra Overpass QL. Normaliza cada POI a un
   esquema mínimo: `osm_id`, `osm_type` (`node`/`way`/`relation`), `name`,
   `amenity`/`shop`/`tourism`/`leisure` (el tag que haya matcheado),
   `opening_hours`, `wheelchair`, `location.lat`/`location.lon`.
2. `ingesta/capturas/samples/enriquecimiento_osm_lugares_sample.json`:
   muestra pequeña commiteada (intenta una captura real primero — Overpass
   es pública y no necesita credenciales; si por lo que sea no es viable en
   este entorno, documenta el motivo exacto igual que hace `doc/012` con
   Google, no lo des por hecho sin comprobarlo en vivo).
3. `grafo/geo.py`: si hace falta, añade un helper de "vecino más cercano
   dentro de un radio" sobre la Haversine ya existente (o reutiliza lo que
   ya haya, revisa antes de añadir código nuevo).
4. `grafo/nodos.py` o un módulo nuevo pequeño: función que, dados los
   `:Lugar` ya extraídos (`nodos.lugares_from_*`) y los POIs OSM
   normalizados, añade a cada `:Lugar` las propiedades `osm_id`,
   `osm_amenity`, `osm_opening_hours` cuando exista un POI OSM a **≤30
   metros** (Haversine) — sin match, el `:Lugar` queda igual que hoy (no
   añadas propiedades `null` de más). Si varios POIs OSM caen dentro del
   radio de un mismo `:Lugar`, quédate con el más cercano.
5. `grafo/cargar_grafo.py`: integra el enriquecimiento en la construcción de
   `lugares` antes de `loader.load_lugares(lugares)`, usando los datos OSM
   obtenidos vía el nuevo productor (léelos del fichero de muestra o repite
   la consulta Overpass real, tu elección — documenta cuál).
6. `infra/neo4j/schema/schema.cypher` (o el fichero de esquema real que uses
   como referencia — revísalo primero): documenta las 3 propiedades nuevas
   de `:Lugar` como opcionales.
7. Tests: `ingesta/tests/test_enriquecimiento_osm_lugares.py` (sin red,
   fixtures) y ampliación de los tests de `grafo/nodos.py`/`grafo/geo.py`
   correspondientes con el nuevo match por proximidad.
8. Actualiza `ingesta/README.md` y `grafo/README.md`.

## Restricciones

- No añadas `osmnx`, `overpy` ni ninguna otra dependencia de terceros para
  Overpass — `requests` + Overpass QL a mano, mismo criterio que el resto
  del proyecto evita dependencias de geometría/mapas pesadas (ver `070`).
- No crees `:Lugar` nuevos a partir de OSM — solo enriquecimiento de los ya
  existentes (ver "Decisión ya tomada" arriba).
- No toques `afluencia_prevista`, `populartimes` ni nada relacionado con
  Google Maps — eso es fuera de alcance aquí (ver tareas `084`/`085`).
- No relances `grafo/cargar_grafo.py` contra la instancia real de Neo4j en
  esta tarea (escribe el código y déjalo listo, como hacía `067`/`070`
  antes de que existiera instancia real) — la recarga real, si aplica, es
  responsabilidad de quien la revise después, para no arriesgar el grafo de
  producción sin revisión humana previa.

## Criterios de aceptación

- El productor OSM funciona de extremo a extremo contra Overpass real (o,
  si no fue posible, está documentado el motivo exacto, igual que `doc/012`
  con Google).
- El enriquecimiento de `:Lugar` por proximidad está implementado y
  testeado con casos reales del fixture (un lugar con match OSM cercano, uno
  sin ningún POI OSM dentro del radio).
- Tests en verde.
- `ingesta/README.md` y `grafo/README.md` actualizados.
