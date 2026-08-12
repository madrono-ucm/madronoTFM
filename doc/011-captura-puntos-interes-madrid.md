# 011 — Captura de puntos de interés de Madrid (muestra, carga puntual)

## Qué se implementó

Décimo productor de datos de la Fase 1 (Ingesta), del mismo tipo que
`callejero_madrid.py` (tarea 009) y `barrios_distritos_madrid.py` (tarea
010): no es un dato que cambie con el tiempo, sino un dato de **referencia**
(la ficha de un monumento o museo no varía minuto a minuto) — una **carga
batch puntual**, no un stream, que nunca necesitará programarse
periódicamente ni siquiera cuando exista infraestructura real.

- `ingesta/capturas/poi_madrid.py`: descarga el catálogo de puntos de
  interés turístico del Ayuntamiento de Madrid, filtra por la categoría
  "Edificios y monumentos" y normaliza a un esquema mínimo pensado para que
  el futuro asistente conversacional resuelva preguntas como «¿merece la
  pena ir a X lugar?». Sin bucle, sin `--interval-seconds`, sin escribir el
  catálogo completo a disco.
- `ingesta/capturas/samples/poi_madrid_sample.json`: la muestra pequeña
  commiteada como fixture (5 puntos de interés reales).
- `ingesta/tests/test_poi_madrid.py` +
  `ingesta/tests/fixtures/poi_turismo_sample.xml`: tests con `unittest`
  (sin red) que verifican el filtrado por categoría, el descarte de puntos
  sin coordenadas, un punto con varias categorías (solo la buscada debe
  quedar en el registro), un punto con subcategoría, la normalización de
  nombres con entidades HTML doblemente escapadas, y que la muestra
  commiteada cumple el esquema esperado.
- `ingesta/README.md`: nueva sección para esta fuente (fuente y categoría
  elegidas y por qué, formato real encontrado, licencia, variables de
  entorno, esquema, y la nota sobre el acceso en vivo desde este entorno).

## Fuente y categoría elegidas y por qué

Dataset "Puntos de interés turístico de la ciudad de Madrid. Qué visitar en
Madrid (www.esmadrid.com)" (id `300030-0-puntos-interes-turistico`) de
[datos.madrid.es](https://datos.madrid.es/dataset/300030-0-puntos-interes-turistico),
publicado por Madrid Destino, Cultura, Turismo y Negocio, S.A.: un único XML
con 935 fichas (museos, monumentos, salas de exposiciones, parques,
instalaciones culturales/deportivas...), cada una con descripción,
geoposición, dirección, horario y coste de acceso. Se descartaron dos
alternativas: "Edificios de carácter monumental" (id
`208844-0-monumentos-edificios`, sin descripción turística ni
horarios/precios) y "Planeamiento Urbanístico. Catálogo de Elementos
Singulares" (id `300486-0-planeamiento-elemento-singulares`, un dataset de
protección patrimonial, no de contenido orientado al visitante).

El objetivo de la tarea pedía elegir una o dos categorías representativas.
Se eligió **una sola: "Edificios y monumentos"** (`idCategoria` `7173`, 355
de las 935 fichas totales), por ser la que más directamente encaja con
"monumentos y lugares de interés turístico" (el ejemplo del propio objetivo)
y con la pregunta guía «¿merece la pena ir a X lugar?» — a diferencia de
categorías como "Empresas de guías turísticos" o "Servicios" (agencias e
infraestructura de soporte, no lugares que visitar). Todas las categorías
del dataset comparten el mismo esquema XML, así que una tarea futura de
carga completa puede iterar sobre el resto de categorías reutilizando este
módulo sin cambios de esquema — no hizo falta una segunda categoría para
cubrir un caso de esquema distinto.

Se ha verificado en vivo desde este entorno que el recurso es accesible
**sin ninguna autenticación ni API key**.

## Captura real en vivo

Se completó una **captura real en vivo**: el fixture commiteado
(`ingesta/capturas/samples/poi_madrid_sample.json`) son 5 puntos de interés
reales (Comunidad Evangélica de Habla Alemana – Friedenskirche, Huerta de la
Salud, Quinta del Duque del Arco, Fuente del río Lozoya, Refugio antiaéreo
del Retiro), descargados ejecutando `python3 -m ingesta.capturas.poi_madrid`
tal cual contra el recurso público durante esta sesión — no son datos de
ejemplo generados a mano. El catálogo completo (935 fichas, ~3.6 MB) se
descargó en memoria porque la fuente no ofrece filtrado remoto por
categoría, pero en ningún momento se escribió a disco; solo la muestra
final de 5 puntos.

## Decisiones de diseño (por qué)

- **Filtro anti-bot descubierto en vivo (`403 Forbidden` sin `User-Agent`)**:
  el servidor `esmadrid.com` devuelve `403` a peticiones sin cabecera
  `User-Agent` o con la que usan por defecto `requests`/`curl -A` (probado
  en vivo), pero responde con normalidad a un `User-Agent` de navegador
  convencional. No es una restricción de acceso real ni requiere ninguna
  credencial — es un filtro básico anti-bot por cabecera — así que este
  módulo simplemente declara un `User-Agent` fijo (`_REQUEST_HEADERS`) en
  sus peticiones, sin necesidad de más lógica.
- **Sin URLs de fotografías en el esquema normalizado**: el dataset declara
  explícitamente unas condiciones de uso distintas al resto del portal
  ("Los textos son de libre uso pero no así las fotografías"). Se optó por
  no incluir el bloque `<multimedia>` en absoluto en el esquema normalizado,
  en vez de incluir las URLs y confiar en que un consumidor futuro respete
  la licencia por su cuenta.
