---
id: 3
slug: captura-transporte-publico-madrid
title: Captura de datos de transporte público de Madrid (muestra)
status: in_review
force: true
branch: task/003-captura-transporte-publico-madrid
pr_number: 50
pr_url: https://github.com/madrono-ucm/madronoTFM/pull/50
attempts: 0
next_retry_at: null
last_error: null
created_at: '2026-08-12T01:02:26+00:00'
updated_at: '2026-08-12T01:09:59.946346+00:00'
started_at: '2026-08-12T01:04:28.486684+00:00'
submitted_at: '2026-08-12T01:09:59.946217+00:00'
merged_at: null
---

## Contexto

Continúa la Fase 1 (Ingesta) del proyecto (ver `documents/Memoria_TFM FV.docx`,
apartado 6.1, categoría «Movilidad y transporte»). La tarea 002 ya implementó el
patrón de captura para tráfico (`ingesta/capturas/trafico_madrid.py`); esta tarea
sigue el mismo patrón para transporte público en tiempo real.

**Importante — alcance reducido respecto a la tarea 002**: la tarea 001
(infraestructura AWS) todavía no se ha aplicado, así que no hay S3 ni base de datos
donde aterrizar datos en volumen. Esta tarea NO debe implementar un productor
continuo ni dejar nada programado — ver Restricciones.

## Objetivo

Investigar y usar una fuente de datos abiertos de transporte público de Madrid en
tiempo real (p.ej. EMT Madrid — portal opendata.emtmadrid.es, que requiere registro
gratuito para una API key; o el Consorcio Regional de Transportes, CRTM — usa tu
criterio y documenta por qué eliges una u otra) y producir una **muestra pequeña** de
datos normalizados (posiciones o próximas llegadas de una línea/parada concretas,
por ejemplo).

## Alcance concreto

1. Crea `ingesta/capturas/transporte_publico_madrid.py` siguiendo el mismo patrón que
   `trafico_madrid.py`: descarga -> normaliza a un esquema mínimo y consistente
   (timestamp, id de parada/línea/vehículo, ubicación si aplica, y el dato relevante
   de la fuente — tiempo de espera, ocupación, etc.).
2. Si la fuente elegida requiere una API key gratuita, documenta cómo obtenerla y
   léela de una variable de entorno (p.ej. `EMT_API_KEY`), sin hardcodearla.
3. El script, ejecutado una vez, produce una muestra pequeña (unos pocos registros,
   no todas las líneas/paradas de Madrid) y la guarda como fixture versionado — no
   como una captura en bucle.
4. Añade un test que no dependa de la red real (con un fixture de ejemplo), igual que
   `ingesta/tests/test_trafico_madrid.py`.
5. Documenta el módulo en `ingesta/README.md` (añade una sección para esta fuente,
   igual que ya existe para tráfico).

## Restricciones

- NO dejes nada programado para ejecutarse periódicamente: ni cron, ni systemd timer,
  ni un modo `--interval-seconds`/`--daemon` en el propio script. Es una captura
  puntual, invocada a mano, que produce una muestra pequeña.
- NO escribas datos de forma continua ni sin acotar en el disco de esta EC2 (disco muy
  limitado). El resultado es una muestra pequeña (unos pocos registros) guardada como
  fixture versionado en el repo, p.ej. bajo `ingesta/capturas/samples/` — no un bucle
  de captura hacia `./bronze/...`. Cuando exista infraestructura real (tras aplicar la
  tarea 001), otra tarea conectará esta captura a su destino definitivo (S3 o base de
  datos, según el origen).
- No uses APIs de pago. Una API key gratuita con registro es aceptable.
- Si la fuente pública no fuera accesible desde este entorno, documenta el problema en
  el resumen de `doc/` y deja igualmente el código preparado con datos de ejemplo.

## Criterios de aceptación

- Ejecutar el script una vez produce una muestra de unos pocos registros normalizados,
  visible en el PR como fixture pequeño commiteado, sin dejar nada corriendo ni
  programado.
- El esquema normalizado y las decisiones tomadas (fuente elegida, autenticación)
  quedan documentadas en `ingesta/README.md` y en el resumen de `doc/`.
