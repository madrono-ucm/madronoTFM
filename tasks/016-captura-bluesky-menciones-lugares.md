---
id: 16
slug: captura-bluesky-menciones-lugares
title: "Captura de menciones/opiniones de Bluesky sobre lugares de Madrid (muestra)"
status: pending
force: true
allow_infra_apply: false
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: "2026-08-13T17:10:02+00:00"
updated_at: "2026-08-13T17:10:02+00:00"
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

El asistente «Madroño» necesita una señal de opiniones/eventos recientes sobre un
lugar (memoria, apartado 6.7: "¿voy al centro a las nueve de la noche del
viernes?"). Twitter/X no es viable (API de pago, sin acceso gratuito). Se investigó
como alternativa: **Bluesky** tiene API pública, gratis, sin API key ni registro,
sin límite de rate para lectura pública (`https://public.api.bsky.app`) — se elige
esta fuente. Se descartó Mastodon/Fediverso (sin búsqueda unificada, fragmentado
por instancia, cobertura en español mucho menor) y CAMARA/Telefónica Population
Density Data (API de operadora todavía "under review", exige partner comercial y
consentimiento por usuario — no autoservicio).

**Diseño de captura acordado (dos modos, ambos a implementar en esta tarea):**

1. **Bajo demanda**: cuando el asistente no tiene información concreta de un lugar
   que el usuario menciona, hace una búsqueda rápida y localizada (por nombre del
   lugar + hashtags/etiquetas específicas). Esto lo invocará en el futuro el
   servicio del asistente en tiempo de consulta, no un productor programado — en
   esta tarea, implementa la función reutilizable, no la despliegues como servicio.
2. **Programada (cada hora, cuando exista scheduling)**: búsquedas generales por
   distrito/barrio de Madrid (usa la lista de `tasks/010`/`ingesta/capturas/samples/barrios_distritos_madrid_sample.json`
   si existe, o los nombres de distrito documentados en `ingesta/README.md`) y por
   eventos (buenos o malos: quejas, incidencias, aglomeraciones, recomendaciones),
   pensada para nutrir el entrenamiento del modelo con una serie histórica agregada
   por zona y hora.

## Objetivo

Implementar el productor de captura de Bluesky con ambos modos, y una muestra
pequeña real (no mock, verificada en vivo) que permita ver **cómo llega el dato en
local antes de pasarlo a producción** — es literalmente el objetivo principal de
esta tarea, no un detalle secundario.

## Alcance concreto

1. Crea `ingesta/capturas/bluesky_menciones_madrid.py` con:
   - `search_place(query, tags=None, lang="es", since=None)`: búsqueda puntual por
     lugar/hashtag — la función que usará el modo "bajo demanda".
   - `search_district_sweep(districts, lang="es", since=None)`: recorre una lista
     de distritos/barrios de Madrid haciendo una búsqueda general por cada uno (más
     una búsqueda genérica de "eventos Madrid" con términos positivos/negativos
     razonables) — la función que usará el modo "cada hora".
   - Usa el endpoint público `app.bsky.feed.searchPosts` en
     `https://public.api.bsky.app` (sin autenticación, `q` con sintaxis Lucene,
     `since`/`until`, `lang`).
2. **Privacidad — restricción de diseño explícita del propio proyecto (memoria,
   apartado 6.8: "las señales de discurso social se tratan de forma agregada, sin
   almacenar identificadores")**: el esquema normalizado **NO debe incluir** el
   handle/DID/identificador del autor del post, ni ningún otro dato personal. Guarda
   solo lo necesario como señal agregable: texto del post (o un resumen/hash si
   prefieres no conservar el texto literal, decide y documenta por qué),
   `created_at`, el término/distrito que produjo el match, y contadores públicos
   (likes/reposts) si el endpoint los da. Si tienes dudas sobre qué campo podría
   ser identificable, exclúyelo.
3. No hagas clasificación de sentimiento ("bueno"/"malo") en esta tarea — eso es
   una transformación de Silver/Gold, fuera de alcance aquí. Limítate a capturar y
   normalizar.
4. Genera la muestra pequeña ejecutando **ambos modos** de verdad contra la API
   pública (unos pocos lugares/distritos, no todos) y commitea el resultado en
   `ingesta/capturas/samples/` — es la forma de "ver cómo llega el dato en local"
   antes de conectar nada a producción.
5. Añade un test que no dependa de la red real (con una respuesta de ejemplo del
   endpoint).
6. Documenta en `ingesta/README.md`: los dos modos y su propósito distinto (uno es
   para el asistente en tiempo de consulta, el otro para entrenamiento), el filtro
   de privacidad aplicado y por qué, y variables de entorno si las hay.

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente: ni cron, ni systemd
  timer, ni un modo `--interval-seconds`/`--daemon`. Ninguno de los dos modos se
  despliega en esta tarea, solo se implementan y se prueban con una muestra.
- NO escribas datos de forma continua ni sin acotar en el disco de esta EC2 —
  muestra pequeña, fixture versionado, como el resto de capturas.
- NO almacenes identificadores de autor ni ningún dato personal — ver la sección de
  privacidad arriba, es un requisito, no una sugerencia.
- No hagas scraping de la web de Bluesky ni uses ninguna librería no oficial: el
  endpoint público documentado es suficiente y no requiere autenticación.

## Criterios de aceptación

- `search_place` y `search_district_sweep` existen, funcionan contra la API real, y
  producen resultados normalizados sin identificadores de autor.
- La muestra commiteada en `ingesta/capturas/samples/` contiene resultados reales de
  ambos modos (no datos inventados a mano, salvo que la API no fuera accesible desde
  este entorno, en cuyo caso documenta el problema en `doc/016-captura-bluesky-menciones-lugares.md`).
- `ingesta/README.md` documenta claramente los dos modos, su uso previsto distinto,
  y el filtro de privacidad aplicado.
