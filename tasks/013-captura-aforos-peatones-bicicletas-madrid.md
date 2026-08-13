---
id: 13
slug: captura-aforos-peatones-bicicletas-madrid
title: Captura de aforos de peatones y bicicletas de Madrid (muestra)
status: in_review
force: true
allow_infra_apply: false
branch: task/013-captura-aforos-peatones-bicicletas-madrid
pr_number: 60
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/60
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-12T23:12:29+00:00'
updated_at: '2026-08-13T15:48:23.261956+00:00'
started_at: '2026-08-13T15:39:18.651031+00:00'
submitted_at: '2026-08-13T15:48:23.261932+00:00'
merged_at: null
---

## Contexto

Fase 1 (Ingesta) del proyecto (ver `documents/Memoria_TFM FV.docx`, apartado 6.1
«Contexto urbano»: afluencia de lugares públicos). Complementa a la tarea 012: donde
la 012 estima la popularidad de un lugar concreto (vía una librería en zona gris,
solo admisible en el marco académico), esta tarea usa una fuente **oficial y sin
ningún problema de condiciones de uso**: el Ayuntamiento de Madrid publica en
datos.madrid.es el dataset «Aforos de peatones y bicicletas», con conteos horarios
desde 2019, alimentado por una red de estaciones con cámaras de visión artificial
(tecnología Data From Sky) en puntos fijos de la ciudad.

A diferencia de la tarea 012 (por lugar concreto, tipo negocio/POI), esta fuente mide
afluencia peatonal/ciclista en **puntos y calles fijas** — es un dato real que
cambia con el tiempo (como tráfico, aire o ruido), no una carga de referencia
estática como las tareas 009-011.

**Importante — mismo alcance reducido que el resto de capturas**: la tarea 001
(infraestructura AWS) todavía no se ha aplicado. Esta tarea NO debe implementar un
productor continuo ni dejar nada programado — ver Restricciones.

## Objetivo

Investigar y usar el dataset «Aforos de peatones y bicicletas» de datos.madrid.es y
producir una muestra pequeña de datos normalizados.

## Alcance concreto

1. Crea `ingesta/capturas/aforos_peatones_bicicletas_madrid.py` siguiendo el mismo
   patrón que `trafico_madrid.py`: descarga -> normaliza a un esquema mínimo y
   consistente (timestamp/hora, id de estación/punto de medida, ubicación,
   peatones contados, bicicletas contadas — los campos que ofrezca realmente el
   dataset).
2. El formato de origen puede no ser un feed en vivo sino ficheros publicados
   periódicamente (p.ej. CSV mensual con datos horarios) — investiga la estructura
   real y documéntala; adapta el parseo en consecuencia.
3. El script, ejecutado una vez, produce una muestra pequeña (unas pocas estaciones
   y/o unas pocas horas, no el histórico completo desde 2019) y la guarda como
   fixture versionado — no como una captura en bucle.
4. Añade un test que no dependa de la red real (con un fixture de ejemplo).
5. Documenta el módulo en `ingesta/README.md`, dejando claro que esta fuente es un
   proxy oficial y sin zona gris de la afluencia peatonal general (a diferencia de la
   tarea 012, que estima popularidad por lugar concreto).

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente: ni cron, ni systemd timer,
  ni un modo `--interval-seconds`/`--daemon`. Es una captura puntual que produce una
  muestra pequeña.
- NO escribas datos de forma continua ni sin acotar en el disco de esta EC2. El
  resultado es una muestra pequeña guardada como fixture versionado en el repo — no
  un bucle de captura hacia `./bronze/...`. La conexión al destino real (S3/BD)
  llegará en una tarea posterior, tras aplicar la infraestructura.
- No deberían hacer falta credenciales (son datos abiertos municipales).
- Si el dataset resulta ser muy grande (histórico completo desde 2019), NO lo leas
  entero en el contexto: inspecciónalo con herramientas de línea de comandos
  (`curl -o`, `head`, `wc -l`, etc.) y trabaja solo con lo necesario para la muestra
  pequeña que pide esta tarea.
- Si la fuente pública no fuera accesible desde este entorno, documenta el problema en
  el resumen de `doc/` y deja igualmente el código preparado con datos de ejemplo.

## Criterios de aceptación

- Ejecutar el script una vez produce una muestra de unos pocos registros
  normalizados, visible en el PR como fixture pequeño commiteado, sin dejar nada
  corriendo ni programado.
- El esquema normalizado y la estructura real del dataset (formato, periodicidad de
  publicación) quedan documentados en `ingesta/README.md` y en el resumen de `doc/`.
