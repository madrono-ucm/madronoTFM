# 024 — Desbloquear tarea 003: nueva autenticación EMT (v1.1, x-ClientId/passKey)

## Qué se implementó

La tarea 003 (`ingesta/capturas/transporte_publico_madrid.py`) quedó
bloqueada porque asumió que la API MobilityLabs de la EMT Madrid se
autentica con email + contraseña de una cuenta personal verificada por
correo (endpoint v1, cabeceras `email`/`password`) — un registro que no se
pudo completar de forma autónoma en aquella sesión. Esa asunción era
incorrecta: el mecanismo real es un login **v1.1** con **credenciales de
aplicación**, no de usuario:

```
GET https://openapi.emtmadrid.es/v1.1/mobilitylabs/user/login/
Headers: x-ClientId: <client id>, passKey: <pass key>, Content-Type: application/json
```

Con `EMT_CLIENT_ID`/`EMT_PASS_KEY` ya provisionados en el entorno de esta
EC2 (fuera del repositorio), se sustituyó `fetch_access_token` para usar
este flujo y se verificó en vivo, de extremo a extremo: login v1.1 seguido
de la consulta de llegadas (`v2/transport/busemtmad/stops/{stop_id}/arrives/`,
sin cambios respecto a la tarea 003, ya que solo cambiaba cómo se obtiene el
token, no cómo se usa después). Ambos pasos funcionaron.

## Hallazgo durante la verificación en vivo: dos códigos de éxito distintos

Al probar el login repetidamente se observó que la API no siempre devuelve
`code="00"` ("Register user...") en el éxito: si ya había una sesión
reciente en caché para esas credenciales, devuelve `code="01"`
("Token extend into control-cache...") — con un `accessToken` igualmente
válido en `data[0]`, solo cambia el mensaje. `fetch_access_token` acepta
ambos códigos como éxito; solo el resto (`"99"` sin credenciales, `"91"`
del flujo v1 anterior para email no verificado, etc.) se tratan como error.
Sin este hallazgo, una segunda ejecución de la captura (o cualquier
ejecución tras otra reciente) habría fallado con un `RuntimeError` espurio.

## Captura real completada

El fixture commiteado en
`ingesta/capturas/samples/transporte_publico_madrid_sample.json` son datos
**reales** descargados con `capture_sample` durante esta sesión — 5
llegadas de autobús con `estimateArrive`, coordenadas y destinos reales — y
no los datos de ejemplo escritos a mano que dejó la tarea 003. Se usó la
parada `70` en vez de la `71` por defecto: en el momento de la captura la
71 solo tenía 2 llegadas en curso (una única línea), mientras que la 70
tenía 18 llegadas en 8 líneas distintas — una muestra más representativa
del esquema completo. El valor por defecto (`DEFAULT_STOP_ID = "71"`,
también configurable con `--stop-id`/`EMT_STOP_ID`) no se cambió: la
captura de muestra puntual admite pasar cualquier parada por línea de
comandos, tal como ya hacía la tarea 003.

## Manejo de secretos

Ni `EMT_CLIENT_ID`/`EMT_PASS_KEY` ni el `accessToken` obtenido aparecen en
ningún fichero commiteado. El fixture de test de login
(`ingesta/tests/fixtures/emt_login_v11_sample.json`) usa un `accessToken` de
ejemplo explícitamente falso (`"FAKE-ACCESS-TOKEN-NOT-A-REAL-CREDENTIAL"`),
no una credencial real capturada. En el propio código:
`fetch_access_token` solo registra el código de estado de la respuesta
(`logger.info("Login EMT correcto (code=%s)", ...)`), nunca el token ni las
cabeceras enviadas; el mensaje de error de login tampoco incluye la
`description` de la API, ya que se observó en vivo que en el caso de éxito
la propia API la embebe dentro de ese campo (p.ej.
`"Register user: <usuario> with token: <uuid>  Data recovered OK"`) — un
detalle de la fuente que no se documenta con el valor real en ningún sitio
de este repositorio, solo se advierte aquí de que existe.

## Cambios de código

- `ingesta/capturas/transporte_publico_madrid.py`: `LOGIN_PATH` pasa de
  `/v1/mobilitylabs/user/login/` a `/v1.1/mobilitylabs/user/login/`;
  `CaptureConfig.api_email`/`api_password` se sustituyen por
  `client_id`/`pass_key`, leídos de `EMT_CLIENT_ID`/`EMT_PASS_KEY`;
  `fetch_access_token` envía las cabeceras `x-ClientId`/`passKey` en vez de
  `email`/`password` y acepta `code` `"00"` o `"01"` como éxito. Docstring
  del módulo reescrito para reflejar el mecanismo real y la captura
  completada.
- `ingesta/tests/test_transporte_publico_madrid.py`: nueva clase
  `FetchAccessTokenTests` (5 tests) que sustituye `requests.get` por un
  doble en memoria — verifica las cabeceras enviadas (`x-ClientId`/`passKey`,
  nunca `email`/`password`), el endpoint v1.1, la aceptación de `code="01"`
  como éxito, el error ante un código no reconocido, y el error si faltan
  las variables de entorno. Los tests de `parse_records`/`SampleFixtureTests`
  ya existentes no cambiaron (el esquema de llegadas normalizado no varió).
- `ingesta/tests/fixtures/emt_login_v11_sample.json` (nuevo): respuesta de
  ejemplo del login v1.1 con la forma real observada en vivo, token
  ficticio.
- `ingesta/README.md`: sección de `transporte_publico_madrid.py` actualizada
  al flujo v1.1 (variables de entorno, ejemplo de ejecución, nota de
  captura real); referencias cruzadas en las secciones de `bicimad.py` y
  `crtm_red_transporte_madrid.py` corregidas para no seguir describiendo la
  EMT como bloqueada.

## Suite de tests

Verificada tras el cambio: **225 tests** (220 previos + 5 nuevos), todos en
verde (`python3 -m unittest discover -s ingesta/tests -p "test_*.py"`).

## Relevante para tareas futuras

- El patrón de esta tarea es distinto al de los bloqueos "reales" del
  proyecto (AEMET tarea 018, CAMS/ADS tarea 019, WizinkCenter/Cinesa por
  WAF): aquí no había ningún bloqueo técnico ni de identidad — la tarea 003
  simplemente documentó mal el mecanismo de autenticación de la API
  (asumió email/contraseña de usuario cuando en realidad son credenciales
  de aplicación). Vale la pena, ante una fuente que parece requerir
  registro de cuenta personal, verificar primero si existe un flujo de
  credenciales de aplicación/API key de servicio antes de asumir que hace
  falta una identidad personal verificada por email.
- El hallazgo de los dos códigos de éxito (`"00"`/`"01"`) es específico de
  esta API y no está documentado públicamente en ningún sitio evidente
  durante esta investigación; si una tarea futura ve fallar el login con un
  código inesperado, conviene revisar primero si es realmente un error o
  un tercer caso de éxito no contemplado (`data[0]` sigue trayendo
  `accessToken`).
- La API MobilityLabs de la EMT queda ahora como la única fuente del
  proyecto con llegadas de autobús en tiempo real y funcional; el hallazgo
  de la tarea 021 (CRTM no publica GTFS-RT abierto) sigue siendo válido —
  no hay alternativa multimodal — pero ya no aplica como razón para
  mantener la EMT bloqueada, porque ya no lo está.
