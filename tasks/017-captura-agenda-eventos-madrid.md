---
id: 17
slug: captura-agenda-eventos-madrid
title: "Captura de la agenda oficial de eventos culturales de Madrid (muestra)"
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

Complementa a la tarea 016 (Bluesky, opiniones/menciones informales) con una fuente
de mayor calidad para "eventos" en concreto: el Ayuntamiento de Madrid publica en
datos.madrid.es la agenda oficial de actividades culturales y de ocio en centros
municipales — dataset "Actividades culturales y de ocio municipal en los próximos
100 días" (id `206974-0-agenda-eventos-culturales-100`), accesible vía API CKAN
(`datastore_search`) sin autenticación. Es dato oficial y programado (conciertos,
exposiciones, actividades en bibliotecas/centros culturales/juveniles/de mayores),
justo el tipo de señal que ayuda a explicar picos de afluencia esperados en un
lugar y momento concretos — sin depender de scraping ni zona gris, a diferencia de
la tarea 012 y a diferencia de intentar inferir eventos solo de redes sociales.

Se investigaron y descartaron alternativas antes de esta tarea: Eventbrite (su
búsqueda pública de eventos está descontinuada, la API solo sirve para gestionar
eventos propios) y Foursquare (las reseñas/tips están detrás de un tier de pago).

## Objetivo

Capturar una muestra pequeña de la agenda de eventos culturales de Madrid,
normalizada a un esquema mínimo y consistente.

## Alcance concreto

1. Crea `ingesta/capturas/agenda_eventos_madrid.py` siguiendo el mismo patrón que
   el resto de capturas: descarga (vía la API CKAN `datastore_search` o el recurso
   CSV/XML directo, decide cuál es más simple y documenta por qué) -> normaliza a
   un esquema mínimo y consistente (id del evento, título, descripción breve,
   categoría/tipo, fecha/hora de inicio y fin, ubicación — nombre del centro,
   dirección, distrito, coordenadas si el dataset las da).
2. Investiga también el dataset complementario "Agenda turística de la ciudad de
   Madrid" (`www.esmadrid.com`, id `300028-0-agenda-turismo`) mencionado en el
   propio portal — si aporta cobertura relevante que la agenda municipal no tiene
   (p. ej. eventos no municipales), decide si merece la pena incluirlo también en
   esta misma tarea o dejarlo anotado para una tarea futura; documenta la decisión.
3. El script, ejecutado una vez, produce una muestra pequeña (unos pocos eventos,
   no la agenda completa de 100 días) y la guarda como fixture versionado.
4. Añade un test que no dependa de la red real (con un fixture de ejemplo).
5. Documenta el módulo en `ingesta/README.md`.

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente: ni cron, ni systemd
  timer, ni un modo `--interval-seconds`/`--daemon`. Es una captura puntual que
  produce una muestra pequeña.
- NO escribas datos de forma continua ni sin acotar en el disco de esta EC2.
- No deberían hacer falta credenciales (son datos abiertos municipales).
- Si la fuente pública no fuera accesible desde este entorno, documenta el problema
  en el resumen de `doc/017-captura-agenda-eventos-madrid.md` y deja igualmente el
  código preparado con datos de ejemplo.

## Criterios de aceptación

- Ejecutar el script una vez produce una muestra de unos pocos eventos
  normalizados, visible en el PR como fixture pequeño commiteado, sin dejar nada
  corriendo ni programado.
- El esquema normalizado y la decisión sobre el dataset de esMadrid.com quedan
  documentados en `ingesta/README.md` y en el resumen de `doc/`.
