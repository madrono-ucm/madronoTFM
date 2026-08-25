// ============================================================================
// Esquema inicial del grafo urbano de Madrid (tarea 043)
//
// Ver infra/neo4j/README.md para el diseño completo (por qué estos tipos de
// nodo/relación, cómo se corresponden con los datasets de Gold). Este script
// solo declara constraints e índices -- Neo4j es "schema-optional": los
// tipos de nodo (labels) y de relación no se "crean" aparte, se declaran
// implícitamente la primera vez que un `CREATE`/`MERGE` los usa. Este
// fichero es el contrato explícito y versionado de qué labels/propiedades
// espera el resto del proyecto (futuro ETL Gold -> Neo4j, consultas), y
// además hace cumplir unicidad de identificadores con constraints reales.
//
// Idempotente: todas las sentencias usan `IF NOT EXISTS`, así que se puede
// ejecutar varias veces sin error (p.ej. tras añadir una entrada nueva a
// este fichero en una tarea futura).
//
// NO se ha ejecutado contra ninguna instancia real en esta tarea (no existen
// credenciales todavía, ver "Bloqueo de alta" en el README). Uso previsto,
// una vez exista una instancia AuraDB Free con credenciales:
//
//   cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USERNAME" -p "$NEO4J_PASSWORD" \
//     -f infra/neo4j/schema/schema.cypher
//
// o pegando el contenido en el "Query" pane de Neo4j Browser/Aura Console.
// ============================================================================

// ----------------------------------------------------------------------------
// :Distrito -- los 21 distritos administrativos de Madrid.
// Origen: dataset `barrios_distritos_madrid` (doc/010), capa Gold agregada
// por distrito.
// Propiedades esperadas: codigo (string, código INE/Ayuntamiento, clave de
// negocio), nombre (string).
// ----------------------------------------------------------------------------
CREATE CONSTRAINT distrito_codigo_unique IF NOT EXISTS
FOR (d:Distrito) REQUIRE d.codigo IS UNIQUE;

// ----------------------------------------------------------------------------
// :Barrio -- los ~131 barrios de Madrid, cada uno perteneciente a un
// :Distrito (relación PERTENECE_A). Origen: mismo dataset que Distrito.
// Propiedades esperadas: codigo (string, clave de negocio), nombre (string),
// distrito_codigo (string, redundante con la relación PERTENECE_A para
// permitir filtrar por distrito sin atravesar la relación cuando conviene).
// ----------------------------------------------------------------------------
CREATE CONSTRAINT barrio_codigo_unique IF NOT EXISTS
FOR (b:Barrio) REQUIRE b.codigo IS UNIQUE;

CREATE INDEX barrio_distrito_codigo IF NOT EXISTS
FOR (b:Barrio) ON (b.distrito_codigo);

// ----------------------------------------------------------------------------
// :Lugar -- nodo genérico para cualquier sitio de interés con ubicación fija
// que no sea en sí una estación de medida ni una parada de transporte:
// puntos de interés turístico (`poi_madrid`, doc/011), aparcamientos
// (`aparcamientos_madrid`, doc/005), salas de cine (`cartelera_cines_madrid`,
// doc/023), grandes recintos (`agenda_grandes_recintos_madrid`, doc/022)...
// `tipo` distingue el dataset/subtipo de origen (p.ej. "poi_turistico",
// "aparcamiento", "cine", "recinto"); no se modela un label por dataset
// porque todos comparten el mismo patrón de relaciones (UBICADO_EN,
// PROXIMO_A) y separarlos en labels distintos solo complicaría las
// consultas que buscan "cualquier lugar cerca de X" sin aportar nada que
// `tipo` no dé ya.
// Propiedades esperadas: id (string, "<fuente>:<id_origen>", único),
// nombre (string), tipo (string), fuente (string, nombre del dataset Gold
// de origen), ubicacion (Point, WGS84, `point({latitude: ..., longitude: ...,
// crs: "wgs-84"})`).
// Propiedades opcionales (tarea 083, enriquecimiento con OpenStreetMap vía
// Overpass API -- solo presentes si hubo un POI de OSM a <=30m del :Lugar,
// ver grafo/nodos.py::enrich_lugar_con_osm): osm_id (string,
// "<osm_type>:<osm_id>", identidad del elemento de OSM), osm_amenity
// (string, valor del tag amenity/shop/tourism/leisure de OSM que matcheó),
// osm_opening_hours (string, tag opening_hours de OSM tal cual, formato
// libre de la fuente, sin parsear).
// ----------------------------------------------------------------------------
CREATE CONSTRAINT lugar_id_unique IF NOT EXISTS
FOR (l:Lugar) REQUIRE l.id IS UNIQUE;

CREATE INDEX lugar_tipo IF NOT EXISTS
FOR (l:Lugar) ON (l.tipo);

