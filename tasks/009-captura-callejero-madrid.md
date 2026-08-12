---
id: 9
slug: captura-callejero-madrid
title: Captura del callejero y grafo viario de Madrid (muestra, carga puntual)
status: pending
force: true
branch: null
pr_number: null
pr_url: null
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-12T22:19:15+00:00'
updated_at: '2026-08-12T22:26:45.133615+00:00'
started_at: null
submitted_at: null
merged_at: null
---

## Contexto

Fase 1 (Ingesta) del proyecto (ver `documents/Memoria_TFM FV.docx`, apartado 6.1,
categoría «Contexto urbano»: callejero y grafo viario). A diferencia de las tareas
002-008 (tráfico, aire, ruido...), esta fuente es de **referencia**, no un stream: el
callejero de Madrid apenas cambia, así que esta captura es una **carga batch
puntual** que nunca necesitará programarse periódicamente, ni siquiera cuando exista
infraestructura real — a diferencia de las capturas en tiempo real, que sí la
necesitarán más adelante.

**Importante — mismo alcance reducido que las tareas anteriores**: la tarea 001
(infraestructura AWS) todavía no se ha aplicado. Esta tarea NO debe cargar el
callejero completo ni dejar nada programado — ver Restricciones.

## Objetivo

Investigar y usar la fuente de datos abiertos del callejero/red viaria de Madrid
(datos.madrid.es publica el «Callejero vigente» y cartografía de ejes de circulación;
investiga el dataset más adecuado y documenta cuál eliges y por qué) y producir una
muestra pequeña de datos normalizados que sirva de prueba de concepto para la futura
carga completa en el grafo urbano (Neo4j, ver apartado 5.2 de la memoria).

## Alcance concreto

1. Crea `ingesta/capturas/callejero_madrid.py` siguiendo el mismo patrón que
   `trafico_madrid.py`: descarga -> normaliza a un esquema mínimo y consistente (id
   de vía/tramo, nombre, tipo de vía, geometría o nodos de inicio/fin si el dataset
   es un grafo, código de distrito/barrio si viene incluido).
2. Documenta explícitamente en el docstring del módulo y en `ingesta/README.md` que
   esta captura es una **carga batch puntual de referencia** (no periódica), a
   diferencia de las capturas en tiempo real ya existentes.
3. El script, ejecutado una vez, produce una muestra pequeña (unas pocas calles o
   tramos, no el callejero completo de Madrid) y la guarda como fixture versionado —
   no el dataset completo en disco.
4. Añade un test que no dependa de la red real (con un fixture de ejemplo).

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente: ni cron, ni systemd timer,
  ni un modo `--interval-seconds`/`--daemon`. Es una carga puntual invocada a mano.
- NO descargues ni escribas el dataset completo en el disco de esta EC2 (disco muy
  limitado): solo una muestra pequeña y acotada, guardada como fixture versionado en
  el repo. La carga completa real llegará en una tarea posterior, directamente hacia
  su destino (S3/Neo4j), una vez exista la infraestructura.
- No deberían hacer falta credenciales (son datos abiertos municipales).
- Si la fuente pública no fuera accesible desde este entorno, documenta el problema en
  el resumen de `doc/` y deja igualmente el código preparado con datos de ejemplo.

## Criterios de aceptación

- Ejecutar el script una vez produce una muestra de unos pocos registros
  normalizados, visible en el PR como fixture pequeño commiteado, sin dejar nada
  corriendo ni programado.
- El esquema normalizado, la fuente elegida, y el hecho de que es una carga puntual
  (no periódica) quedan documentados en `ingesta/README.md` y en el resumen de `doc/`.

## Nota tras un primer intento fallido

Un intento anterior agotó el presupuesto por tarea leyendo el dataset completo directamente en el contexto (varios millones de tokens). El dataset de origen puede ser grande — **no lo leas entero**: inspecciónalo con herramientas de línea de comandos (`curl -o`, `head`, `wc -l`, `jq`, `ogrinfo`, etc.) y trabaja solo con los primeros registros necesarios para la muestra pequeña que pide la tarea.
