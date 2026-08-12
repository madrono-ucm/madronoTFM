# 006 — Captura de datos de calidad del aire de Madrid (muestra)

## Qué se implementó

Quinto productor de datos de la Fase 1 (Ingesta), con el mismo alcance
reducido que las tareas 003/004/005 (captura puntual de muestra, no
productor continuo — la infraestructura AWS de la tarea 001 sigue sin
aplicarse):

- `ingesta/capturas/calidad_aire_madrid.py`: descarga las lecturas horarias
  en tiempo real de la red de 24 estaciones de control de contaminación del
  Ayuntamiento de Madrid y, para poder resolver nombre/dirección/coordenadas
  de cada estación, el catálogo de estaciones, las normaliza a un esquema
  mínimo, y guarda una **muestra pequeña** (5 lecturas por defecto,
  configurable) en un fichero fijo — sin bucle, sin `--interval-seconds`,
  sin escribir en la capa Bronze particionada.
- `ingesta/capturas/samples/calidad_aire_madrid_sample.json`: la muestra
  pequeña commiteada como fixture (5 lecturas).
- `ingesta/tests/test_calidad_aire_madrid.py` +
  `ingesta/tests/fixtures/calidad_aire_realtime_sample.json` +
  `ingesta/tests/fixtures/calidad_aire_estaciones_sample.csv`: tests con
  `unittest` (sin red) que verifican el parseo/normalización, incluidos los
  casos de un código de magnitud sin ceros a la izquierda, una lectura sin
  ninguna hora válida ese día (se descarta), y una estación sin metadatos
  conocidos en el catálogo, y que la muestra commiteada cumple el esquema
  esperado.
- `ingesta/README.md`: nueva sección para esta fuente (formato real
  encontrado, variables de entorno, esquema, y la nota sobre el acceso en
  vivo desde este entorno).

## Fuente elegida y formato real encontrado

