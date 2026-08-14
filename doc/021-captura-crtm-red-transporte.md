# 021 — Captura de la red estructural de transporte de Madrid (GTFS, CRTM; muestra)

## Qué se implementó

`ingesta/capturas/crtm_red_transporte_madrid.py`: undécimo productor de
carga puntual de referencia del proyecto (tras `callejero_madrid.py` tarea
009, `barrios_distritos_madrid.py` tarea 010, `poi_madrid.py` tarea 011,
`calendario_laboral_madrid.py` tarea 020). Descarga los feeds GTFS
estáticos del Consorcio Regional de Transportes de Madrid (CRTM) y los
normaliza a un esquema mínimo de **líneas con las paradas de un viaje
representativo** — no el grafo completo de horarios, tal como permitía el
enunciado. Sin bucle, sin `--interval-seconds`, sin credenciales.

- `ingesta/capturas/samples/crtm_red_transporte_madrid_sample.json`:
  muestra real commiteada — 12 líneas reales (3 de metro, 3 de EMT bus, 3
  de metro ligero, 3 de cercanías), descargadas en vivo ejecutando
  `python3 -m ingesta.capturas.crtm_red_transporte_madrid`.
- `ingesta/tests/test_crtm_red_transporte_madrid.py`: 17 tests sin red,
  usando un GTFS sintético construido en memoria con las mismas columnas
  que los feeds reales.
- `ingesta/README.md`: nueva sección para esta fuente.

## Fuente y descubrimiento del catálogo

El buscador web de `datos.crtm.es` (portal ArcGIS Hub) es una SPA que no
devuelve resultados por HTTP directo. El catálogo completo sí es accesible
sin autenticación vía el feed DCAT-US 1.1 estándar que expone todo portal
ArcGIS Hub (`https://datos.crtm.es/api/feed/dcat-us/1.1.json`). Filtrando
ese catálogo por "gtfs" aparecen **6 feeds GTFS estáticos**: Metro (1.5 MB),
EMT bus (18 MB), Metro Ligero/Tranvía (0.4 MB), Cercanías (6 KB), autobuses
urbanos de la Comunidad de Madrid (8 MB) y autobuses interurbanos de la
Comunidad de Madrid (72 MB, el más pesado del catálogo). Cada uno se
descarga sin autenticación desde el endpoint estándar de contenido de
ArcGIS Online (`.../sharing/rest/content/items/{item_id}/data`), el mismo
que usa el botón "Download" del portal.

**Decisión de alcance**: la muestra por defecto (`DEFAULT_MODES`) incluye
los tres modos que el enunciado pedía investigar explícitamente (metro,
EMT, metro ligero) más cercanías (por el hallazgo de calidad de datos
descrito abajo). Los dos feeds de autobuses de la Comunidad de Madrid
quedan soportados vía `CRTM_GTFS_MODES` pero fuera de la muestra por
defecto: cubren municipios fuera de la capital (no la red estructural de
la ciudad de Madrid, objeto de esta tarea) y el más grande (72 MB) no
aporta variedad de esquema sobre el de EMT ya incluido.

## Hallazgo: no existe GTFS-RT abierto de CRTM

Se buscó explícitamente un feed GTFS-RT (alertas, posición de vehículos,
retrasos) del CRTM: ni en el catálogo DCAT del propio portal (ni en su
portal hermano `datos-movilidad.crtm.es`), ni en Transitland (el catálogo
independiente de referencia mundial de feeds GTFS/GTFS-RT, que solo
registra el GTFS estático de CRTM), ni en hosts candidatos (`api.crtm.es`,
`opendata.crtm.es`, ambos inalcanzables). **Conclusión: CRTM no publica
tiempo real de forma abierta a nivel de red multimodal.** Esto no
desbloquea la tarea 003 (EMT, bloqueada por registro con email sin
verificar) — la única vía de llegadas en vivo verificada sigue siendo
`transporte_publico_madrid.py` — pero es un hallazgo negativo documentado
para no repetir esta búsqueda en el futuro.

## Dos hallazgos de calidad de datos en los GTFS de CRTM

Documentados y no corregidos (mismo criterio que la tarea 020 con el
calendario laboral):

1. El feed de `cercanias` trae `routes.txt`/`stops.txt` completos (10
   líneas con sus estaciones) pero `trips.txt`/`stop_times.txt` están
   **vacíos** — CRTM no modela el servicio programado de Cercanías (lo
   opera Renfe). Sus líneas en la muestra tienen `"stops": []`.
2. Dentro de `metro`, la línea 3 (`4__3___`) tampoco tiene ningún
   `trip_id`, a diferencia del resto de líneas del mismo feed (1, 2,
   4-12, R) — otro hueco real de la fuente, no relacionado con el caso
   anterior.

