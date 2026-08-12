---
id: 6
slug: captura-calidad-aire-madrid
title: Captura de datos de calidad del aire de Madrid (muestra)
status: done
force: true
branch: task/006-captura-calidad-aire-madrid
pr_number: 53
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/53
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-12T01:02:26+00:00'
updated_at: '2026-08-12T01:33:53.825623+00:00'
started_at: '2026-08-12T01:26:18.281653+00:00'
submitted_at: '2026-08-12T01:32:47.316129+00:00'
merged_at: '2026-08-12T01:32:50Z'
---

## Contexto

Continúa la Fase 1 (Ingesta) del proyecto (ver `documents/Memoria_TFM FV.docx`,
apartado 6.1, categoría «Medioambiente»: calidad del aire). Sigue el mismo patrón
que la tarea 002 (`ingesta/capturas/trafico_madrid.py`).

**Importante — alcance reducido**: la tarea 001 (infraestructura AWS) todavía no se
ha aplicado. Esta tarea NO debe implementar un productor continuo ni dejar nada
programado — ver Restricciones.

## Objetivo

Investigar y usar la fuente de datos abiertos de calidad del aire en tiempo real del
Ayuntamiento de Madrid (datos.madrid.es publica lecturas horarias de la red de
estaciones de control de contaminación) y producir una muestra pequeña de datos
normalizados.

## Alcance concreto

1. Crea `ingesta/capturas/calidad_aire_madrid.py` siguiendo el mismo patrón que
   `trafico_madrid.py`: descarga -> normaliza a un esquema mínimo y consistente
   (timestamp, id de estación, ubicación, magnitud medida — NO2, PM10, O3, etc. — y
   su valor).
2. El formato de origen puede requerir un parseo distinto al XML de tráfico (p.ej.
   CSV horario); documenta el formato real encontrado.
3. El script, ejecutado una vez, produce una muestra pequeña (unas pocas estaciones o
   magnitudes) y la guarda como fixture versionado — no como una captura en bucle.
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
- No deberían hacer falta credenciales (son datos abiertos municipales); si la fuente
  elegida requiere una API key gratuita, documenta cómo obtenerla y léela de una
  variable de entorno.
- Si la fuente pública no fuera accesible desde este entorno, documenta el problema en
  el resumen de `doc/` y deja igualmente el código preparado con datos de ejemplo.

## Criterios de aceptación

- Ejecutar el script una vez produce una muestra de unos pocos registros normalizados,
  visible en el PR como fixture pequeño commiteado, sin dejar nada corriendo ni
  programado.
- El esquema normalizado y la fuente elegida quedan documentados en
  `ingesta/README.md` y en el resumen de `doc/`.
