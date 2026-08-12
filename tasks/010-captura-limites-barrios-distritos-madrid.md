---
id: 10
slug: captura-limites-barrios-distritos-madrid
title: Captura de límites de barrios y distritos de Madrid (muestra, carga puntual)
status: in_review
force: true
branch: task/010-captura-limites-barrios-distritos-madrid
pr_number: 57
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/57
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-12T22:19:15+00:00'
updated_at: '2026-08-12T22:51:54.358101+00:00'
started_at: '2026-08-12T22:44:04.443868+00:00'
submitted_at: '2026-08-12T22:51:54.357953+00:00'
merged_at: null
---

## Contexto

Fase 1 (Ingesta) del proyecto (ver `documents/Memoria_TFM FV.docx`, apartado 6.1,
categoría «Contexto urbano»: límites de barrio y distrito). Igual que la tarea 009,
es una fuente de **referencia** casi estática (los límites administrativos de Madrid
cambian muy raramente): una **carga batch puntual**, no un stream, y no necesitará
programarse periódicamente ni siquiera cuando exista infraestructura real.

**Importante — mismo alcance reducido que las tareas anteriores**: la tarea 001
(infraestructura AWS) todavía no se ha aplicado. Esta tarea NO debe cargar todos los
barrios/distritos ni dejar nada programado — ver Restricciones.

## Objetivo

Investigar y usar la fuente de datos abiertos de límites administrativos de Madrid
(datos.madrid.es publica geometrías de distritos y barrios) y producir una muestra
pequeña de datos normalizados. Estos límites son clave para relacionar el resto de
fuentes (tráfico, aire, ruido...) con una unidad geográfica común en el grafo urbano.

## Alcance concreto

1. Crea `ingesta/capturas/barrios_distritos_madrid.py` siguiendo el mismo patrón que
   `trafico_madrid.py`: descarga -> normaliza a un esquema mínimo y consistente (id
   de distrito, id de barrio, nombres, geometría del límite — o su representación
   simplificada si la geometría completa es muy pesada, documenta la decisión).
2. Documenta explícitamente que esta captura es una **carga batch puntual de
   referencia** (no periódica).
3. El script, ejecutado una vez, produce una muestra pequeña (unos pocos
   barrios/distritos, no los 131 barrios de Madrid completos) y la guarda como
   fixture versionado — no el dataset completo en disco.
4. Añade un test que no dependa de la red real (con un fixture de ejemplo).

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente: ni cron, ni systemd timer,
  ni un modo `--interval-seconds`/`--daemon`. Es una carga puntual invocada a mano.
- NO descargues ni escribas el dataset completo en el disco de esta EC2: solo una
  muestra pequeña y acotada, guardada como fixture versionado en el repo. La carga
  completa real llegará en una tarea posterior, directamente hacia su destino
  (S3/Neo4j), una vez exista la infraestructura.
- No deberían hacer falta credenciales (son datos abiertos municipales).
- Si la fuente pública no fuera accesible desde este entorno, documenta el problema en
  el resumen de `doc/` y deja igualmente el código preparado con datos de ejemplo.

## Criterios de aceptación

- Ejecutar el script una vez produce una muestra de unos pocos barrios/distritos
  normalizados, visible en el PR como fixture pequeño commiteado, sin dejar nada
  corriendo ni programado.
- El esquema normalizado, la fuente elegida, y el hecho de que es una carga puntual
  (no periódica) quedan documentados en `ingesta/README.md` y en el resumen de `doc/`.
