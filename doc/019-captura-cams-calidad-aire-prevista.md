# 019 — Captura de calidad del aire prevista y validada (Copernicus CAMS, muestra)

## Qué se implementó

`ingesta/capturas/cams_calidad_aire_madrid.py`: productor de la previsión de
calidad del aire de [Copernicus CAMS](https://ads.atmosphere.copernicus.eu/datasets/cams-europe-air-quality-forecasts)
(dataset `cams-europe-air-quality-forecasts` del Atmosphere Data Store, ADS)
para Madrid. Complementa a `calidad_aire_madrid.py` (tarea 006, mediciones
**en tiempo real** de la red municipal) con una **previsión** horaria a 4
días vista, validada contra observaciones oficiales a escala europea —
exactamente el enriquecimiento que la memoria del TFM (apartado 6.1) dejaba
anotado como pendiente ("fuentes europeas de cobertura continental").

Una única función pública de captura, `fetch_forecast(config, run_date=None)`:
construye la petición a la ADS API (`cdsapi.Client.retrieve`), descarga el
`.zip` con el/los NetCDF resultantes, y los normaliza al esquema mínimo
pedido (contaminante, valor previsto, fecha/hora de validez, fecha de
emisión de la previsión, `source="cams"`). Documentación completa (esquema,
variables de entorno, cadencia real) en `ingesta/README.md`, sección
`capturas/cams_calidad_aire_madrid.py`.

## Bloqueo de registro: cuenta real ligada a identidad, no un CAPTCHA técnico

Se investigó en vivo el formulario de alta de la ADS API
(`accounts.ecmwf.int/.../registrations?client_id=cds...`): a diferencia de
AEMET (tarea 018) o la EMT (tarea 003), **no tiene reCAPTCHA ni ningún otro
CAPTCHA** — solo pide nombre, apellidos, email, contraseña y su
confirmación. Aun así se decidió tratarlo como el mismo tipo de bloqueo que
esas tareas: completar el alta implica crear una **cuenta real, persistente
y ligada a la identidad de quien la crea**, con una contraseña elegida en
el momento y, muy probablemente, una confirmación por email (patrón
estándar de Keycloak/EU Login, el sistema que usa `accounts.ecmwf.int`) —
un paso para el que esta sesión no tiene acceso a ningún buzón de correo.
Elegir una contraseña y registrar una cuenta a nombre de un tercero sin que
haya un humano confirmando esa acción en el momento no es algo que este
pipeline autónomo deba decidir por iniciativa propia, aunque técnicamente
nada (CAPTCHA) lo hubiera impedido de forma automática. El código queda
completo y listo para ejecutarse el día que alguien complete el alta
manualmente y configure `CAMS_ADS_API_KEY` (nunca hardcodeada); la
documentación oficial confirma además que hay que aceptar los "Terms of
Use" del dataset desde su página en el ADS, ya logueado — otro paso manual
no automatizable.

## El esquema sí se obtuvo, sin necesidad de un token válido

El ADS expone públicamente, sin autenticación,
`GET /api/retrieve/v1/processes/cams-europe-air-quality-forecasts`
(verificado en vivo). De ahí salen, con certeza, todos los parámetros
válidos de la petición (contaminante, modelo, nivel, tipo, `leadtime_hour`,
`data_format="netcdf_zip"`, recorte geográfico `area`) y la confirmación de
qué contaminantes están regularmente validados: **NO, NO2, SO2, O3, PM2.5,
PM10 y polvo** — exactamente el conjunto que restringía el enunciado de
esta tarea; el resto (polen, COVs, amoniaco...) se declara explícitamente
"experimental, sin validar" y queda fuera de `POLLUTANT_VARIABLES`.

Los nombres cortos de variable **dentro** de cada NetCDF (`no2_conc`,
`o3_conc`, `pm10_conc`, `pm2p5_conc`, `so2_conc`) se contrastaron con
varias fuentes públicas independientes. Para `nitrogen_monoxide`/`dust` no
se encontró ninguna fuente que citara su nombre corto exacto: se mapean
como `no_conc`/`dust_conc` por el mismo patrón que las cinco anteriores,
pero sin poder contrastarlo contra un fichero real — mismo tipo de aviso de
menor confianza ya usado en la tarea 018 para el esquema CAP de avisos de
AEMET. El código es tolerante a esto: `normalize_forecast_file` solo
procesa las variables de `POLLUTANT_VARIABLES` que encuentra en cada
fichero, así que un nombre equivocado no rompe la captura, solo deja sin
registros a ese contaminante en vez de fallar.

## Decisiones de diseño

- **Modelo `ensemble`, no un modelo individual**: CAMS combina once
  sistemas de previsión europeos en una mediana de conjunto, documentada
  como de mejor rendimiento que cualquier modelo individual; es el valor
  por defecto de `CAMS_MODEL`, configurable a cualquiera de los once
  modelos individuales si hiciera falta.
- **Recorte geográfico (`area`) alrededor de Madrid, no toda Europa**: el
  dataset cubre 25°O-45°E/30°N-72°N a 0.1°; `DEFAULT_AREA` es una caja
  estrecha alrededor de Madrid capital, y la normalización se queda con el
  único punto de rejilla más cercano a su centro (40.4168, -3.7038) —
  cumple el criterio de "muestra pequeña" pidiendo el subconjunto correcto
  en origen, no descargando toda Europa y recortando después.
- **4 contaminantes por defecto (NO2/O3/PM2.5/PM10)**, los regulados por la
  UE/OMS, pedidos explícitamente en el objetivo de la tarea; NO/SO2/polvo
  también están soportados (`POLLUTANT_VARIABLES` completo, configurable
  vía `CAMS_POLLUTANTS`) pero no forman parte de la muestra por defecto.
- **Descarga a un fichero temporal que se borra inmediatamente**: el
  cliente oficial `cdsapi` solo sabe escribir a disco, no a memoria
  directamente; `_fetch_forecast_zip_bytes` usa `tempfile.NamedTemporaryFile`
  y borra el `.zip` en un `finally` en cuanto se han leído sus bytes — no
  queda ningún dato crudo sin acotar en disco, ni siquiera temporalmente
  más allá de esa única llamada.
- **Import perezoso de `cdsapi`** dentro de `_fetch_forecast_zip_bytes` (no
  a nivel de módulo): permite sustituirlo por un doble de test vía
  `sys.modules["cdsapi"]` sin necesidad de que el paquete real esté
  instalado en entornos que solo normalicen/testeen.

## Test de flujo completo, no solo de normalización aislada

`ingesta/tests/test_cams_calidad_aire_madrid.py` no depende de la red.
Usa un fixture NetCDF sintético pero con la estructura real documentada del
dataset (`ingesta/tests/fixtures/cams_forecast_sample.nc`: dimensiones
`time`/`latitude`/`longitude`, variable escalar `forecast_reference_time`,
variables `no2_conc`/`o3_conc`/`pm2p5_conc`/`pm10_conc` con atributo
`units`), generado con la librería `netCDF4` durante esta sesión — no se
pudo generar con datos reales descargados porque el registro está
bloqueado.

A diferencia de otras tareas bloqueadas del proyecto (que solo prueban las
funciones de normalización de forma aislada), aquí `FetchForecastTests`
ejercita **el flujo completo** (`fetch_forecast`: construcción de la
petición, llamada a `cdsapi.Client.retrieve`, descompresión del `.zip`,
parseo del NetCDF y normalización) sustituyendo `cdsapi.Client` por un
doble en memoria que escribe el `.zip` sintético en el `target` pedido —
posible precisamente por el import perezoso de `cdsapi` explicado arriba.
También se verifica explícitamente que el `.zip` temporal no queda en
disco tras la llamada. Suite completa del proyecto verificada tras el
cambio: **154 tests** (139 previos + 15 nuevos), todos en verde.

## Dependencias añadidas

`ingesta/requirements.txt`: `cdsapi>=0.7,<1` (cliente oficial de la ADS
API) y `netCDF4>=1.6,<2` (lectura del NetCDF descargado; instala wheels
precompilados con HDF5/netCDF-C incluidos, sin necesidad de compilar nada
ni de dependencias de sistema adicionales — verificado instalándolo en
esta misma sesión, ~13 MB adicionales de disco).

## Relevante para tareas futuras

- Este es el segundo caso del proyecto (tras la tarea 018) de un bloqueo de
  registro sin CAPTCHA técnico, resuelto igualmente como bloqueo: la razón
  de fondo no es "¿hay un CAPTCHA?" sino "¿implica crear una identidad
  persistente/contraseña de un tercero sin supervisión humana en el
  momento?". Si una tarea futura encuentra otro registro sin CAPTCHA pero
  con el mismo patrón (cuenta+contraseña+posible verificación de email),
  debería aplicar el mismo criterio en vez de asumir que la ausencia de
  CAPTCHA implica que se puede completar automáticamente.
- Si una tarea futura completa el alta y configura `CAMS_ADS_API_KEY`, el
  código debería funcionar tal cual (esquema de petición verificado contra
  la especificación pública real del proceso ADS), pero conviene
  **volver a contrastar el mapeo `no_conc`/`dust_conc` contra un NetCDF
  real en cuanto haya una key**, ya que es la parte de menor confianza de
  este módulo (nunca se pudo verificar en vivo, ver arriba).
- La cadencia real de CAMS (una corrida diaria a las 00:00 UTC, publicada
  en dos tandas: horas 0-48 a partir de las 06:45 UTC, horas 49-96 a partir
  de las 08:30 UTC) queda documentada en `ingesta/README.md`; un scheduling
  real debería sondear una vez tras cada tanda, no en un intervalo
  arbitrario, y el punto de conexión a un futuro productor Kafka sigue
  marcado con `TODO(kafka)` en el módulo por consistencia con el resto del
  proyecto.
- El patrón "import perezoso de la librería cliente + doble sustituyendo
  `sys.modules[...]`" usado aquí para probar el flujo completo sin red es
  reutilizable para cualquier fuente futura bloqueada por registro que use
  un cliente Python oficial (en vez de `requests` directo): permite un test
  de integración real del pipeline de captura sin depender de que la
  librería esté instalada en todos los entornos, y sin necesitar
  credenciales reales.
