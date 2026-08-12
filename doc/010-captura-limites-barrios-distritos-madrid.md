# 010 — Captura de límites de barrios y distritos de Madrid (muestra, carga puntual)

## Qué se implementó

Noveno productor de datos de la Fase 1 (Ingesta), del mismo tipo que
`callejero_madrid.py` (tarea 009): no es un dato que cambie con el tiempo,
sino un dato de **referencia** (los límites administrativos de Madrid apenas
varían) — una **carga batch puntual**, no un stream, que nunca necesitará
programarse periódicamente ni siquiera cuando exista infraestructura real.

- `ingesta/capturas/barrios_distritos_madrid.py`: descarga los límites
  (geometría) de los 21 distritos y 131 barrios del municipio de Madrid y
  los normaliza a un esquema mínimo pensado para relacionar el resto de
  fuentes del proyecto (tráfico, calidad del aire, ruido...) con una unidad
  geográfica administrativa común. Sin bucle, sin `--interval-seconds`, sin
  descargar el dataset completo.
- `ingesta/capturas/samples/barrios_distritos_madrid_distritos_sample.json` +
  `barrios_distritos_madrid_barrios_sample.json`: la muestra pequeña
  commiteada como fixture (3 distritos con 2 barrios cada uno).
- `ingesta/tests/test_barrios_distritos_madrid.py` +
  `ingesta/tests/fixtures/barrios_distritos_distritos_sample.json` +
  `barrios_distritos_barrios_sample.json`: tests con `unittest` (sin red)
  que verifican el algoritmo de simplificación Douglas-Peucker, la
  normalización de distritos/barrios (`Polygon` y `MultiPolygon`), el tope
  de barrios por distrito, y que la muestra commiteada cumple el esquema
  esperado.
- `ingesta/README.md`: nueva sección para esta fuente (fuente elegida y por
  qué, formato real encontrado, decisión de simplificación de geometría,
  variables de entorno, esquema, y la nota sobre el acceso en vivo desde
  este entorno).

## Fuente elegida y por qué

Los datasets "Distritos municipales de Madrid" (id
`300497-0-distritos-municipales-madrid`) y "Barrios municipales de Madrid"
(id `300496-0-barrios-madrid`) de datos.madrid.es publican varios formatos
(KML, XLSX, CSV, ZIP/SHP), pero ninguno resultó a la vez ligero y
consultable de forma parcial: el CSV/XLSX no traen geometría (solo id,
nombre y área); el KML de distritos trae el contorno como `LineString` (no
un polígono relleno) y hay que descargarlo completo; el KML de barrios
**no fue accesible** durante esta sesión (`Barrios.kml` redirige a una
página de mantenimiento genérica del Ayuntamiento,
`indexServicioNoDisponible.html` — el mismo tipo de problema de
disponibilidad puntual del portal ya documentado en la tarea 009).

En su lugar, uno de los recursos listados del dataset de distritos apunta
(con el formato mal etiquetado como "CSV" en el catálogo — un error de
metadatos del propio Ayuntamiento, no algo inventado en esta tarea) a un
servicio **ArcGIS REST (MapServer)** público:
`https://sigma.madrid.es/hosted/rest/services/CARTOGRAFIA/LIMITES_ADMINISTRATIVOS/MapServer`,
con capas de polígonos reales ("DISTRITOS" capa 26, "BARRIOS" capa 25, del
grupo de escalas más detallado del servicio). Se prefirió a los ficheros
KML/ZIP por dos motivos: (1) devuelve GeoJSON con polígonos reales ya
reproyectados a WGS84 con un simple parámetro de query (`outSR=4326`), sin
parsear coordenadas DMS ni añadir una dependencia de geoprocesado
(`pyproj`/`shapely`); y (2) admite filtrar, ordenar y limitar resultados
**en el servidor** (`where`, `orderByFields`, `resultRecordCount`), así que
esta captura nunca descarga el conjunto completo (21 distritos / 131
barrios) a este entorno, ni siquiera en memoria — a diferencia de
`callejero_madrid.py` o `ruido_madrid.py`, que sí tuvieron que traer un CSV
completo porque su fuente no ofrecía filtrado remoto.

Se ha verificado en vivo desde este entorno que el servicio MapServer es
accesible **sin ninguna autenticación ni API key**.

## Captura real en vivo

Se completó una **captura real en vivo**: los fixtures commiteados son 3
distritos reales (Centro, Arganzuela, Retiro) con 2 barrios reales cada uno
(Palacio, Embajadores; Imperial, Acacias; Pacífico, Adelfas), descargados
ejecutando `python3 -m ingesta.capturas.barrios_distritos_madrid` tal cual
contra el servicio ArcGIS REST público durante esta sesión — no son datos de
ejemplo generados a mano.

## Decisiones de diseño (por qué)

