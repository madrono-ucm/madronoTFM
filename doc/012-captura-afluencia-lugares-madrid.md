# 012 — Captura de afluencia de lugares de Madrid (muestra, zona gris)

## Qué se implementó

Undécimo productor de datos de la Fase 1 (Ingesta), y el primero de un tipo
distinto a todos los anteriores: no usa una fuente de datos.madrid.es ni
ningún otro portal municipal, sino la librería de terceros
[`m-wrzr/populartimes`](https://github.com/m-wrzr/populartimes) para obtener
un dato de afluencia (popularidad tipo Google) que no está disponible por
ninguna API oficial.

- `ingesta/capturas/afluencia_lugares_madrid.py`: para una muestra de 5
  lugares conocidos de Madrid (Puerta del Sol, Parque del Retiro, Mercado de
  San Miguel, Museo del Prado, Plaza Mayor), resuelve cada nombre a un
  `place_id` de Google (API oficial "Find Place from Text") y obtiene
  popularidad en vivo (`live_pct`) y patrón habitual por día/hora
  (`typical_by_hour`) vía `populartimes.get_id(...)`. Sin bucle, sin
  `--interval-seconds`, sin `BronzeWriter`.
- `ingesta/requirements.txt`: añadida
  `populartimes @ git+https://github.com/m-wrzr/populartimes` — **no** desde
  PyPI, porque no está publicada allí (comprobado en vivo:
  `https://pypi.org/pypi/populartimes/json` devuelve `404`).
- `ingesta/capturas/samples/afluencia_lugares_madrid_sample.json`: la
  muestra commiteada como fixture, 5 lugares, **datos de ejemplo (mock)**,
  cada registro con `"is_mock": true` — ver más abajo, "Resultado del
  intento de captura real".
- `ingesta/tests/test_afluencia_lugares_madrid.py` +
  `ingesta/tests/fixtures/populartimes_get_id_sample.json` +
  `ingesta/tests/fixtures/find_place_sample.json`: tests con `unittest` (sin
  red) que verifican la normalización de días de la semana a claves en
  español, el caso de un lugar sin ningún dato de popularidad
  (`current_popularity`/`populartimes` ausentes en la fuente), el parseo de
  la respuesta "Find Place" (con y sin resultados), y que la muestra
  commiteada cumple el esquema esperado y está marcada como mock.
- `ingesta/README.md`: nueva sección para esta fuente — origen del dato (API
  oficial + scraping no documentado), cita explícita al apartado 6.8 de la
  memoria sobre la zona gris académica, la alternativa comercial para
  producción (BestTime.app), variables de entorno, esquema, y el resultado
  concreto del intento de captura real en esta sesión.

## Resultado del intento de captura real: la librería NO falló, faltó la API key

**No se pudo hacer una captura real en vivo en esta sesión**, pero no porque
`populartimes` estuviera rota (el riesgo que la propia tarea anticipaba): el
único bloqueo real fue no tener configurada ninguna `GOOGLE_MAPS_API_KEY` en
este entorno (obtenerla requiere dar de alta un proyecto en Google Cloud,
un paso manual no automatizable de forma autónoma en este pipeline — mismo
tipo de bloqueo que la verificación por email de la EMT en la tarea 003). Se
verificó en vivo, con una clave de prueba deliberadamente inválida:

- `pip install "populartimes @ git+https://github.com/m-wrzr/populartimes"`
  instala sin errores (arrastra `geopy`/`urllib3` como dependencias
  transitivas).
- `resolve_place_id` (la llamada oficial "Find Place from Text") completa
  una petición HTTP real y recibe `200 OK` con
  `{"status": "REQUEST_DENIED", ...}` de Google — el módulo lo interpreta
  correctamente como "sin candidato" y sigue con el resto de la muestra sin
  interrumpirse.
- `populartimes.get_id("FAKE_KEY_FOR_TESTING", <place_id real>)` sí llega a
  ejecutarse (contra la API de detalles de Google) y lanza
  `populartimes.crawler.PopulartimesException` con el mensaje exacto
  `('Google Places REQUEST_DENIED', 'Request was denied, the API key is
  invalid.')`.

Es decir: el código de este módulo funciona de extremo a extremo contra los
endpoints reales; solo falta una credencial válida para producir una
captura real. Por eso el fixture commiteado son 5 registros de ejemplo
escritos a mano (no descargados), cada uno con el campo `"is_mock": true`
para que la procedencia quede explícita en el propio dato y no solo en esta
nota — incluyendo un caso realista (Plaza Mayor) con `live_pct` y
`typical_by_hour` ambos a `null`, el mismo comportamiento que tendría un
lugar real sin datos suficientes en Google.

## Decisiones de diseño (por qué)

- **Zona gris citada explícitamente, no ocultada**: tanto el docstring del
  módulo como el README citan el apartado 6.8 de la memoria y dejan
  explícito que esta técnica (scraping de un endpoint no documentado de
  Google) es admisible solo en el marco académico de este TFM, con
  BestTime.app como ejemplo de alternativa comercial para producción — sin
  integrarla, solo mencionada, tal como pedía el objetivo de la tarea.
- **No se reimplementa el scraping**: `fetch_populartimes` es un wrapper
  fino sobre `populartimes.get_id(...)`; toda la lógica de scraping vive en
  la dependencia externa, tal como exigía explícitamente el objetivo de la
  tarea.
- **Dos llamadas separadas, cada una testeada por su cuenta**: resolver el
  lugar (`resolve_place_id`/`_pick_candidate`, API oficial "Find Place") y
  obtener la popularidad (`fetch_populartimes`, vía la librería) son pasos
  independientes con fuentes de fiabilidad muy distinta (una es una API
  oficial estable, la otra es scraping frágil); separarlos permite que un
  fallo en la resolución de un lugar concreto (p.ej. `ZERO_RESULTS`) no
  aborte la captura completa de la muestra — se registra un `WARNING` y se
  continúa con el resto, mismo criterio de robustez por-registro que
  `poi_madrid.py` (tarea 011) con puntos sin coordenadas.
- **`is_mock` como campo del esquema, no solo nota de documentación**: a
  diferencia de la tarea 003 (fixture de EMT hecho a mano sin ningún
  marcador en el propio dato), aquí se decidió añadir un campo explícito
  `is_mock: bool` en el esquema normalizado. Con una fuente tan
  explícitamente de "zona gris académica", parecía más honesto que la
  procedencia de cada registro (captura real vs. ejemplo escrito a mano)
  quede trazable en el dato mismo, no solo en el README — útil sobre todo si
  esta muestra llegara a mezclarse alguna vez con una futura captura real
  sin revisar antes cada registro a mano.
- **Días de la semana normalizados a claves en español** (`lunes`...
  `domingo`), no las que devuelve la librería en inglés (`Monday`...
  `Sunday`): consistencia con el resto de este proyecto, que es
  íntegramente en español.
- **`MADRID_PLACES_QUERIES` configurable por variable de entorno** (lista
  separada por `|`), con `DEFAULT_PLACE_QUERIES` como los 5 lugares del
  objetivo de la tarea: permite ampliar o cambiar la muestra sin tocar
  código, mismo patrón de configuración por entorno que el resto de
  productores de este proyecto.
- **Sin `BronzeWriter` ni modo `--interval-seconds`, y esto no es temporal**:
  a diferencia de las tareas 003-008 (que sí serán productores continuos el
  día que exista infraestructura), aquí la razón de fondo no desaparece con
  la infraestructura: raspar Google en bucle agravaría el problema de zona
  gris. Un futuro productor continuo real de este dato debería migrar al
  proveedor comercial mencionado (BestTime.app o similar), no escalar esta
  técnica — se documenta así explícitamente para que una tarea futura no dé
  por hecho que basta con añadir un bucle cuando llegue la infraestructura.

## Relevante para tareas futuras

- Esta captura depende de una `GOOGLE_MAPS_API_KEY` real para producir datos
  reales; el día que alguien la configure (ver README, sección
  "Autenticación", con el enlace directo a la consola de Google Cloud), el
  código ya está listo para ejecutarse tal cual sin cambios.
- Si en el futuro se sustituye esta fuente por un proveedor comercial
  (BestTime.app u otro), el esquema normalizado (`live_pct`,
  `typical_by_hour` con claves de día en español y 24 valores por día)
  debería poder mantenerse igual de cara a los consumidores downstream —
  solo cambiaría cómo se rellena, no la forma del dato.
- El campo `is_mock` introducido en esta tarea es un patrón nuevo en este
  proyecto (ninguna captura anterior lo tenía, ni siquiera la de la tarea
  003 con el mismo tipo de bloqueo de credencial); si una tarea futura
  encuentra el mismo tipo de bloqueo (fuente real pero credencial no
  obtenible de forma autónoma), podría valorar adoptar el mismo campo para
  que la procedencia del dato quede trazable sin depender de la
  documentación externa.
- Igual que en las tareas 003-011, este productor sigue sin estar conectado
  a ningún destino de almacenamiento definitivo (S3/Bronze); eso llegará en
  una tarea posterior, tras aplicar la infraestructura de la tarea 001.
  `TODO(kafka)` queda marcado en el módulo por consistencia con el resto de
  productores, aunque dado el carácter de zona gris de esta fuente, un
  productor continuo real debería reevaluar la fuente en sí (migrar al
  proveedor comercial) antes de conectarse a ningún broker en producción.
