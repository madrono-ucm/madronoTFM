# 009 — Captura del callejero y grafo viario de Madrid (muestra, carga puntual)

## Qué se implementó

Octavo productor de datos de la Fase 1 (Ingesta), pero de un tipo distinto a
los anteriores (002-008): no es un dato que cambie con el tiempo (tráfico,
calidad del aire, meteorología...), sino un dato de **referencia** — el
callejero de Madrid apenas cambia — así que esta captura es, a propósito,
una **carga batch puntual**, no solo una "muestra reducida por falta de
infraestructura" como las tareas 003-008. Nunca necesitará programarse
periódicamente, ni siquiera cuando exista infraestructura real.

- `ingesta/capturas/callejero_madrid.py`: descarga el callejero vigente del
  Ayuntamiento de Madrid — viales (calles, avenidas, plazas...) y sus
  cruces con otros viales — y lo normaliza a un esquema mínimo pensado para
  alimentar el futuro grafo urbano en Neo4j (memoria, apartado 5.2). Sin
  bucle, sin `--interval-seconds`, sin escribir en la capa Bronze
  particionada ni el dataset completo a disco.
- `ingesta/capturas/samples/callejero_madrid_vias_sample.json` +
  `callejero_madrid_cruces_sample.json`: la muestra pequeña commiteada como
  fixture (5 viales con sus 20 cruces).
- `ingesta/tests/test_callejero_madrid.py` +
  `ingesta/tests/fixtures/callejero_vias_sample.csv` +
  `ingesta/tests/fixtures/callejero_cruces_sample.csv`: tests con
  `unittest` (sin red) que verifican el parseo de coordenadas DMS, distritos
  múltiples, código postal `"varios"`, el descarte de viales sin
  coordenadas, el filtrado/deduplicado de cruces, y que la muestra
  commiteada cumple el esquema esperado.
- `ingesta/README.md`: nueva sección para esta fuente (fuente elegida y por
  qué, formato real encontrado, por qué es una carga puntual y no periódica,
  variables de entorno, esquema, y la nota sobre el acceso en vivo desde
  este entorno).

## Fuente elegida y por qué

Dataset "Callejero. Información adicional asociada. Códigos postales, zonas
SER, categoría fiscal, parcela catastral, etc." (id `200075-0-callejero`) de
[datos.madrid.es](https://datos.madrid.es/dataset/200075-0-callejero), en
concreto dos de sus recursos CSV: **"Viales oficiales y topónimos"** (un
registro por vial vigente, con código, nombre, tipo, distritos, código(s)
postal(es), y coordenadas de inicio/fin — el **nodo** del grafo viario) y
**"Cruces de viales con coordenadas geográficas"** (un registro por cada
cruce entre dos viales, con la coordenada del cruce — la **arista** del
grafo viario).

Se descartaron tres alternativas: "Callejero oficial del Ayuntamiento de
Madrid" (id `213605-0-callejero-oficial-madrid`, mismo origen CADMA, pero
sin coordenadas de inicio/fin ni cruces — solo numeración por
distrito/barrio); "Callejero oficial. Viales vigentes" (id
`300735-0-mapas-callejero-viales`, solo WMS, sin recurso tabular
descargable); y "Callejero Oficial del Ayuntamiento de Madrid (Servicio
Web)" (id `300274-0-callejero-oficial-webservice`, un SOAP pensado para
sincronizar cambios incrementales, no para una carga inicial).

Nota sobre el propio portal: durante la investigación, la interfaz HTML de
datos.madrid.es (`https://datos.madrid.es/egob/...`) devolvía una página de
mantenimiento genérica del Ayuntamiento; el catálogo real ahora corre sobre
un backend CKAN accesible en `https://datos.madrid.es/api/3/action/...`,
que sí respondió con normalidad y fue el que se usó para localizar el
dataset (`package_search`/`package_show`). Los enlaces de descarga de los
recursos CSV (`https://datos.madrid.es/dataset/.../resource/.../download/...`)
son independientes de esa interfaz HTML y funcionaron sin problema.

Se ha verificado en vivo desde este entorno que ambos recursos elegidos son
accesibles **sin ninguna autenticación ni API key**.

## Formato real encontrado

Ambos CSV se publican en **ISO-8859-1 (Latin-1)** con `;` como separador.
Las coordenadas WGS84 vienen como texto en formato grados-minutos-segundos
con el símbolo `º` (p.ej. `"3º40'16.72'' W"`), no como decimal — el módulo
las convierte a grados decimales. El "Código de vía" (8 dígitos, p.ej.
`"00000127"`) enlaza ambos ficheros y se conserva tal cual (no se convierte
a entero, para no perder los ceros a la izquierda ni la capacidad de cruce
con la fuente oficial). El campo "Distritos atravesados" puede traer varios
códigos separados por `-`; el de "Códigos postales" puede ser un único
código, el literal `"varios"`, o estar vacío. El CSV de cruces trae cada
cruce dos veces (una vez con cada vial como "tratado", en direcciones
opuestas); el módulo solo conserva los cruces cuyo vial "tratado" es uno de
los viales de la muestra, para no duplicar la misma arista dos veces.

## Captura real en vivo