- **Simplificación de geometría con Douglas-Peucker propio, no una
  dependencia de geoprocesado**: algunos distritos tienen miles de vértices
  sin simplificar (Fuencarral - El Pardo, el mayor, 2.910 puntos), que
  inflarían una muestra pensada para ser pequeña. Se implementó
  Douglas-Peucker a mano (sin `shapely`/`pyproj`, dependencias que este
  proyecto no usa en ningún otro productor) con una tolerancia configurable
  en grados (`MADRID_BOUNDARIES_SIMPLIFY_TOLERANCE_DEG`, por defecto
  `0.0001`, ~8-11 m en la latitud de Madrid): con ese valor, Fuencarral - El
  Pardo pasa de 2.910 a ~450 puntos conservando la forma general. Cada
  registro guarda `simplified`/`simplify_tolerance_deg` para que quede
  explícito que la geometría no es necesariamente bit a bit la de la fuente;
  poner la tolerancia a `0` la desactiva y conserva la geometría exacta.
- **Sin descarga del dataset completo, ni siquiera en memoria**: a
  diferencia de `callejero_madrid.py` (tarea 009) o `ruido_madrid.py` (tarea
  007), que tuvieron que descargar un CSV completo porque su fuente no
  ofrecía filtrado remoto, aquí el servicio ArcGIS REST admite pedir
  directamente "los N distritos ordenados por código" y "los barrios de
  estos distritos" — la muestra nunca requiere traer los 21 distritos /
  131 barrios completos a este entorno.
- **Muestra de barrios acotada a los distritos de la muestra de distritos**:
  se seleccionan primero los distritos (los primeros `N` por código) y
  después solo los barrios de esos distritos concretos (con un tope por
  distrito), para que el fixture resultante sea un conjunto padre-hijo
  coherente y no una mezcla de barrios sueltos sin su distrito —mismo
  criterio que "primero los viales, luego solo sus cruces" en
  `callejero_madrid.py` (tarea 009).
- **`district_id`/`neighbourhood_id` como cadenas con ceros a la izquierda**
  (`"01"`, `"011"`), no enteros: son los códigos oficiales que usa la fuente
  y que una futura carga completa necesitará para cruzar con otros recursos
  del mismo origen (mismo criterio que `vial_id` en la tarea 009).
- **`geometry` soporta `Polygon` y `MultiPolygon`** aunque en la
  investigación de esta tarea los 21 distritos y 131 barrios actuales son
  todos `Polygon` simples (verificado descargando y comprobando el `type` de
  las 152 features completas): se dejó el soporte por robustez ante una
  futura redelimitación que introdujera un distrito/barrio con varias
  partes, sin necesidad de tocar el esquema.
- **Sin `BronzeWriter` ni modo `--interval-seconds`**, igual que
  `callejero_madrid.py` (tarea 009) y por la misma razón: es un dato de
  referencia que nunca necesitará recaptura periódica, ni siquiera en
  producción — no es una limitación temporal por falta de infraestructura
  como en las tareas 003-008.
- **Sin variables de entorno de credenciales**: el servicio ArcGIS REST
  usado es público y no las necesita.

## Relevante para tareas futuras

- El servicio ArcGIS REST es completamente público y no depende de ningún
  registro pendiente: el día que se implemente la carga completa real (21
  distritos + 131 barrios) hacia su destino (S3/Neo4j), no hay ningún
  bloqueo de credenciales que resolver antes, y la misma técnica de
  filtrado/orden en servidor sigue aplicando (aunque para la carga completa
  simplemente no haría falta el `where`/`resultRecordCount` acotado).
- El KML del recurso "Barrios municipales de Madrid" (`Barrios.kml`) no fue
  accesible durante esta sesión (redirige a una página de mantenimiento del
  Ayuntamiento). Si una tarea futura necesitara ese recurso KML en concreto
  (p.ej. para comparar con el servicio ArcGIS REST usado aquí), convendría
  reintentarlo primero, ya que podría tratarse de una caída puntual del
  portal, como ya se documentó en la tarea 009 para la interfaz HTML
  clásica de datos.madrid.es.
- Cuando se implemente la carga completa hacia Neo4j, esta fuente encaja de
  forma natural con la relación distrito→barrios como jerarquía padre-hijo
  en el grafo urbano (ver memoria, apartado 5.2), y con `district_codes` del
  callejero (tarea 009) y con los distritos/barrios de las estaciones de
  ruido (`district`/`neighbourhood` en `ruido_madrid.py`, tarea 007) como
  puntos de unión con el resto de fuentes del proyecto.
- La tolerancia de simplificación por defecto (`0.0001` grados) es una
  decisión razonable para una muestra pequeña legible como fixture, pero no
  necesariamente la adecuada para una carga completa real: una tarea futura
  debería revisar si conservar la geometría exacta (`tolerancia=0`) o ajustar
  la tolerancia según el uso final (visualización a escala de ciudad vs.
  cálculos geométricos exactos como "¿qué barrio contiene este punto?").
- `TODO(kafka)` queda marcado en el módulo por consistencia con el resto de
  productores, aunque no se espera que esta fuente de referencia conecte
  nunca a un broker Kafka (mismo razonamiento que en la tarea 009).