## Decisiones técnicas relevantes

- **Esquema mínimo**: un único `trip_id` representativo por línea (el
  primero en sentido `direction_id="0"`, o el primero disponible) provee
  la secuencia ordenada real de paradas sin necesidad de modelar
  calendarios, frecuencias o el resto de viajes.
- **`stop_times.txt` en streaming, nunca cargado entero**: es, con
  diferencia, el fichero más grande de un GTFS (84 MB sin comprimir en el
  feed de EMT). `_read_stop_times_for_trips` lo recorre fila a fila
  directamente desde el ZIP, descartando lo que no pertenece a los pocos
  `trip_id` de la muestra — mismo criterio de "no leer el fichero completo
  en el contexto de la sesión" que ya aplicaron `callejero_madrid.py` y
  `barrios_distritos_madrid.py` con sus CSV.
- **Elementos de accesibilidad excluidos de las paradas**: `stops.txt`
  incluye, junto a las paradas reales, elementos con prefijo `acc_` en el
  `stop_id` (ascensores, accesos de superficie..., `location_type="2"`)
  que `_index_boarding_stops` filtra explícitamente.
- **Un único dataset con campo `mode`**: sigue el patrón ya establecido en
  las tareas 013/016/017 para representar varias fuentes/redes
  complementarias del mismo dominio en un solo fichero.

## Investigación sin dejar residuos en disco

Para decidir el esquema y verificar los dos hallazgos de calidad de datos
se descargaron temporalmente los 6 ZIP GTFS completos (hasta 72 MB el de
autobuses interurbanos) en `/tmp` y se inspeccionaron con `zipfile`/`csv`
de Python (listado de miembros, primeras filas) — nunca con la herramienta
`Read` sobre el contenido completo. Todos los ZIP se borraron al terminar
la investigación; el único artefacto persistente es la muestra pequeña
commiteada.

## Tests

`ingesta/tests/test_crtm_red_transporte_madrid.py`: no dependen de la red.
Construyen un GTFS sintético en memoria (mismas columnas que los feeds
reales) que incluye a propósito los dos casos reales de la fuente (línea
sin trips, elementos de accesibilidad en `stops.txt`). Cubren
`_read_stop_times_for_trips` (streaming, filtrado), `_index_boarding_stops`,
`_select_representative_trip`, `select_sample_routes`, `normalize_route`
(caso feliz y caso sin viajes), el flujo completo `fetch_and_normalize_mode`
(sustituyendo `fetch_gtfs_zip` por un doble) y una verificación de esquema
sobre la propia muestra commiteada, incluyendo que el hueco de datos de
`cercanias` se refleja tal cual. Suite completa del proyecto verificada
tras el cambio: **182 tests** (165 previos + 17 nuevos), todos en verde.

## Relevante para tareas futuras

- El hallazgo de que **no existe GTFS-RT abierto de CRTM** es la pieza que
  faltaba para decidir qué hacer con la tarea 003: no hay una alternativa
  multimodal que la sustituya, así que desbloquear las llegadas en vivo de
  Madrid sigue dependiendo de completar el registro de MobilityLabs (EMT)
  con un email verificado.
- `MODE_FEEDS` ya registra los 6 feeds GTFS del catálogo (incluidos
  `urbano_cm`/`interurbano_cm`, fuera de la muestra por defecto): una
  tarea futura que necesite la red de autobuses de la Comunidad de Madrid
  (no solo la ciudad) puede reutilizar este módulo tal cual, vía
  `CRTM_GTFS_MODES`, sin escribir un capturador nuevo.
- Los dos huecos de datos documentados (Cercanías sin `trips`/`stop_times`,
  línea 3 de metro sin `trips`) son de la fuente, no de este módulo: si en
  una recaptura futura CRTM los completa, no hace falta ningún cambio de
  código — el módulo ya maneja el caso "línea sin viajes" (`stops: []`)
  sin asumir que siempre hay datos.
- El esquema deliberadamente no modela el grafo completo de horarios
  (calendarios, frecuencias, todos los viajes de cada línea): si una tarea
  futura necesita eso (p.ej. para calcular tiempos de trayecto reales),
  debe volver a los GTFS completos — este módulo ya sabe descargarlos
  (`fetch_gtfs_zip`) y parsear cualquiera de sus ficheros
  (`_read_csv_member`/`_read_stop_times_for_trips`), solo falta ampliar la
  normalización.
- `TODO(kafka)` queda marcado en el módulo por consistencia con el resto
  de cargas de referencia (009-011, 020), aunque no se espera que esta
  fuente conecte nunca a un broker Kafka: su destino natural es el grafo
  Neo4j (líneas/paradas como nodos) o una tabla de dimensión.
