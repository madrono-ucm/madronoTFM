# 005 — Captura de ocupación de aparcamientos públicos de Madrid (muestra)

## Qué se implementó

Cuarto productor de datos de la Fase 1 (Ingesta), con el mismo alcance
reducido que las tareas 003/004 (captura puntual de muestra, no productor
continuo — la infraestructura AWS de la tarea 001 sigue sin aplicarse):

- `ingesta/capturas/aparcamientos_madrid.py`: descarga la ocupación en
  tiempo real (plazas libres) de los aparcamientos públicos rotacionales de
  Madrid y, para cada uno de la muestra, sus plazas totales, los normaliza a
  un esquema mínimo, y guarda una **muestra pequeña** (5 aparcamientos por
  defecto, configurable) en un fichero fijo — sin bucle, sin
  `--interval-seconds`, sin escribir en la capa Bronze particionada.
- `ingesta/capturas/samples/aparcamientos_madrid_sample.json`: la muestra
  pequeña commiteada como fixture (5 aparcamientos).
- `ingesta/tests/test_aparcamientos_madrid.py` +
  `ingesta/tests/fixtures/parking_list_sample.xml` +
  `ingesta/tests/fixtures/parking_detail_sample.xml`: tests con `unittest`
  (sin red) que verifican el parseo/normalización, incluido el caso de un
  aparcamiento que no comparte ocupación en tiempo real, y que la muestra
  commiteada cumple el esquema esperado.
- `ingesta/README.md`: nueva sección para esta fuente (fuente elegida,
  variables de entorno, esquema, y la nota sobre el acceso en vivo desde
  este entorno).

## Fuente elegida y por qué: servicio SOAP `infoParking`, sin autenticación

Se investigaron tres datasets candidatos de aparcamientos en datos.madrid.es
y datos.emtmadrid.es:

- **"Aparcamientos públicos (rotacionales). Datos de ocupación en tiempo
  real"** (id `50027-0-aparcamientosocupacionyservicios`): agrega la
  ocupación en tiempo real de los aparcamientos rotacionales (municipales y
  privados) que comparten voluntariamente su dato — el mismo sistema que
  alimenta la app oficial "Parking Madrid". **Elegido**: es el único de los
  tres con ocupación en tiempo real granular por aparcamiento.
- "Aparcamientos EMT" (datos.emtmadrid.es): descartado — subconjunto más
  pequeño (aparcamientos disuasorios) sin un feed de ocupación en tiempo real
  tan directo.
- "Aparcamientos públicos municipales (rotacionales). Histórico de
  ocupación" (dataset 300346): descartado — es un agregado mensual/histórico,
  no ocupación en tiempo real, no encaja con el objetivo de la tarea.

A diferencia de los feeds HTTP simples usados en tareas anteriores (XML de
Informo en tráfico — tarea 002, JSON GBFS en BiciMAD — tarea 004), el dataset
elegido **no publica un XML/JSON descargable directamente**: su único recurso
de datos es un servicio **SOAP** (WSDL "infoParking"), descargable desde el
portal, que apunta al endpoint real
`https://servayto.madrid.es/MTPAR_WSINFO/InfoParking`. Se verificó en vivo
desde este entorno que este endpoint SOAP **no requiere ninguna
autenticación ni API key**, así que no hizo falta aplicar la salvedad de la
tarea sobre credenciales.

Se completó una **captura real en vivo**: el fixture commiteado
(`ingesta/capturas/samples/aparcamientos_madrid_sample.json`) son 5
aparcamientos reales (Nuestra Señora del Recuerdo, Avenida de Portugal,
Paseo de Recoletos, Almagro, Jacinto Benavente), descargados ejecutando
`python3 -m ingesta.capturas.aparcamientos_madrid` tal cual contra el
servicio SOAP público durante esta sesión — no son datos de ejemplo
generados a mano. De los 75 aparcamientos del listado completo (operación
`GetListParking`), 24 compartían ocupación en tiempo real en el momento de
la captura (compartirla es voluntario por parte de cada aparcamiento).