Dataset "Calidad del aire. Datos en tiempo real" (id
`212531-0-calidad-aire-tiempo-real`) de
[datos.madrid.es](https://datos.madrid.es/egob/catalogo/212531-0-calidad-aire-tiempo-real):
lecturas horarias, actualizadas cada 20 minutos, de las 24 estaciones fijas
de la red de vigilancia de calidad del aire. El dataset ofrece TXT, CSV,
JSON y XML con el mismo contenido; se eligió **JSON** por ser el más simple
de parsear sin dependencias extra (a diferencia del XML de tráfico de la
tarea 002, que sí requería `xml.etree`).

El formato real, confirmado descargando el recurso en vivo y contrastándolo
con el PDF oficial "Intérprete de ficheros de calidad del aire" (que el
propio dataset enlaza como documentación), **no es una lista plana de
lecturas**: es un registro por combinación estación+magnitud+día, con las 24
lecturas horarias de ese día ya embebidas en columnas `H01`..`H24` (cada una
con su código de validación `V01`..`V24`: `"V"` = válido, `"N"` = no
válido/sin dato). El campo `PUNTO_MUESTREO` (p.ej. `"28079011_12_8"`)
codifica estación (`28079011`) + magnitud (`12`) + técnica de muestreo
(`8`). El campo `MAGNITUD` da el código de magnitud **sin ceros a la
izquierda** (`"1"` en vez de `"01"` para SO2), a diferencia de como aparece
en el propio `PUNTO_MUESTREO` o en la tabla de códigos del PDF — el
productor lo normaliza con `zfill(2)` antes de mapearlo contra la tabla de
magnitudes (Anexo II del PDF: SO2, CO, NO, NO2, PM2.5, PM10, NOx, O3,
tolueno, benceno...).

El JSON de tiempo real no incluye nombre, dirección ni coordenadas de la
estación (solo su código numérico), así que este productor combina una
segunda fuente: el dataset "Calidad del aire. Estaciones de control" (id
`212629-0-estaciones-control-aire`), un CSV con esos metadatos por estación
(coordenadas ya en WGS84 decimal en las columnas `LONGITUD`/`LATITUD`, sin
necesidad de reproyectar desde las columnas UTM/DMS que también incluye el
CSV). Es el mismo patrón de combinar dos fuentes ya usado en
`aparcamientos_madrid.py` (tarea 005, `GetListParking` + `GetDetailParking`)
y `bicimad.py` (tarea 004, `station_information` + `station_status`).

Se verificó en vivo desde este entorno que ambos recursos son accesibles
**sin ninguna autenticación ni API key** — no hizo falta aplicar la
salvedad de la tarea sobre credenciales, ni sobre fuente no accesible.

## Captura real en vivo

Se completó una **captura real en vivo**: el fixture commiteado
(`ingesta/capturas/samples/calidad_aire_madrid_sample.json`) son 5 lecturas
reales de las estaciones "Ramón y Cajal" y "Arturo Soria" (magnitudes NOx,
NO, NO2 y O3), descargadas ejecutando
`python3 -m ingesta.capturas.calidad_aire_madrid` tal cual contra ambos
recursos públicos durante esta sesión — no son datos de ejemplo generados a
mano. De las 123 lecturas estación+magnitud que devolvió la fuente en el
momento de la captura, las 123 tenían al menos una hora válida ese día; la
muestra son las primeras 5 en el orden en que las devuelve la fuente (mismo
criterio que `aparcamientos_madrid.py`), por lo que solo cubre 2 de las 24
estaciones — es una limitación conocida de tomar "las primeras N", no un
problema de la fuente.

## Decisiones de diseño (por qué)

- **Se toma la lectura horaria válida más reciente del día por registro**,
  no las 24 horas completas: cada registro estación+magnitud+día trae un
  día entero de lecturas, pero el objetivo de la tarea (y el patrón de
  "muestra pequeña" de las tareas 003-005) es un estado puntual "actual", no
  una serie temporal completa. `_latest_valid_hour` recorre `H24`→`H01` y
  se queda con la primera marcada `V`. Una tarea futura de captura
  histórica/continua sí querría conservar las 24 horas.
- **Lecturas sin ninguna hora válida se descartan** (`normalize_record`
  devuelve `None`), a diferencia del criterio de tráfico/BiciMAD/aparcamientos
  de "conservar el registro con campos a `null`": aquí el registro entero
  no aporta ningún valor de calidad del aire ese día (single, no un campo
  parcial), así que no hay nada útil que normalizar; se prefirió no incluir
  registros completamente vacíos en una muestra ya de por sí pequeña.
- **Segunda descarga al catálogo de estaciones** en vez de solo el feed de
  tiempo real: sin ella, la muestra no tendría nombre, dirección ni
  coordenadas de estación, solo un código numérico — mismo razonamiento que
  llevó a combinar dos fuentes en las tareas 004/005.
- **Sin `BronzeWriter` ni modo `--interval-seconds`**, igual que en las
  tareas 003/004/005 y por la misma razón: la tarea prohibía dejar algo
  programado o escribir sin acotar en el disco de la EC2.
- **Sin variables de entorno de credenciales**: ambos recursos de
  datos.madrid.es usados son públicos y no las necesitan, igual que BiciMAD
  (tarea 004) y aparcamientos (tarea 005).

## Relevante para tareas futuras

- Ambos recursos (tiempo real y catálogo de estaciones) son completamente
  públicos y no dependen de ningún registro pendiente: el día que se
  implemente un productor continuo real para esta fuente, no hay ningún
  bloqueo de credenciales que resolver antes.
- Si se implementa un productor continuo, conviene decidir si se conservan
  las 24 horas de cada registro estación+magnitud+día (útil para relleno
  histórico) en vez de solo la última hora válida, y si se cachea el
  catálogo de estaciones (cambia con muy poca frecuencia) en vez de
  descargarlo en cada ciclo.
- Igual que en las tareas 003/004/005, este productor sigue sin estar
  conectado a ningún destino de almacenamiento definitivo (S3/Bronze); eso
  llegará en una tarea posterior, tras aplicar la infraestructura de la
  tarea 001.
- `TODO(kafka)` queda marcado en el módulo para cuando exista un broker
  Kafka desplegado, igual que en los productores anteriores.
- La tabla `MAGNITUDES` del módulo cubre las magnitudes documentadas en el
  Anexo II del PDF oficial (incluye compuestos orgánicos volátiles como
  tolueno/benceno/xilenos, no solo los contaminantes "clásicos"
  NO2/PM10/PM2.5/O3/SO2/CO); una lectura con un código de magnitud no
  presente en la tabla se normaliza igualmente pero con
  `magnitude_abbr`/`magnitude_name`/`unit` a `null` en vez de fallar.