Se completó una **captura real en vivo**: los fixtures commiteados son 5
viales reales (Isabel Colbrand, González Dávila, de la Abada, de los
Abades, de la Abadesa) con sus 20 cruces reales, descargados ejecutando
`python3 -m ingesta.capturas.callejero_madrid` tal cual contra ambos
recursos públicos durante esta sesión — no son datos de ejemplo generados a
mano. El CSV de viales tenía 10.093 viales vigentes y el de cruces 31.654
cruces en el momento de la captura (~3.7 MB y ~12.4 MB respectivamente).

## Decisiones de diseño (por qué)

- **Dos fixtures (viales + cruces), no uno solo**: el objetivo de la tarea
  es explícitamente el "grafo viario", no solo un listado de calles. Un
  grafo necesita nodos y aristas; forzar ambos conceptos en un único
  registro habría perdido la relación N:N entre viales (cada vial cruza con
  varios otros). Dos ficheros con un `vial_id` compartido como clave de
  unión es el formato más directo de cargar como nodos+relaciones en Neo4j
  más adelante (tarea futura, ver memoria apartado 5.2).
- **Muestra de viales = "primeros N con coordenadas válidas" (mismo criterio
  que tareas anteriores), luego cruces derivados de esos viales**: en vez de
  muestrear cruces de forma independiente, se seleccionan primero los
  viales y después solo los cruces que salen de ellos — así la muestra
  resultante es un grafo realmente conectado y navegable, no un conjunto de
  aristas sueltas sin sus nodos.
- **Tope de cruces por vial (`MADRID_STREETS_MAX_CROSSINGS_PER_VIAL`, 8 por
  defecto)**: algunas avenidas grandes tienen más de 100 cruces en la
  fuente; sin este tope, la muestra podría dejar de ser "pequeña" según qué
  viales caigan en los primeros N del fichero.
- **Filtrado por vial "tratado" únicamente** al seleccionar cruces (no por
  "tratado" o "que cruza"): el CSV de cruces incluye cada intersección dos
  veces (una por cada vial como protagonista); filtrar por ambas columnas
  habría duplicado cada arista en las dos direcciones.
- **`vial_id` se conserva como cadena de 8 dígitos con ceros a la
  izquierda**, no se convierte a entero: es el identificador oficial que usa
  la fuente para enlazar viales y cruces, y una futura carga completa
  necesitará ese mismo formato para cruzarse con el resto de recursos del
  dataset (numeraciones, tramos...) sin ambigüedad.
- **Sin `barrio`**: ninguno de los dos recursos usados publica el barrio a
  nivel de vial completo (solo distrito); el barrio sí aparece en otros
  recursos del mismo dataset a nivel de tramo/numeración concreta, fuera del
  alcance de esta tarea.
- **Es una carga puntual real, no una "muestra por falta de
  infraestructura"**: a diferencia de las tareas 003-008 (que serán
  productores continuos el día que exista infraestructura), esta fuente es
  de referencia y no necesitará nunca un modo `--interval-seconds` — se
  documenta así explícitamente en el docstring del módulo y en el README
  para que quede claro que no es una limitación temporal.
- **Descarga completa de ambos CSV en memoria, pero nunca a disco**: ninguno
  de los dos recursos ofrece un subconjunto descargable más pequeño (no hay
  paginación ni un endpoint "primeros N"), así que hace falta traer el CSV
  completo (~3.7 MB y ~12.4 MB) para poder elegir la muestra — mismo patrón
  ya usado en `ruido_madrid.py` (tarea 007) con un CSV de ~24 MB. En ningún
  momento se escribe el dataset completo en el disco de la EC2, solo la
  muestra final pequeña.

## Relevante para tareas futuras

- Ambos recursos son completamente públicos y no dependen de ningún
  registro pendiente: la carga completa real no tiene ningún bloqueo de
  credenciales que resolver antes.
- Cuando se aplique la infraestructura de la tarea 001 y se implemente la
  carga completa real hacia Neo4j, esta es la primera fuente del proyecto
  pensada explícitamente como una carga puntual de referencia (no un
  productor recurrente ni siquiera en producción) — un buen precedente si
  las tareas 010 (límites administrativos) y 011 (POIs) resultan tener la
  misma naturaleza de referencia.
- El dataset `200075-0-callejero` también publica "Cruces de viales" con
  código postal por tramo y "Direcciones postales vigentes con
  coordenadas" (numeraciones), no usados por esta tarea (fuera de su
  alcance: solo pedía el grafo viario) pero disponibles si una tarea futura
  de geocodificación/direcciones los necesitara.
- El portal HTML clásico de datos.madrid.es (`/egob/...`) devolvía una
  página de mantenimiento genérica durante esta sesión; el catálogo real
  vive ahora en un backend CKAN (`/api/3/action/...`). Si una tarea futura
  necesita explorar el catálogo de datasets de datos.madrid.es mediante
  scripts (no solo abrir enlaces conocidos), conviene usar directamente la
  API CKAN (`package_search`, `package_show`) en vez de la interfaz HTML.
- Los nombres de fichero de los recursos CSV de este dataset incluyen el mes
  de publicación (p.ej. `..._202607.csv`) y cambian cada vez que el
  Ayuntamiento sube una nueva versión; como esta es una carga puntual
  invocada a mano (no un cron), no se automatizó la resolución de la URL
  vigente vía la API CKAN — si en una ejecución futura la URL por defecto
  devolviera 404, basta con volver a mirar el dataset en el portal (o
  `package_show`) y pasar la URL nueva con
  `MADRID_STREETS_VIAS_URL`/`MADRID_STREETS_CROSSINGS_URL`.
