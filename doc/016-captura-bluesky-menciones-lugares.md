# 016 — Captura de menciones/opiniones de Bluesky sobre lugares de Madrid (muestra)

## Qué se implementó

`ingesta/capturas/bluesky_menciones_madrid.py`: productor de menciones
públicas de Bluesky sobre Madrid, con **dos modos** implementados y
probados, ninguno desplegado como servicio/cron en esta tarea:

- `search_place(config, query, tags=None, lang="es", since=None, ...)`:
  búsqueda puntual por lugar/hashtag, pensada para que el asistente
  conversacional la invoque en tiempo de consulta.
- `search_district_sweep(config, districts, lang="es", since=None, ...)`:
  barrido por distrito de Madrid + búsquedas genéricas de "eventos Madrid"
  (términos positivos y negativos), pensado para un futuro productor
  programado cada hora que alimente una serie histórica agregada por zona.

Ambas comparten `search_posts_raw` (llamada HTTP a
`app.bsky.feed.searchPosts`) y `normalize_post` (normalización al esquema
mínimo). No hay clasificación de sentimiento: eso es Silver/Gold, fuera de
alcance.

Documentación completa (esquema, variables de entorno, ejemplos) en
`ingesta/README.md`, sección `capturas/bluesky_menciones_madrid.py`.

## Decisiones relevantes

- **Fuente elegida: Bluesky, sin API key ni registro.** Se descartaron
  Twitter/X (sin API gratuita viable), Mastodon/Fediverso (sin búsqueda
  unificada, cobertura en español mucho menor) y CAMARA/Telefónica
  Population Density Data (API de operadora "under review", exige partner
  comercial y consentimiento por usuario, no autoservicio).
- **Privacidad — sin identificadores de autor.** `normalize_post` descarta
  explícitamente `author` (`did`/`handle`/`displayName`/`avatar`) y también
  `uri`/`cid` del post, porque el `uri` de Bluesky incluye el DID del autor
  (`at://did:plc:.../app.bsky.feed.post/...`). Se decidió conservar el
  **texto literal** del post (no un hash) porque es contenido ya público y
  es la señal necesaria para una futura clasificación de sentimiento; lo que
  se excluye es todo lo que identifique a quién lo escribió, no el
  contenido. Se añade `post_hash` (SHA-256 truncado del texto) como clave de
  deduplicación entre términos de búsqueda solapados, sin depender del `uri`
  real.
- **Un único dataset con campo `mode`, no dos ficheros.** Sigue el mismo
  patrón ya establecido en la tarea 013
  (`aforos_peatones_bicicletas_madrid.py`): la muestra combina ambos modos
  en `bluesky_menciones_madrid_sample.json` con `mode` = `"bajo_demanda"` /
  `"distrito_sweep"`; quien necesite solo un modo filtra por ese campo.
- **`config: CaptureConfig` como primer argumento de ambas funciones**, en
  vez de leer variables de entorno dentro de ellas — mismo patrón que
  `resolve_place_id`/`fetch_populartimes` en `afluencia_lugares_madrid.py`
  (tarea 012), para mantener consistencia con el resto de `ingesta/capturas/`
  aunque el enunciado de la tarea sugiriera una firma más simple.
- **21 distritos por defecto obtenidos en vivo**, no adivinados: se
  consultó el mismo servicio ArcGIS que usa `barrios_distritos_madrid.py`
  (tarea 010,
  `sigma.madrid.es/.../LIMITES_ADMINISTRATIVOS/MapServer/26/query`) para
  obtener la grafía oficial exacta (p.ej. `"Fuencarral - El Pardo"`, con
  espacios alrededor del guion, no `"Fuencarral-El Pardo"`).

## Descubrimiento importante: `public.api.bsky.app` bloquea `searchPosts` desde este entorno

El host documentado por el AT Protocol para lectura pública sin
autenticación es `https://public.api.bsky.app`. Se verificó en vivo que
**ese host responde `403 Forbidden` (página HTML de BunnyCDN, no JSON)
específicamente para `app.bsky.feed.searchPosts`**, mientras que otros
métodos de solo lectura en el mismo host (`app.bsky.actor.searchActors`,
`app.bsky.unspecced.getPopularFeedGenerators`, `/xrpc/_health`) responden
`200` con normalidad desde la misma IP. El bloqueo persistió cambiando
`User-Agent` y añadiendo cabeceras de navegador (`Accept`/`Origin`/
`Referer`); no depende de los parámetros de la búsqueda. Apunta a un
bloqueo del WAF específico de esa ruta para el rango de IP de esta EC2 (muy
probablemente porque `searchPosts` es el endpoint más costoso de servir y
más atractivo para scraping masivo, así que Bluesky/BunnyCDN lo protegen más
que el resto de la API pública).