## Esquema normalizado

Por aparcamiento: `schema_version`, `source`
(`"madrid_aparcamientos_rotacionales"`), `parking_id`, `name`, `address`,
`measured_at` (UTC, de `lstOccupation.moment`; `null` si no comparte
ocupación en tiempo real), `ingested_at` (UTC, instante de la descarga),
`free_spaces` (de `GetListParking`; `null` si no comparte ocupación),
`total_spaces` (de `GetDetailParking`, característica "Total"; `null` si no
se pudo obtener), y `location` (`lat`/`lon` WGS84 estándar, no UTM).
Detalle completo en `ingesta/README.md`.

## Decisiones de diseño (por qué)

- **Dos llamadas SOAP encadenadas** (`GetListParking` + `GetDetailParking`
  por aparcamiento de la muestra), en vez de una sola: `GetListParking`
  (que lista los 75 aparcamientos) no incluye las plazas totales, solo las
  libres; las plazas totales solo están en `GetDetailParking`, que se llama
  una vez por aparcamiento. Como esta tarea solo necesita una muestra
  pequeña (5 por defecto), el coste de N llamadas de detalle es aceptable;
  un productor continuo real tendría que decidir si cachea `GetDetailParking`
  (las plazas totales cambian poco) en vez de repetirlo en cada ciclo.
- **Solo se muestrean aparcamientos con ocupación en tiempo real
  compartida**: de los 75 aparcamientos del listado, se filtran los que
  tienen `free_spaces` no nulo antes de tomar la muestra — son el
  subconjunto relevante para el objetivo de la tarea (ocupación), ya que
  compartir la ocupación es voluntario y muchos aparcamientos del listado no
  la incluyen.
- **Aparcamientos sin ocupación no se descartan del parseo**: `parse_list_parking`
  normaliza igualmente los aparcamientos sin `lstOccupation` (con
  `free_spaces`/`measured_at` a `null`), igual que el criterio ya usado en
  tráfico (tarea 002) y BiciMAD (tarea 004) — Bronze/la muestra deben
  reflejar la fuente tal cual. El filtrado a "solo con ocupación" ocurre
  después, solo para decidir qué aparcamientos entran en la muestra pequeña.
- **Sin `BronzeWriter` ni modo `--interval-seconds`**, igual que en las
  tareas 003/004 y por la misma razón: la tarea prohibía dejar algo
  programado o escribir sin acotar en el disco de la EC2.
- **Sin variables de entorno de credenciales**: el servicio SOAP es público y
  no las necesita, igual que el feed GBFS de BiciMAD (tarea 004).

## Relevante para tareas futuras

- El servicio SOAP `infoParking` es completamente público y no depende de
  ningún registro pendiente (a diferencia de la EMT MobilityLabs de la tarea
  003): el día que se implemente un productor continuo real para esta
  fuente, no hay ningún bloqueo de credenciales que resolver antes.
- Si se implementa un productor continuo, conviene revisar si cachear
  `GetDetailParking` por aparcamiento (las plazas totales cambian rara vez)
  en vez de repetir esa llamada en cada ciclo de captura, para no
  sobrecargar el servicio SOAP con N llamadas por ciclo.
- Igual que en las tareas 003/004, este productor sigue sin estar conectado
  a ningún destino de almacenamiento definitivo (S3/Bronze); cuando se
  aplique la infraestructura de la tarea 001, habrá que decidir si reutiliza
  `BronzeWriter` (como tráfico) o un escritor de muestra/lote distinto, y
  añadir un modo de captura periódica si se decide operarlo así.
- `TODO(kafka)` queda marcado en el módulo para cuando exista un broker
  Kafka desplegado, igual que en los productores anteriores.
- De los 75 aparcamientos del listado completo, solo 24 compartían ocupación
  en tiempo real en el momento de esta captura; ese número puede variar con
  el tiempo según qué aparcamientos decidan compartir su dato.
