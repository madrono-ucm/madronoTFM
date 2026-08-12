# 003 — Captura de datos de transporte público de Madrid (muestra)

## Qué se implementó

Segundo productor de datos de la Fase 1 (Ingesta), siguiendo el mismo patrón
que la tarea 002 pero con alcance deliberadamente reducido (no hay
infraestructura AWS aplicada todavía y esta tarea pide explícitamente una
captura puntual, no continua):

- `ingesta/capturas/transporte_publico_madrid.py`: descarga los próximos
  tiempos de llegada de autobús a una parada concreta de la EMT Madrid
  (Empresa Municipal de Transportes) usando su API REST "MobilityLabs"
  (`https://openapi.emtmadrid.es`), la normaliza a un esquema mínimo, y
  guarda **una única muestra pequeña** (5 registros por defecto,
  configurable) en un fichero fijo — sin bucle, sin `--interval-seconds`,
  sin escribir en la capa Bronze particionada.
- `ingesta/capturas/samples/transporte_publico_madrid_sample.json`: la
  muestra pequeña commiteada como fixture (3 registros).
- `ingesta/tests/test_transporte_publico_madrid.py` +
  `ingesta/tests/fixtures/emt_arrivals_sample.json`: tests con `unittest`
  (sin red) que verifican el parseo/normalización contra un fixture con la
  forma exacta de la respuesta real de la API, y que la muestra commiteada
  cumple el esquema esperado.
- `ingesta/README.md`: nueva sección para esta fuente (autenticación,
  variables de entorno, esquema, y la nota sobre el acceso desde este
  entorno — ver más abajo).

## Fuente elegida y por qué

Se eligió **EMT Madrid (API MobilityLabs)** sobre CRTM: es la fuente que
sugería la propia tarea como primera opción, tiene tiempos de llegada en
tiempo real por parada (lo que pide el objetivo: "próximas llegadas de una
línea/parada concretas"), y su API está bien documentada por la comunidad
(varias librerías cliente en GitHub permitieron confirmar el esquema exacto
de endpoints y respuestas). CRTM, por comparación, expone sobre todo GTFS
estático vía su portal ArcGIS Open Data; su información en tiempo real existe
pero está menos documentada públicamente para uso programático directo.

## Autenticación: API key gratuita, no una key simple

La API EMT no usa una API key de un solo valor, sino email + contraseña de
una cuenta registrada gratis en <https://mobilitylabs.emtmadrid.es>. El login
(`GET /v1/mobilitylabs/user/login/` con headers `email`/`password`) devuelve
un `accessToken` a reenviar en las siguientes llamadas. Las credenciales se
leen de `EMT_API_EMAIL`/`EMT_API_PASSWORD` (nunca hardcodeadas), siguiendo el
mismo patrón de configuración por entorno que ya usaba `trafico_madrid.py`.

## Decisión relevante: por qué la muestra commiteada es sintética, no en vivo

Se verificó en vivo que la API (`https://openapi.emtmadrid.es`) es accesible
desde este entorno y que el endpoint de login funciona correctamente:

- Sin credenciales: `{"code": "99", "description": "Error in
  mobilitylabs_context Init session", ...}`
- Con un email/contraseña de prueba (no registrados):
  `{"code": "91", "description": "Error: Email is not verified (lapsed: ...
  millsecs)", ...}`

Es decir, la fuente en sí **es accesible y funcional**, pero requiere una
cuenta con un email real que hay que verificar mediante un correo de
confirmación — un paso manual (registro + revisar bandeja de entrada) que no
es automatizable de forma autónoma en este pipeline sin supervisión humana en
tiempo real. Aplicando la salvedad que preveía la propia tarea para este
caso ("si la fuente pública no fuera accesible... documenta el problema... y
deja igualmente el código preparado con datos de ejemplo"), se optó por:

1. Dejar el código de captura (`fetch_access_token`, `fetch_raw_arrivals`,
   `capture_sample`) completo y funcional, listo para ejecutarse tal cual el
   día que alguien complete el registro real y exporte
   `EMT_API_EMAIL`/`EMT_API_PASSWORD`.
2. Generar a mano el fixture commiteado
   (`ingesta/capturas/samples/transporte_publico_madrid_sample.json`) con
   datos de ejemplo realistas que siguen exactamente el esquema que produce
   `normalize_record` — mismos campos, mismo formato, IDs de
   parada/línea/bus ilustrativos —, en vez de simular estar accediendo a
   datos reales.
3. Documentarlo explícitamente tanto en `ingesta/README.md` como aquí, para
   que quede claro que el bloqueo es el registro/verificación por email, no
   un problema del código o de la fuente.

## Otras decisiones de diseño (por qué)

- **Sin `BronzeWriter` ni modo `--interval-seconds`**: la tarea prohibía
  explícitamente dejar algo programado o escribir sin acotar en el disco de
  la EC2. El escritor de muestra escribe siempre en la misma ruta fija
  (sobrescribiendo), acotado a `EMT_SAMPLE_SIZE` (5 por defecto) registros,
  en vez de reutilizar el patrón de partición por fecha/hora de
  `BronzeWriter` (pensado para capturas repetidas que si se ejecutaran
  muchas veces a mano irían acumulando ficheros).
- **`location.lon`/`location.lat` en WGS84, a diferencia de tráfico**: la API
  EMT ya da las coordenadas de cada autobús como GeoJSON `Point` en WGS84
  (lon/lat estándar), a diferencia del feed de tráfico (UTM ETRS89). No hizo
  falta ninguna decisión de reproyección aquí.
- **Parada de ejemplo `71` por defecto** (`EMT_STOP_ID`/`--stop-id`): es solo
  un valor por defecto ilustrativo para poder invocar el script sin más
  argumentos una vez haya credenciales reales; no tiene ningún significado
  especial más allá de servir de ejemplo.

## Relevante para tareas futuras

- Para poder ejecutar este productor con datos reales, alguien debe: (a)
  registrarse en <https://mobilitylabs.emtmadrid.es>, (b) verificar el email
  de confirmación, y (c) exportar `EMT_API_EMAIL`/`EMT_API_PASSWORD` en el
  entorno de ejecución. Ninguna de estas tres acciones se ha realizado en
  esta sesión.
- El fixture de muestra commiteado es representativo del esquema real (mismo
  formato que produce `normalize_record`), pero sus valores concretos son de
  ejemplo, no una captura real — a diferencia del fixture de tráfico de la
  tarea 002, que sí es una copia reducida de una respuesta real.
- Igual que en la tarea 002, `TODO(kafka)` queda marcado en el módulo para
  cuando exista un broker Kafka desplegado.
- Este productor sigue sin estar conectado a ningún destino de
  almacenamiento definitivo (S3/Bronze); cuando se aplique la
  infraestructura de la tarea 001 y este productor pase a usarse de forma
  recurrente (no solo como muestra puntual), habrá que decidir si reutiliza
  `BronzeWriter` (como tráfico) o un escritor de muestra/lote distinto, y
  añadir de nuevo un modo de captura periódica si se decide operarlo así.
