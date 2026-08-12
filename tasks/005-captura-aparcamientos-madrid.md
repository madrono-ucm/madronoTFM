---
id: 5
slug: captura-aparcamientos-madrid
title: Captura de ocupación de aparcamientos públicos de Madrid (muestra)
status: in_review
force: true
branch: task/005-captura-aparcamientos-madrid
pr_number: 52
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/52
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-12T01:02:26+00:00'
updated_at: '2026-08-12T01:24:09.633560+00:00'
started_at: '2026-08-12T01:18:18.807988+00:00'
submitted_at: '2026-08-12T01:24:09.633428+00:00'
merged_at: null
---

## Contexto

Continúa la Fase 1 (Ingesta) del proyecto (ver `documents/Memoria_TFM FV.docx`,
apartado 6.1, categoría «Movilidad y transporte»: ocupación de aparcamientos). Sigue
el mismo patrón que la tarea 002 (`ingesta/capturas/trafico_madrid.py`).

**Importante — alcance reducido**: la tarea 001 (infraestructura AWS) todavía no se
ha aplicado. Esta tarea NO debe implementar un productor continuo ni dejar nada
programado — ver Restricciones.

## Objetivo

Investigar y usar una fuente de datos abiertos de ocupación de aparcamientos
públicos/disuasorios de Madrid (portal datos.madrid.es tiene datasets de
aparcamientos municipales y de la EMT con plazas libres en tiempo real — investiga y
elige el más adecuado, documenta por qué) y producir una muestra pequeña de datos
normalizados.

## Alcance concreto

1. Crea `ingesta/capturas/aparcamientos_madrid.py` siguiendo el mismo patrón que
   `trafico_madrid.py`: descarga -> normaliza a un esquema mínimo y consistente
   (timestamp, id del aparcamiento, nombre/ubicación, plazas libres, plazas totales
   si están disponibles en la fuente).
2. El script, ejecutado una vez, produce una muestra pequeña (unos pocos
   aparcamientos) y la guarda como fixture versionado — no como una captura en bucle.
3. Añade un test que no dependa de la red real (con un fixture de ejemplo).
4. Documenta el módulo en `ingesta/README.md`.

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente: ni cron, ni systemd timer,
  ni un modo `--interval-seconds`/`--daemon`. Es una captura puntual que produce una
  muestra pequeña.
- NO escribas datos de forma continua ni sin acotar en el disco de esta EC2. El
  resultado es una muestra pequeña guardada como fixture versionado en el repo — no
  un bucle de captura hacia `./bronze/...`. La conexión al destino real (S3/BD)
  llegará en una tarea posterior, tras aplicar la infraestructura.
- No necesitas credenciales; si la fuente elegida requiere una API key gratuita, es
  aceptable — documenta cómo obtenerla y léela de una variable de entorno.
- Si la fuente pública no fuera accesible desde este entorno, documenta el problema en
  el resumen de `doc/` y deja igualmente el código preparado con datos de ejemplo.

## Criterios de aceptación

- Ejecutar el script una vez produce una muestra de unos pocos aparcamientos
  normalizados, visible en el PR como fixture pequeño commiteado, sin dejar nada
  corriendo ni programado.
- El esquema normalizado y la fuente elegida quedan documentados en
  `ingesta/README.md` y en el resumen de `doc/`.