En cambio, **`https://api.bsky.app`** — el mismo host que usa la propia web
`bsky.app` para sus peticiones al AppView — expone la misma operación
`app.bsky.feed.searchPosts`, con la misma respuesta, y respondió `200`
repetidamente durante esta sesión. Por eso el módulo usa
`https://api.bsky.app` como valor por defecto de `BLUESKY_API_BASE_URL`
(configurable, por si en otro entorno —p.ej. la máquina donde corra el
asistente en producción— `public.api.bsky.app` sí funciona o se prefiere
por ser el host oficialmente documentado).

## Captura real en vivo

Se completó una **captura real en vivo** con ambos modos: el fixture
commiteado en
`ingesta/capturas/samples/bluesky_menciones_madrid_sample.json` son **40
posts reales** —15 de `search_place` (lugares "Puerta del Sol", "Parque del
Retiro", "Malasaña") y 25 de `search_district_sweep` (distritos Centro,
Arganzuela, Retiro + términos de eventos "concierto", "fiesta")—,
descargados ejecutando `python3 -m ingesta.capturas.bluesky_menciones_madrid`
tal cual contra `https://api.bsky.app` durante esta sesión. No son datos de
ejemplo generados a mano; se verificó manualmente que ningún registro
contiene `author`/`did`/`handle`/`displayName`/`avatar`/`uri`/`cid`.

El fixture de test (`ingesta/tests/fixtures/bluesky_search_posts_sample.json`,
usado solo para probar `normalize_post` sin red) sí usa autores/`uri`/`cid`
inventados en vez de reales, a propósito: no hace falta preservar
identificadores reales de terceros en un fixture de test versionado en el
repositorio, aunque `normalize_post` los descartaría de todas formas.

## Tests

`ingesta/tests/test_bluesky_menciones_madrid.py`: no dependen de la red,
usan el fixture anterior. Cubren `_build_query`, `normalize_post` (ambos
modos, deduplicación por `post_hash`, ausencia explícita de identificadores
de autor), y una verificación de esquema sobre la propia muestra
commiteada. Suite completa del proyecto verificada tras el cambio: 115 tests
(106 previos + 9 nuevos), todos en verde.

## Relevante para tareas futuras

- **El host real a usar para `app.bsky.feed.searchPosts` desde infraestructura
  AWS de este proyecto (EC2, Lambda...) es `https://api.bsky.app`, no
  `https://public.api.bsky.app`.** Si una tarea futura despliega el modo
  `search_place` como parte del servicio del asistente conversacional (o el
  modo `search_district_sweep` como productor programado real), debería
  verificar de nuevo el comportamiento del host desde el entorno de destino
  final antes de asumir cuál funciona — el bloqueo observado aquí es
  específico de la IP/rango de esta EC2 en el momento de esta sesión, y
  podría no reproducirse igual (o podría aparecer también en `api.bsky.app`)
  desde otra infraestructura.
- Igual que las tareas 003-008, 012 y 013, este productor sigue sin estar
  conectado a ningún destino de almacenamiento definitivo (S3/Bronze); eso
  llegará en una tarea posterior. `TODO(kafka)` queda marcado en el módulo
  por consistencia, aplicable solo al modo `search_district_sweep` (el modo
  `search_place` no es un productor continuo, es una función de consulta
  bajo demanda del futuro servicio del asistente, no debería conectarse a
  Kafka).
- El patrón "un único dataset con campo `mode`" para representar "dos formas
  de capturar la misma fuente, con propósitos distintos (consulta puntual
  vs. serie histórica)" es, junto con el precedente ya sentado en la tarea
  013 para "dos redes de sensores distintas", un segundo precedente
  reutilizable: aquí para "dos *modos de invocación* de la misma fuente",
  un caso ligeramente distinto que puede servir de referencia para fuentes
  futuras con esa misma forma (una función de consulta puntual + un barrido
  programado).
- La restricción de privacidad aplicada aquí (excluir `author`/`uri`/`cid`
  por completo, conservando solo texto y contadores agregables) es el primer
  precedente concreto de "captura de discurso social" del proyecto; si una
  tarea futura añade otra fuente de este tipo (otra red social, foros,
  reseñas con autor visible...), debería aplicar el mismo criterio general
  del apartado 6.8 de la memoria: nunca persistir el identificador del
  autor, aunque la fuente sí lo exponga.
