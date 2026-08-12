---
id: 4
slug: captura-bicimad
title: Captura de datos de BiciMAD (bicicleta compartida) (muestra)
status: in_progress
force: true
branch: task/004-captura-bicimad
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-12T01:02:26+00:00'
updated_at: '2026-08-12T01:12:08.915790+00:00'
started_at: '2026-08-12T01:12:08.915766+00:00'
submitted_at: null
merged_at: null
---

## Contexto

Continúa la Fase 1 (Ingesta) del proyecto (ver `documents/Memoria_TFM FV.docx`,
apartado 6.1, categoría «Movilidad y transporte»: bicicleta compartida). Sigue el
mismo patrón que la tarea 002 (`ingesta/capturas/trafico_madrid.py`).

**Importante — alcance reducido**: la tarea 001 (infraestructura AWS) todavía no se
ha aplicado. Esta tarea NO debe implementar un productor continuo ni dejar nada
programado — ver Restricciones.

## Objetivo

Investigar y usar una fuente de datos abiertos del servicio de bicicleta compartida
de Madrid, BiciMAD (estado de estaciones: bicis y anclajes disponibles). Muchos
sistemas de bicicleta compartida publican un feed abierto estándar GBFS (General
Bikeshare Feed Specification) sin autenticación — comprueba si BiciMAD/EMT lo ofrece;
si no, usa el portal opendata.emtmadrid.es (requiere registro gratuito). Usa tu
criterio y documenta la fuente elegida.

## Alcance concreto

1. Crea `ingesta/capturas/bicimad.py` siguiendo el mismo patrón que
   `trafico_madrid.py`: descarga -> normaliza a un esquema mínimo y consistente
   (timestamp, id de estación, ubicación, bicis disponibles, anclajes libres/totales).
2. Si la fuente requiere una API key gratuita, léela de una variable de entorno, sin
   hardcodearla, y documenta cómo obtenerla.
3. El script, ejecutado una vez, produce una muestra pequeña (unas pocas estaciones,
   no la red completa) y la guarda como fixture versionado — no como una captura en
   bucle.
4. Añade un test que no dependa de la red real (con un fixture de ejemplo).
5. Documenta el módulo en `ingesta/README.md`.

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente: ni cron, ni systemd timer,
  ni un modo `--interval-seconds`/`--daemon`. Es una captura puntual que produce una
  muestra pequeña.
- NO escribas datos de forma continua ni sin acotar en el disco de esta EC2. El
  resultado es una muestra pequeña guardada como fixture versionado en el repo — no
  un bucle de captura hacia `./bronze/...`. La conexión al destino real (S3/BD)
  llegará en una tarea posterior, tras aplicar la infraestructura.
- No uses APIs de pago. Una API key gratuita con registro es aceptable.
- Si la fuente pública no fuera accesible desde este entorno, documenta el problema en
  el resumen de `doc/` y deja igualmente el código preparado con datos de ejemplo.

## Criterios de aceptación

- Ejecutar el script una vez produce una muestra de unas pocas estaciones
  normalizadas, visible en el PR como fixture pequeño commiteado, sin dejar nada
  corriendo ni programado.
- El esquema normalizado y la fuente elegida quedan documentados en
  `ingesta/README.md` y en el resumen de `doc/`.
