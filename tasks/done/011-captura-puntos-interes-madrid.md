---
id: 11
slug: captura-puntos-interes-madrid
title: Captura de puntos de interés de Madrid (muestra, carga puntual)
status: done
force: true
branch: task/011-captura-puntos-interes-madrid
pr_number: 58
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/58
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-12T22:19:15+00:00'
updated_at: '2026-08-12T23:02:39.523234+00:00'
started_at: '2026-08-12T22:54:03.197533+00:00'
submitted_at: '2026-08-12T23:01:33.074509+00:00'
merged_at: '2026-08-12T23:01:36Z'
---

## Contexto

Fase 1 (Ingesta) del proyecto (ver `documents/Memoria_TFM FV.docx`, apartado 6.1,
categoría «Contexto urbano»: puntos de interés). Igual que las tareas 009 y 010, es
una fuente de referencia casi estática: una **carga batch puntual**, no un stream, y
no necesitará programarse periódicamente ni siquiera cuando exista infraestructura
real.

**Importante — mismo alcance reducido que las tareas anteriores**: la tarea 001
(infraestructura AWS) todavía no se ha aplicado. Esta tarea NO debe cargar todos los
POIs de Madrid ni dejar nada programado — ver Restricciones.

## Objetivo

Investigar y usar una fuente de datos abiertos de puntos de interés de Madrid
(datos.madrid.es publica varios datasets por categoría: monumentos y lugares de
interés turístico, instalaciones deportivas, bibliotecas, mercados, etc. — elige
**una o dos categorías representativas** para esta primera captura, no intentes
cubrir todas; documenta cuáles eliges y por qué) y produce una muestra pequeña de
datos normalizados. Estos POIs son los nodos que el asistente conversacional
consultará para responder preguntas como «¿merece la pena ir a X lugar?».

## Alcance concreto

1. Crea `ingesta/capturas/poi_madrid.py` siguiendo el mismo patrón que
   `trafico_madrid.py`: descarga -> normaliza a un esquema mínimo y consistente (id
   del POI, nombre, categoría, ubicación, distrito/barrio si viene incluido en la
   fuente o se puede derivar).
2. Documenta explícitamente que esta captura es una **carga batch puntual de
   referencia** (no periódica).
3. El script, ejecutado una vez, produce una muestra pequeña (unos pocos POIs de la
   categoría o categorías elegidas, no el catálogo completo) y la guarda como fixture
   versionado — no el dataset completo en disco.
4. Añade un test que no dependa de la red real (con un fixture de ejemplo).

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente: ni cron, ni systemd timer,
  ni un modo `--interval-seconds`/`--daemon`. Es una carga puntual invocada a mano.
- NO descargues ni escribas el catálogo completo en el disco de esta EC2: solo una
  muestra pequeña y acotada, guardada como fixture versionado en el repo. La carga
  completa real (de todas las categorías de POI relevantes) llegará en una tarea
  posterior, directamente hacia su destino (S3/Neo4j), una vez exista la
  infraestructura.
- No deberían hacer falta credenciales (son datos abiertos municipales).
- Si la fuente pública no fuera accesible desde este entorno, documenta el problema en
  el resumen de `doc/` y deja igualmente el código preparado con datos de ejemplo.

## Criterios de aceptación

- Ejecutar el script una vez produce una muestra de unos pocos POIs normalizados,
  visible en el PR como fixture pequeño commiteado, sin dejar nada corriendo ni
  programado.
- El esquema normalizado, la(s) categoría(s) elegida(s), y el hecho de que es una
  carga puntual (no periódica) quedan documentados en `ingesta/README.md` y en el
  resumen de `doc/`.