- **`district`/`neighbourhood` a `null`, no derivados**: la fuente no
  publica distrito ni barrio (solo dirección postal y código postal); el
  campo `locality` a veces trae un nombre de distrito (p.ej. "Fuencarral -
  El Pardo" para la Quinta del Duque del Arco) pero de forma inconsistente
  (la mayoría de fichas lo dejan vacío), así que no es una fuente fiable
  para derivarlo mecánicamente. Una derivación correcta requeriría un cruce
  punto-en-polígono contra los límites de `barrios_distritos_madrid.py`
  (tarea 010) — fuera del alcance de esta captura de muestra; se deja el
  campo a `null` en vez de rellenarlo con un dato poco fiable, tal como
  permite el objetivo de la tarea cuando el dato "no viene incluido en la
  fuente ni se puede derivar" de forma simple.
- **`_strip_html`/`_unescape` para texto plano, sin dependencias extra**: los
  campos `body` (descripción), "Horario" y "Servicios de pago" traen HTML
  embebido, y `name`/`title` traen entidades HTML doblemente escapadas
  (p.ej. el texto ya parseado por XML contiene literalmente `&eacute;` en
  vez de `é`, porque la fuente escribió `&amp;eacute;` en el XML crudo). Se
  resolvió con una función de regex + `html.unescape` de la librería
  estándar, sin añadir una dependencia de parseo HTML (`BeautifulSoup` u
  similar) que este proyecto no usa en ningún otro productor.
- **El literal `"--"` de la fuente se conserva tal cual, no se convierte a
  `null`**: cuando un punto no tiene coste de acceso ni horario que mostrar,
  la fuente usa literalmente el texto `"--"` en vez de dejar el campo vacío;
  tratarlo como una ausencia de dato habría perdido la distinción entre "la
  fuente no dice nada" (campo realmente vacío, se normaliza a `null`) y "la
  fuente dice explícitamente que no aplica" (`"--"`, se conserva).
- **`category`/`subcategories` extraídos solo de la categoría buscada**: una
  ficha puede tener varias categorías (39 de las 355 fichas de "Edificios y
  monumentos" también tienen otra categoría, p.ej. "Espacios para eventos");
  `_matched_category` solo recoge el nombre y las subcategorías del bloque
  de categoría que coincide con `MADRID_POI_CATEGORY_ID`, no de las demás
  categorías que pueda tener la ficha — mismo criterio que "un registro
  refleja la fuente para el filtro aplicado, no todo lo que trae la ficha".
- **Sin `BronzeWriter` ni modo `--interval-seconds`**, igual que
  `callejero_madrid.py` (tarea 009) y `barrios_distritos_madrid.py` (tarea
  010) y por la misma razón: es un dato de referencia que nunca necesitará
  recaptura periódica, ni siquiera en producción — no es una limitación
  temporal por falta de infraestructura.
- **Sin variables de entorno de credenciales**: el recurso de
  datos.madrid.es/esmadrid.com usado es público y no las necesita (solo
  requirió declarar un `User-Agent`, ver más arriba).

## Relevante para tareas futuras

- El recurso es completamente público y no depende de ningún registro
  pendiente: el día que se implemente la carga completa real (todas las
  categorías de POI relevantes), no hay ningún bloqueo de credenciales que
  resolver antes — solo hace falta reutilizar el `User-Agent` ya declarado
  en `_REQUEST_HEADERS`.
- Quedan 10 categorías del mismo dataset sin capturar en esta tarea
  ("Instalaciones culturales" —la mayor, 395 fichas—, "Parques y jardines",
  "Instalaciones deportivas", "Espacios para eventos"...). Todas comparten
  el mismo esquema XML que ya normaliza `poi_madrid.py`; una tarea futura de
  carga completa puede iterar `MADRID_POI_CATEGORY_ID` sobre cada una sin
  cambios de esquema (bastaría con quitar el filtro de categoría única, o
  con parametrizar una lista de IDs a incluir).
- `district`/`neighbourhood` quedan `null` en todos los registros de esta
  fuente: si una tarea futura de Silver/Gold necesita resolverlos, el camino
  más fiable encontrado en esta investigación es un cruce punto-en-polígono
  entre `location.lat`/`location.lon` de cada POI y los polígonos de
  `barrios_distritos_madrid.py` (tarea 010), no el campo `locality` de esta
  fuente (presente solo en algunas fichas y sin garantía de formato).
- Igual que en las tareas 009 y 010, este productor sigue sin estar
  conectado a ningún destino de almacenamiento definitivo (S3/Neo4j); eso
  llegará en una tarea posterior, tras aplicar la infraestructura de la
  tarea 001. Dado que estos POIs son nodos que el asistente conversacional
  consultará (ver objetivo de la tarea), encajan de forma natural como nodos
  del grafo urbano en Neo4j (ver memoria, apartado 5.2), relacionables por
  `location` con los barrios/distritos de la tarea 010 y por dirección con
  el callejero de la tarea 009.
- `TODO(kafka)` queda marcado en el módulo por consistencia con el resto de
  productores, aunque no se espera que esta fuente de referencia conecte
  nunca a un broker Kafka (mismo razonamiento que en las tareas 009 y 010).
- El filtro anti-bot por `User-Agent` de `esmadrid.com` (distinto del resto
  de fuentes de este proyecto, todas en el dominio `datos.madrid.es` o
  servicios municipales sin este filtro) es un precedente a tener en cuenta
  si una tarea futura captura otra fuente servida desde ese mismo dominio
  (`esmadrid.com`): probar primero si la petición por defecto de `requests`
  devuelve `403` antes de asumir que la fuente requiere autenticación real.