CREATE POINT INDEX lugar_ubicacion IF NOT EXISTS
FOR (l:Lugar) ON (l.ubicacion);

// ----------------------------------------------------------------------------
// :EstacionMedida -- puntos fijos de medición/sensorización: tráfico
// (`trafico_madrid`, doc/002), calidad del aire (`calidad_aire_madrid`,
// doc/006), ruido (`ruido_madrid`, doc/007), aforos de peatones/bicicletas
// (`aforos_peatones_bicicletas`, doc/054/087). Deliberadamente NO almacena
// series temporales de medidas (eso sigue viviendo en Gold/Athena, fuera de
// Neo4j) -- aquí solo la identidad y ubicación del punto de medida, para
// poder relacionarlo espacialmente con Lugar/Barrio/ParadaTransporte.
// Propiedades esperadas: id (string, "<fuente>:<id_origen>", único),
// tipo (string: "trafico" | "calidad_aire" | "ruido" |
// "aforos_peatones_bicicletas"), fuente (string), ubicacion (Point, WGS84).
// ----------------------------------------------------------------------------
CREATE CONSTRAINT estacion_medida_id_unique IF NOT EXISTS
FOR (e:EstacionMedida) REQUIRE e.id IS UNIQUE;

CREATE INDEX estacion_medida_tipo IF NOT EXISTS
FOR (e:EstacionMedida) ON (e.tipo);

CREATE POINT INDEX estacion_medida_ubicacion IF NOT EXISTS
FOR (e:EstacionMedida) ON (e.ubicacion);

// ----------------------------------------------------------------------------
// :ParadaTransporte -- nodos de la red de transporte: paradas de la EMT
// (`transporte_publico_emt`, doc/003), estaciones de BiciMAD (`bicimad`,
// doc/004), paradas/estaciones de la red CRTM -- metro, cercanías, interurbano
// (`crtm_red_transporte`, doc/021). Es el nodo sobre el que se apoya la
// relación CONECTADO_CON (ver README) para modelar la red de transporte
// como un grafo navegable.
// Propiedades esperadas: id (string, "<fuente>:<id_origen>", único),
// tipo (string: "emt" | "bicimad" | "metro" | "cercanias" | ...),
// fuente (string), ubicacion (Point, WGS84).
// ----------------------------------------------------------------------------
CREATE CONSTRAINT parada_transporte_id_unique IF NOT EXISTS
FOR (p:ParadaTransporte) REQUIRE p.id IS UNIQUE;

CREATE INDEX parada_transporte_tipo IF NOT EXISTS
FOR (p:ParadaTransporte) ON (p.tipo);

CREATE POINT INDEX parada_transporte_ubicacion IF NOT EXISTS
FOR (p:ParadaTransporte) ON (p.ubicacion);

// ============================================================================
// Tipos de relación (documentados aquí; Neo4j no permite declarar
// constraints de existencia/tipo sobre relaciones en Community/AuraDB Free,
// así que el contrato es este comentario + la disciplina del futuro código
// de carga, igual que ya ocurre con los `dataclass` de `ingesta/capturas/`
// frente al JSON de Bronze sin esquema forzado).
//
//   (:Barrio)-[:PERTENECE_A]->(:Distrito)
//     Un barrio pertenece a exactamente un distrito. Sin propiedades.
//
//   (:Lugar|:EstacionMedida|:ParadaTransporte)-[:UBICADO_EN]->(:Barrio)
//     El barrio que contiene el punto (point-in-polygon contra los límites
//     de `barrios_distritos_madrid`, calculado por el futuro ETL, no en
//     Neo4j). Sin propiedades.
//
//   (a)-[:PROXIMO_A {distancia_m: float}]->(b)
//     Proximidad espacial entre dos nodos cualesquiera con `ubicacion`
//     (Lugar, EstacionMedida, ParadaTransporte, en cualquier combinación),
//     por debajo de un umbral de distancia que decida el ETL que la genere
//     (no fijado aquí). Se crea en una sola dirección por par para evitar
//     duplicar el grafo; una consulta que necesite ambos sentidos usa un
//     patrón no dirigido (`(a)-[:PROXIMO_A]-(b)`).
//
//   (:ParadaTransporte)-[:CONECTADO_CON {modo: string, linea: string}]->(:ParadaTransporte)
//     Adyacencia real de la red de transporte: dos paradas consecutivas de
//     una misma línea (`modo`: "emt" | "metro" | "cercanias" | "bicimad";
//     `linea`: identificador de línea de origen, o null para BiciMAD, que no
//     tiene líneas). Es lo que convierte ParadaTransporte en un grafo
//     navegable (ruta más corta, nº de trasbordos), no solo en puntos
//     sueltos con proximidad.
// ============================================================================
